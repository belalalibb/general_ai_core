"""T-IMPL-034 — MVP Phase 8 slice 2: provider failure + rate-limit hardening.

Adversarial tests over EXISTING surfaces (R054 slicing decision; fixes for
exposed defects in-scope, features out-of-scope). Gap-focused by design —
this suite deliberately does NOT duplicate:

- tests/execution/test_execution_service.py (~40 tests): retry taxonomy,
  failover order, bounded retry, retry_after_ms via sleeper, request-
  indicting no-shop rule, raised-exception normalization at service level,
  usage settlement including crash paths.
- tests/providers/test_provider_registries.py: health aggregation basics
  (one failed account degrades-not-kills, all-failing is account-scope
  evidence, explicit adverse signal wins, template cannot pass).
- tests/contract/test_provider_contract.py: closed enum sets and the
  RateLimitStatus coherence rules (T-IMPL-034 checkpoint 1).

What THIS suite attacks (30 §11-§14; 20 §4; 10 §9):

1. ALL 12 ProviderErrorCategory values driven through POST /v1/execute
   end-to-end — exact unified code + HTTP status asserted independently
   (hardcoded expectations, not re-imported from the implementation), and
   the mapping table is proven COMPLETE against the closed enum so a 13th
   category cannot ship unmapped.
2. Raw-internals containment at the API boundary: provider_code, raised
   exception text, and stack traces never appear in any response body —
   only safe_message crosses.
3. Adapter failure containment on /v1/execute: a RAISING adapter and a
   contract-breaching adapter (failed-without-error) both yield the
   normalized unified surface, never a 500/stack trace, and the usage
   reservation SETTLES (no leaked holds), including across REPEATED
   failures.
4. Health conflation attacks beyond the existing basics: a HEALTHY
   provider-scope signal must NOT launder failing accounts; template rule
   beats every other input; account states cross the report verbatim.
5. Rate-limit honesty at the API surface: retryable rate_limited errors
   cross with retryable=true and 429; the GET diagnosis path carries the
   same specific code as the POST failure.
6. Router behavior under ineligible providers on the EXISTING surface:
   a template/non-functional provider and a status-disabled provider are
   excluded from routing and surface as explainable 503 model_unavailable.

Hermetic: httpx ASGI transport, scripted fakes, asyncio.run (ADR-0001).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from core.contracts.domain import Provider, ProviderStatus
from core.contracts.provider import (
    AccountHealthCheckState,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealthState,
    RateLimitState,
)
from core.providers.registry import ProviderRegistry, aggregate_provider_health
from tests.api.test_execute_api import (
    FakeAdapter,
    World,
    _assert_unified_error,
    _get,
    _post,
    _provider_error,
    run,
)
from tests.providers.test_provider_registries import (
    _entry,
    _manifest,
    _provider,
    _template_manifest,
)

# --- 1. all 12 categories through the API, mapping asserted independently -------------

#: EXPECTED unified code + HTTP status per category — hardcoded on purpose
#: (asserting against a re-import of the implementation table would make the
#: test a tautology). Source of truth: 10 §9 + the recorded mapping decisions
#: in apps/api/errors.py module docstring.
_EXPECTED_API_MAPPING: dict[ProviderErrorCategory, tuple[str, int]] = {
    ProviderErrorCategory.RATE_LIMITED: ("rate_limited", 429),
    ProviderErrorCategory.QUOTA_EXCEEDED: ("entitlement_exceeded", 403),
    ProviderErrorCategory.MODEL_UNAVAILABLE: ("model_unavailable", 503),
    ProviderErrorCategory.PROVIDER_UNAVAILABLE: ("provider_unavailable", 503),
    ProviderErrorCategory.AUTH_EXPIRED: ("execution_failed", 502),
    ProviderErrorCategory.INVALID_CREDENTIAL: ("execution_failed", 502),
    ProviderErrorCategory.UNSUPPORTED_CAPABILITY: ("execution_failed", 502),
    ProviderErrorCategory.BAD_REQUEST: ("execution_failed", 502),
    ProviderErrorCategory.CONTENT_REJECTED: ("execution_failed", 502),
    ProviderErrorCategory.TIMEOUT: ("execution_failed", 502),
    ProviderErrorCategory.RETRYABLE_SERVER_ERROR: ("execution_failed", 502),
    ProviderErrorCategory.NON_RETRYABLE_ERROR: ("execution_failed", 502),
}


def test_expected_mapping_table_is_complete_against_the_closed_enum() -> None:
    """A 13th ProviderErrorCategory cannot ship without an explicit API
    mapping decision — this test breaks the moment the enum grows."""
    assert set(_EXPECTED_API_MAPPING.keys()) == set(ProviderErrorCategory)


@pytest.mark.parametrize("category", list(ProviderErrorCategory))
def test_every_category_maps_to_exact_unified_code_and_status(
    category: ProviderErrorCategory,
) -> None:
    expected_code, expected_status = _EXPECTED_API_MAPPING[category]
    world = World(script=[_provider_error(category)])
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == expected_status, category
    payload = response.json()
    _assert_unified_error(payload, expected_code)
    details = payload["error"]["details"]
    assert details["provider_error_category"] == category.value
    UUID(details["execution_id"])  # always diagnosable via GET
    # 30 §14 / 20 §4: only safe_message crosses; the raw provider code and
    # any auth/credential category detail must never reach clients.
    assert payload["error"]["message"] == f"fake {category.value}"
    assert "RAW-INTERNAL-CODE" not in response.text
    assert "provider_code" not in response.text


def test_get_diagnosis_carries_the_same_specific_code_as_the_post_failure() -> None:
    """The GET /v1/executions/{id} path uses the SAME mapping — a client
    diagnosing later must not see a different (or leakier) category."""
    world = World(script=[_provider_error(ProviderErrorCategory.QUOTA_EXCEEDED)])
    app = world.app()
    post_body = run(_post(app, {"ask": "hi"})).json()
    execution_id = post_body["error"]["details"]["execution_id"]
    response = run(_get(app, f"/v1/executions/{execution_id}"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "entitlement_exceeded"
    assert body["error"]["code"] == post_body["error"]["code"]
    assert "RAW-INTERNAL-CODE" not in response.text


# --- 2+3. adapter failure containment at the API boundary -----------------------------


class _RaisingAdapter(FakeAdapter):
    """Adapter that RAISES from generate() — the 30 §8.1 forbidden move.

    The exception text carries a secret-shaped token and vendor internals;
    NONE of it may reach the client (only normalize_error's safe output)."""

    async def generate(
        self, request: ProviderGenerateRequest
    ) -> ProviderGenerateResponse:
        self.requests.append(request)
        msg = "VENDOR-STACK-INTERNAL sk-live_abcdefghij0123456789 exploded"
        raise RuntimeError(msg)


class _BreachingAdapter(FakeAdapter):
    """Adapter that returns succeeded=False WITHOUT a normalized error —
    a contract breach the service must normalize, not propagate."""

    async def generate(
        self, request: ProviderGenerateRequest
    ) -> ProviderGenerateResponse:
        self.requests.append(request)
        return ProviderGenerateResponse(
            request_id=request.request_id, succeeded=False, error=None, latency_ms=3
        )


def test_raising_adapter_yields_normalized_error_never_a_stack_trace() -> None:
    world = World()
    world.adapter = _RaisingAdapter()
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 502  # normalized non_retryable_error path
    _assert_unified_error(response.json(), "execution_failed")
    # Containment: no exception text, no traceback, no secret-shaped token.
    assert "VENDOR-STACK-INTERNAL" not in response.text
    assert "sk-live_" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text


def test_raising_adapter_settles_the_usage_reservation() -> None:
    """The reservation taken before provider work must be RESOLVED when the
    adapter blows up — no leaked holds on the raising path (at API level)."""
    world = World()
    world.adapter = _RaisingAdapter()
    accounting = world.grant_budget(5.0)
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 502
    summary = accounting.summary(world.principal.tenant_id)
    assert summary.task_units.remaining == 5.0  # hold released, nothing settled


def test_contract_breaching_adapter_is_normalized_not_a_500() -> None:
    world = World()
    world.adapter = _BreachingAdapter()
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 502
    _assert_unified_error(response.json(), "execution_failed")
    assert "Traceback" not in response.text


def test_repeated_failures_never_erode_the_budget() -> None:
    """Adversarial hold-leak probe: N consecutive provider failures must
    leave the tenant budget byte-identical to its starting value."""
    world = World(
        script=[
            _provider_error(ProviderErrorCategory.TIMEOUT),
            _provider_error(ProviderErrorCategory.RETRYABLE_SERVER_ERROR),
            _provider_error(ProviderErrorCategory.PROVIDER_UNAVAILABLE),
        ]
    )
    accounting = world.grant_budget(5.0)
    app = world.app()
    for _ in range(3):
        assert run(_post(app, {"ask": "hi"})).status_code >= 400
    summary = accounting.summary(world.principal.tenant_id)
    assert summary.task_units.remaining == 5.0


# --- 4. health conflation attacks (30 §11) ---------------------------------------------


def test_healthy_provider_signal_cannot_launder_failing_accounts() -> None:
    """An explicit HEALTHY provider-scope signal is NOT an override switch:
    account degradation evidence must still surface as DEGRADED."""
    health = aggregate_provider_health(
        _entry(),
        {
            "acc-1": AccountHealthCheckState.READY,
            "acc-2": AccountHealthCheckState.INVALID,
        },
        provider_signal=ProviderHealthState.HEALTHY,
    )
    assert health.state is ProviderHealthState.DEGRADED


def test_template_rule_beats_every_other_input() -> None:
    """Templates cannot pass health checks (31 §10) — not even with all
    accounts READY and an explicit HEALTHY signal stacked in their favor."""
    health = aggregate_provider_health(
        _entry(_template_manifest()),
        {"acc-1": AccountHealthCheckState.READY},
        provider_signal=ProviderHealthState.HEALTHY,
    )
    assert health.state is ProviderHealthState.UNAVAILABLE


def test_account_states_cross_the_report_verbatim_no_laundering() -> None:
    """The per-account evidence must survive aggregation untouched — a
    consumer must be able to see WHICH account failed and HOW."""
    states = {
        "acc-ready": AccountHealthCheckState.READY,
        "acc-cooldown": AccountHealthCheckState.COOLDOWN,
        "acc-expired": AccountHealthCheckState.AUTH_EXPIRED,
        "acc-invalid": AccountHealthCheckState.INVALID,
    }
    health = aggregate_provider_health(_entry(), states)
    assert health.state is ProviderHealthState.DEGRADED
    assert health.accounts == states  # verbatim, all four states preserved


def test_adverse_signal_with_failing_accounts_reports_the_signal_state() -> None:
    """When both scopes carry evidence, the provider-scope signal wins and
    the account evidence still rides along in the report."""
    health = aggregate_provider_health(
        _entry(),
        {"acc-1": AccountHealthCheckState.INVALID},
        provider_signal=ProviderHealthState.UNAVAILABLE,
    )
    assert health.state is ProviderHealthState.UNAVAILABLE
    assert health.accounts["acc-1"] is AccountHealthCheckState.INVALID


# --- 5. rate-limit honesty at the API surface (30 §12) ---------------------------------


def test_unknown_rate_limit_state_is_never_available() -> None:
    """30 §12: unknown is a first-class honest state — structurally distinct
    from available. No consumer may collapse the two (documented guarantee;
    the closed 4-value set is asserted in the contract suite)."""
    assert RateLimitState.UNKNOWN is not RateLimitState.AVAILABLE
    assert RateLimitState.UNKNOWN.value != RateLimitState.AVAILABLE.value


def test_retryable_rate_limited_crosses_with_retryable_true_and_429() -> None:
    """The client-facing envelope must carry the retryability signal for
    rate limits so callers can back off honestly."""
    world = World(
        script=[
            _provider_error(ProviderErrorCategory.RATE_LIMITED, retryable=True)
        ]
    )
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 429
    payload = response.json()
    _assert_unified_error(payload, "rate_limited")
    assert payload["error"]["retryable"] is True


def test_nonretryable_rate_limited_crosses_with_retryable_false() -> None:
    world = World(
        script=[
            _provider_error(ProviderErrorCategory.RATE_LIMITED, retryable=False)
        ]
    )
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 429
    assert response.json()["error"]["retryable"] is False


# --- 6. router behavior under ineligible providers (existing surface) ------------------


def _world_with_manifest_swapped_to_template() -> World:
    """World whose only provider is re-registered as a template/non-functional
    manifest — the provider exists but must be invisible to routing."""
    world = World()
    template = _template_manifest()
    swapped = ProviderRegistry()
    swapped.register(world.provider, template)
    world.providers = swapped
    return world


def test_template_provider_is_unroutable_and_surfaces_explainable_503() -> None:
    world = _world_with_manifest_swapped_to_template()
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 503
    payload = response.json()
    _assert_unified_error(payload, "model_unavailable")
    # 11 §14 "fail clearly": the exclusion is explainable, not silent.
    assert payload["error"]["details"]


def test_status_disabled_provider_is_unroutable() -> None:
    """A provider with domain status=disabled must be excluded from routing
    even with a perfectly functional manifest (registry admission rule
    surfaced through the API, not re-implemented)."""
    world = World()
    disabled = Provider(
        id=uuid4(),
        provider_key="prov_disabled",
        display_name="prov_disabled",
        status=ProviderStatus.DISABLED,
        auth_types=["api_key"],
        supports_account_pool=False,
    )
    swapped = ProviderRegistry()
    swapped.register(disabled, _manifest(id="prov_disabled"))
    world.providers = swapped
    world.provider = disabled
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 503
    _assert_unified_error(response.json(), "model_unavailable")


def test_no_provider_work_happens_when_routing_excludes_everything() -> None:
    """Fail-before-spend: an unroutable request must never reach an adapter
    and must never touch the tenant budget."""
    world = _world_with_manifest_swapped_to_template()
    accounting = world.grant_budget(5.0)
    response = run(_post(world.app(), {"ask": "hi"}))
    assert response.status_code == 503
    assert world.adapter.requests == []  # adapter never called
    summary = accounting.summary(world.principal.tenant_id)
    assert summary.task_units.remaining == 5.0


# --- guard: fixtures imported for realism stay real -------------------------------------


def test_fixture_sanity_provider_helper_builds_active_provider() -> None:
    """Guard against fixture drift in the cross-module helpers this suite
    borrows (they are test code, but this suite depends on their meaning)."""
    provider = _provider("sanity")
    assert provider.status is ProviderStatus.ACTIVE
    entry = _entry()
    assert entry.is_routable
    health = aggregate_provider_health(entry, checked_at=datetime.now(tz=UTC))
    assert health.state is ProviderHealthState.HEALTHY
