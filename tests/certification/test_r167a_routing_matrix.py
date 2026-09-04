# ruff: noqa: E501
"""R167-A §4B/§4D/§9 — routing matrix + failure-shape classification, test-only injection.

Every case runs the REAL ``SimpleScoringRouter`` and the REAL ``ExecutionService`` against
scripted adapters. Nothing in ``core/`` / ``apps/`` / ``providers/`` is patched; the only
injection is the adapter script, a test-module object production code cannot import
(``test_injection_is_unreachable_from_production``).

Each ``case_*`` asserts the behaviour ``evidence/provider_contract.md`` documents; the
printed ``MATRIX|`` rows are copied verbatim into ``evidence/provider_routing_matrix.md``
and tagged [INJECTED].

The real captured failure shapes in ``evidence/failure_shapes/`` are replayed through the
shipped Groq adapter over ``httpx.MockTransport`` in ``test_shape_*`` so the classification
map in ``evidence/error_classification_map.md`` is derived from the code, not from reading it.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from core.contracts.domain import (
    BindingAvailability,
    CredentialStatus,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.model_policy import AutoModelPolicy, ExplicitModelPolicy, FallbackScope
from core.contracts.provider import (
    CredentialHealth,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderManifest,
    ProviderOperation,
)
from core.contracts.routing import RoutingDecision, RoutingRequest
from core.execution import ExecutionReport, ExecutionService
from core.execution.errors import CredentialNotConfigured
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.providers.errors import DuplicateRegistration
from core.routing import NoEligibleCandidates, SimpleScoringRouter
from core.usage.memory import InMemoryUsageAccounting
from providers.real.genspark_llm import MANIFEST as GENSPARK_MANIFEST
from providers.real.genspark_llm import GensparkLLMAdapter
from providers.real.groq import MANIFEST as GROQ_MANIFEST
from providers.real.groq import GroqAdapter

REPO = Path(__file__).resolve().parents[2]
SHAPES = REPO / "evidence" / "failure_shapes"
M = "shared-model"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(_: float) -> None:
    return None


# --- scripted adapter ---------------------------------------------------------------


def err(
    category: ProviderErrorCategory,
    *,
    retryable: bool = False,
    retry_after_ms: int | None = None,
    code: str | None = None,
) -> ProviderError:
    return ProviderError(
        category=category,
        retryable=retryable,
        retry_after_ms=retry_after_ms,
        provider_code=code,
        safe_message=f"injected {category.value}",
    )


class ScriptedAdapter:
    def __init__(self, script: list[object] | None = None) -> None:
        self.script = list(script or [])
        self.requests: list[ProviderGenerateRequest] = []

    def get_manifest(self) -> ProviderManifest:  # pragma: no cover
        raise NotImplementedError

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(credential_ref=credential_ref, status=CredentialStatus.ACTIVE)

    async def discover_models(self, account_id: UUID | None = None) -> list[DiscoveredModel]:
        return []  # pragma: no cover

    async def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover
        return ProviderCapabilities()

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        self.requests.append(request)
        step: object = self.script.pop(0) if self.script else {"content": "ok"}
        if isinstance(step, Exception):
            raise step
        if isinstance(step, ProviderError):
            return ProviderGenerateResponse(
                request_id=request.request_id, succeeded=False, error=step, latency_ms=3
            )
        assert isinstance(step, dict)
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output=step,
            usage={"units": 1},
            latency_ms=2,
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:  # pragma: no cover
        raise NotImplementedError

    def normalize_error(self, error: object) -> ProviderError:
        return err(ProviderErrorCategory.NON_RETRYABLE_ERROR, code=type(error).__name__)


# --- world: registries + router + service -------------------------------------------


def _manifest(key: str) -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "id": key,
            "name": key,
            "version": "1.0.0",
            "status": "active",
            "auth": {"types": ["api_key"], "supports_refresh": False},
            "account_pool": {"supported": False},
            "capabilities": {"chat": True},
            "operations": ["generate_text"],
            "models": {"discovery": "static", "static_models": []},
            "rate_limits": {"strategy": "provider_defined"},
            "health": {"checks": ["ping"]},
            "errors": {"mapping": "error_map.json"},
        }
    )


def _model(key: str, tier: ModelTier = ModelTier.MEDIUM) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=tier,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.5,
        reliability_score=0.5,
        cost_score=0.5,
        speed_score=0.5,
        status=ModelStatus.ACTIVE,
    )


class World:
    """Mirrors apps/composition/runtime.py::_bind_real_providers: one Provider per key,
    one credential_ref per provider, account_id never set."""

    def __init__(self) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.adapters: dict[UUID, ScriptedAdapter] = {}
        self.credential_refs: dict[UUID, str] = {}
        self.by_key: dict[str, Provider] = {}
        self.registered_models: set[str] = set()
        self.usage = InMemoryUsageAccounting()

    def provider(self, key: str, *models: Model, script: list[object] | None = None) -> Provider:
        provider = Provider(
            id=uuid4(),
            provider_key=key,
            display_name=key,
            status=ProviderStatus.ACTIVE,
            auth_types=["api_key"],
            supports_account_pool=False,
        )
        self.providers.register(provider, _manifest(key))
        self.adapters[provider.id] = ScriptedAdapter(script)
        self.credential_refs[provider.id] = f"secret-ref://{key}"
        self.by_key[key] = provider
        for model in models:
            if model.model_key not in self.registered_models:
                self.models.register(model)
                self.registered_models.add(model.model_key)
            self.bindings.register(
                ProviderModelBinding(
                    provider_id=provider.id,
                    model_id=model.id,
                    provider_model_name=model.model_key,
                    availability=BindingAvailability.AVAILABLE,
                )
            )
        return provider

    def router(self) -> SimpleScoringRouter:
        return SimpleScoringRouter(self.providers, self.models, self.bindings)

    def service(self, *, retries: int = 1) -> ExecutionService:
        return ExecutionService(
            adapters=self.adapters,
            credential_refs=self.credential_refs,
            bindings=self.bindings,
            max_retries_per_candidate=retries,
            usage=self.usage,
            sleeper=_no_sleep,
        )

    def route(self, policy: Any) -> RoutingDecision:
        return self.router().route(
            RoutingRequest(operation=ProviderOperation.GENERATE_TEXT, model_policy=policy)
        )

    def execute(
        self, decision: RoutingDecision, *, tenant: UUID | None = None, retries: int = 1
    ) -> ExecutionReport:
        tenant_id = tenant or uuid4()
        self.usage.configure_tenant(tenant_id, plan="test", task_units_limit=1000)
        return run(
            self.service(retries=retries).execute_single(
                tenant_id=tenant_id,
                user_id=uuid4(),
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload={"ask": "hi"},
                request_hash="h",
            )
        )


Attempt = tuple[str, int, bool, str | None]


def _attempts(report: ExecutionReport, world: World) -> list[Attempt]:
    keys = {p.id: k for k, p in world.by_key.items()}
    return [
        (
            keys[a.candidate.provider_id],
            a.attempt,
            a.succeeded,
            a.error.category.value if a.error else None,
        )
        for node in report.nodes
        for a in node.attempts
    ]


def _row(case: str, world: World, report: ExecutionReport, note: str) -> None:
    refs = sorted({r.credential_ref for a in world.adapters.values() for r in a.requests})
    accounts = sorted({str(r.account_id) for a in world.adapters.values() for r in a.requests})
    ledger = (
        None if report.usage is None else (report.usage.status.value, report.usage.units_settled)
    )
    print(
        f"MATRIX|{case}|status={report.execution.status.value}|attempts={_attempts(report, world)}"
        f"|credential_refs_used={refs}|account_ids={accounts}|ledger={ledger}|{note}"
    )


def explicit(
    model: str, scope: FallbackScope | None = None, allow: bool | None = None
) -> ExplicitModelPolicy:
    return ExplicitModelPolicy(
        type="explicit_model", model_id=model, allow_fallback=allow, fallback_scope=scope
    )


# --- §4B cases -----------------------------------------------------------------------


def case_a_healthy() -> None:
    w = World()
    m = _model(M)
    w.provider("A", m)
    r = w.execute(w.route(explicit(M)))
    assert r.execution.status.value == "succeeded"
    assert _attempts(r, w) == [("A", 1, True, None)]
    _row("A_healthy", w, r, "class=A single account; 1 call; settled 1")


def case_a_restricted_then_b() -> None:
    """A answers the real Groq shape (400 organization_restricted → invalid_credential)."""
    w = World()
    m = _model(M)
    w.provider(
        "A",
        m,
        script=[err(ProviderErrorCategory.INVALID_CREDENTIAL, code="organization_restricted")],
    )
    w.provider("B", m)
    r = w.execute(w.route(explicit(M, FallbackScope.SAME_MODEL_DIFFERENT_PROVIDER)))
    assert r.execution.status.value == "succeeded"
    assert _attempts(r, w) == [("A", 1, False, "invalid_credential"), ("B", 1, True, None)]
    _row("A_restricted_B_healthy", w, r, "class=B failover to B without retry on A (non-retryable)")


def case_a_retryable() -> None:
    w = World()
    m = _model(M)
    w.provider(
        "A",
        m,
        script=[
            err(ProviderErrorCategory.RATE_LIMITED, retryable=True, retry_after_ms=10),
            err(ProviderErrorCategory.RETRYABLE_SERVER_ERROR, retryable=True),
        ],
    )
    w.provider("B", m)
    r = w.execute(w.route(explicit(M, FallbackScope.SAME_MODEL_DIFFERENT_PROVIDER)), retries=1)
    assert _attempts(r, w) == [
        ("A", 1, False, "rate_limited"),
        ("A", 2, False, "retryable_server_error"),
        ("B", 1, True, None),
    ]
    _row(
        "A_retryable_429_5xx",
        w,
        r,
        "retries=1 on A honoured then failover; timeout is the same path",
    )


def case_a_credential_fault_single_provider() -> None:
    w = World()
    m = _model(M)
    w.provider(
        "A", m, script=[err(ProviderErrorCategory.INVALID_CREDENTIAL, code="invalid_api_key")]
    )
    r = w.execute(w.route(explicit(M, FallbackScope.MAX_ESCALATION)))
    assert r.execution.status.value == "failed"
    assert _attempts(r, w) == [("A", 1, False, "invalid_credential")]
    _row(
        "A_credential_fault_only_A",
        w,
        r,
        "no second credential for A exists in the contract → run fails; matches live 15_developer_transcript §10",
    )


def case_a_malformed() -> None:
    w = World()
    m = _model(M)
    w.provider(
        "A", m, script=[err(ProviderErrorCategory.BAD_REQUEST, code="invalid_request_error")]
    )
    w.provider("B", m)
    r = w.execute(w.route(explicit(M, FallbackScope.SAME_MODEL_DIFFERENT_PROVIDER)))
    assert r.execution.status.value == "failed"
    assert _attempts(r, w) == [("A", 1, False, "bad_request")]
    assert not w.adapters[w.by_key["B"].id].requests
    _row("A_malformed_request", w, r, "request-indicting: no retry, no failover, B never called")


def case_same_model_b_and_c() -> None:
    w = World()
    m = _model(M)
    w.provider("A", m, script=[err(ProviderErrorCategory.PROVIDER_UNAVAILABLE)])
    w.provider("B", m, script=[err(ProviderErrorCategory.MODEL_UNAVAILABLE)])
    w.provider("C", m)
    r = w.execute(w.route(explicit(M, FallbackScope.SAME_MODEL_DIFFERENT_PROVIDER)))
    assert r.execution.status.value == "succeeded"
    assert [a[0] for a in _attempts(r, w)] == ["A", "B", "C"]
    _row("same_model_via_B_then_C", w, r, "class=B chain in Router order")


def case_same_model_different_provider_default() -> None:
    """Silent caller (no scope) under AUTO gets same_model_different_provider (cf37e69)."""
    w = World()
    m = _model(M)
    w.provider("A", m, script=[err(ProviderErrorCategory.PROVIDER_UNAVAILABLE)])
    w.provider("B", m)
    r = w.execute(w.route(AutoModelPolicy(type="auto")))
    assert r.execution.status.value == "succeeded"
    assert len(_attempts(r, w)) == 2
    _row("same_model_different_provider_silent_default", w, r, "class=B; default scope engaged")


def case_model_unavailable_on_bound_account() -> None:
    w = World()
    m = _model(M)
    other = _model("other-model")
    w.provider("A", m, script=[err(ProviderErrorCategory.MODEL_UNAVAILABLE, code="http_404")])
    w.provider("B", other)
    r = w.execute(w.route(explicit(M, FallbackScope.SAME_TIER)))
    assert r.execution.status.value == "succeeded"
    assert [a[0] for a in _attempts(r, w)] == ["A", "B"]
    _row(
        "model_unavailable_on_bound_account",
        w,
        r,
        "class=C: escalated to a different model on B under same_tier",
    )


def case_concurrent_tenants_a_degraded() -> None:
    w = World()
    m = _model(M)
    w.provider(
        "A",
        m,
        script=[err(ProviderErrorCategory.RATE_LIMITED, retryable=True, retry_after_ms=5)] * 4,
    )
    w.provider("B", m)
    t1, t2 = uuid4(), uuid4()
    dec = w.route(explicit(M, FallbackScope.SAME_MODEL_DIFFERENT_PROVIDER))
    r1 = w.execute(dec, tenant=t1, retries=1)
    r2 = w.execute(dec, tenant=t2, retries=1)
    for r in (r1, r2):
        assert r.execution.status.value == "succeeded"
    assert w.usage.summary(t1).task_units.used == 1.0
    assert w.usage.summary(t2).task_units.used == 1.0
    assert r1.execution.tenant_id != r2.execution.tenant_id
    _row(
        "concurrent_tenants_A_degraded",
        w,
        r2,
        "class=D: each tenant billed exactly 1 unit; A rate-limited both times; no cross-tenant state",
    )


def case_two_credentials_same_provider() -> None:
    """§4C — can the contract hold two credentials for ONE provider?
    Pool-less path (this case, unchanged): credential_refs is Mapping[provider_id, str];
    a second registration of the same provider_key is refused by the registry; a second
    dict entry overwrites the first.
    R168 D-03/D-04 added the POOLED path: ResourceSelector.complete() +
    ExecutionService(account_credentials=...) give each account of ONE provider its own
    credential_ref — proven hermetically in tests/routing/test_d03_d04_two_account_failover.py."""
    w = World()
    m = _model(M)
    p = w.provider("A", m)
    first = w.credential_refs[p.id]
    w.credential_refs[p.id] = "secret-ref://A-second"
    assert w.credential_refs[p.id] != first  # overwritten, not pooled
    with pytest.raises(DuplicateRegistration):
        w.providers.register(p, _manifest("A"))  # duplicate key refused
    print(
        "MATRIX|two_credentials_same_provider|SUPPORTED VIA ACCOUNT POOL (R168 D-03/D-04)"
        "|pool-less path stays 1:1 per provider_id; pooled path: ResourceSelector.complete"
        " + per-account credential_ref, hermetic proof tests/routing/test_d03_d04_*"
    )


def case_credential_missing_is_precheck_failure() -> None:
    w = World()
    m = _model(M)
    p = w.provider("A", m)
    del w.credential_refs[p.id]
    with pytest.raises(CredentialNotConfigured):
        w.execute(w.route(explicit(M)))
    print("MATRIX|credential_missing|refused before any provider call (CredentialNotConfigured)")


def case_no_route() -> None:
    w = World()
    w.provider("A", _model("only"))
    with pytest.raises(NoEligibleCandidates):
        w.route(explicit("nonexistent"))
    print(
        "MATRIX|model_not_bound_anywhere|NoEligibleCandidates at routing time; zero provider calls"
    )


CASES = [
    case_a_healthy,
    case_a_restricted_then_b,
    case_a_retryable,
    case_a_credential_fault_single_provider,
    case_a_malformed,
    case_same_model_b_and_c,
    case_same_model_different_provider_default,
    case_model_unavailable_on_bound_account,
    case_concurrent_tenants_a_degraded,
    case_two_credentials_same_provider,
    case_credential_missing_is_precheck_failure,
    case_no_route,
]


@pytest.mark.parametrize("case", CASES, ids=[c.__name__ for c in CASES])
def test_matrix(case: Any) -> None:
    case()


# --- §4D real shapes replayed through the shipped Groq adapter ----------------------

CRED_REF = "credref_r167a_placeholder"


def _groq_replay(status: int, body: Any) -> ProviderGenerateResponse:
    def responder(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    adapter = GroqAdapter(
        GROQ_MANIFEST,
        secret_resolver=lambda ref: "not-a-real-key",
        health_credential_ref=CRED_REF,
        transport=httpx.MockTransport(responder),
    )
    request = ProviderGenerateRequest.model_validate(
        {
            "request_id": uuid4(),
            "tenant_id": uuid4(),
            "operation": ProviderOperation.GENERATE_TEXT,
            "provider_model_name": "allam-2-7b",
            "credential_ref": CRED_REF,
            "payload": {"ask": "hello"},
        }
    )
    return run(adapter.generate(request))


def _genspark_replay(status: int, body: Any) -> ProviderGenerateResponse:
    def responder(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    adapter = GensparkLLMAdapter(
        GENSPARK_MANIFEST,
        secret_resolver=lambda ref: "not-a-real-key",
        health_credential_ref=CRED_REF,
        transport=httpx.MockTransport(responder),
    )
    request = ProviderGenerateRequest.model_validate(
        {
            "request_id": uuid4(),
            "tenant_id": uuid4(),
            "operation": ProviderOperation.GENERATE_TEXT,
            "provider_model_name": "gpt-5-nano",
            "credential_ref": CRED_REF,
            "payload": {"ask": "hello"},
        }
    )
    return run(adapter.generate(request))


def _shape(name: str) -> tuple[int, Any]:
    doc = json.loads((SHAPES / name).read_text())
    return int(doc["_meta"]["http_status"]), doc["body"]


def test_shape_groq_org_restricted_is_invalid_credential() -> None:
    status, body = _shape("groq_400_organization_restricted.json")
    r = _groq_replay(status, body)
    assert r.succeeded is False and r.error is not None
    assert r.error.category is ProviderErrorCategory.INVALID_CREDENTIAL
    assert r.error.retryable is False
    assert r.error.provider_code == "organization_restricted"
    print(
        f"MAP|groq_400_organization_restricted|{r.error.category.value}|retryable={r.error.retryable}"
    )


def test_shape_401_detail_only_is_invalid_credential() -> None:
    status, body = _shape("genspark_llm_invalid_credential.json")
    r = _groq_replay(status, body)
    assert r.error is not None
    assert r.error.category is ProviderErrorCategory.INVALID_CREDENTIAL
    print(
        f"MAP|401_detail_invalid_or_expired_token|{r.error.category.value}|retryable={r.error.retryable}"
    )


def test_shape_unknown_model_400_detail_only_is_model_unavailable() -> None:
    """Proxy answers 400 + {'detail': "Model ... is not allowed"} with no error.code.
    R167-A booked bad_request (request-indicting ⇒ no failover) — ledger D-02.
    R168: the Groq normaliser detects the shape structurally and books
    model_unavailable (candidate-indicting ⇒ failover permitted); the detail
    text never crosses (tests/providers/test_d02_groq_detail_only_400.py)."""
    status, body = _shape("genspark_llm_unknown_model.json")
    r = _groq_replay(status, body)
    assert r.error is not None
    print(
        f"MAP|400_detail_model_not_allowed|{r.error.category.value}|retryable={r.error.retryable}"
        "|D-02 FIXED R168"
    )
    assert r.error.category is ProviderErrorCategory.MODEL_UNAVAILABLE
    assert r.error.provider_code == "model_not_allowed"


def test_shape_200_plan_refusal_is_quota_exceeded_r168() -> None:
    """D-01 fixed in R168: the genspark_llm adapter (origin of the captured
    shape) now books an in-band HTTP-200 plan refusal as a FAILED,
    account-indicting call. R167-A recorded this as SUCCESS with no
    classification path; that assertion was the defect, not the contract."""
    doc = json.loads((SHAPES / "genspark_llm_200_plan_refusal.json").read_text())
    assert doc["_meta"]["http_status"] == 200
    r = _genspark_replay(200, doc["body"])
    assert r.succeeded is False and r.error is not None
    assert r.error.category is ProviderErrorCategory.QUOTA_EXCEEDED
    assert r.error.retryable is False
    assert r.error.provider_code == "plan_refusal_200"
    assert r.output == {} and r.usage == {}
    assert "Free-plan" not in r.error.model_dump_json()
    print("MAP|200_plan_refusal|quota_exceeded|retryable=False|D-01 FIXED R168")


# --- §9 injection is unreachable from production ------------------------------------


def test_injection_is_unreachable_from_production() -> None:
    # Import/usage forms only — docstrings that MENTION httpx.MockTransport as the
    # documented test seam are not reachability (the adapters accept any transport).
    pattern = re.compile(
        r"^\s*(from|import)\s+tests\b|ScriptedAdapter|FakeAdapter|MockTransport\(", re.M
    )
    hits = [
        str(p.relative_to(REPO))
        for d in ("apps", "core", "providers")
        for p in (REPO / d).rglob("*.py")
        if pattern.search(p.read_text(errors="ignore"))
    ]
    assert hits == []
    assert "tests.certification.test_r167a_routing_matrix" in sys.modules
