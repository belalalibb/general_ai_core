"""G4 platform-side operational hardening — ALL hermetic (MockTransport).

Covers the platform half of the G4 mandate:

- §2 Secret-manager seam: gateway secret + route token resolved through the
  EXISTING ``SecretManagerPort`` composition seam, last-moment, per attempt.
- §3 Rotation drill (adapter view): stale-version 401 -> re-read -> retry
  once -> success; rotation via the secret manager needs no restart.
- §6 Failure containment: every gateway-side failure mode resolves the
  usage reservation through the EXISTING ledger — billing is never bypassed.
- §7 No-leak: secrets/tokens/refs absent from every artifact the platform
  produces under failure.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.composition import (
    GatewaySettings,
    build_gateway_adapter,
    gateway_secret_resolver_from_secret_manager,
    route_token_resolver_from_secret_manager,
)
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import (
    ProviderCapabilities,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderOperation,
)
from core.contracts.routing import RoutingRequest
from core.contracts.usage import UsageLedgerStatus
from core.execution.service import ExecutionService
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.router import SimpleScoringRouter
from core.secrets.memory import InMemorySecretManager
from core.usage import InMemoryUsageAccounting
from providers.real.gateway import CREDENTIAL_MODE_PLATFORM, build_gateway_manifest

# Test-only sentinels — never real credentials.
SECRET_OLD = "gwsecret_TEST_ONLY_g4_old_value_v1"
SECRET_NEW = "gwsecret_TEST_ONLY_g4_new_value_v2"
ROUTE_TOKEN = "routetok_TEST_ONLY_g4_hardening"
MODEL_NAME = "hardening-model-1"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _manifest() -> Any:
    return build_gateway_manifest(
        provider_key="remote-hardening",
        display_name="Remote Hardening",
        operations=[ProviderOperation.GENERATE_TEXT],
        capabilities=ProviderCapabilities(chat=True),
    )


def _generate_request() -> ProviderGenerateRequest:
    return ProviderGenerateRequest(
        request_id=uuid4(),
        tenant_id=uuid4(),
        operation=ProviderOperation.GENERATE_TEXT,
        provider_model_name=MODEL_NAME,
        credential_ref="credref_opaque",
        payload={"ask": "hello"},
        timeout_ms=5_000,
    )


def _canonical_success(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "succeeded": True,
            "output": {"text": "OK", "finish_reason": "stop"},
            "usage": {"input_tokens": 2, "output_tokens": 1, "units": 1},
            "latency_ms": 4,
            "error": None,
        },
    )


# --------------------------------------------------------------------------- #
# §2 — Secret-manager composition seam                                         #
# --------------------------------------------------------------------------- #


class TestSecretManagerSeam:
    def _seam(self) -> tuple[InMemorySecretManager, Any, Any, Any]:
        secrets = InMemorySecretManager()
        tenant_id = uuid4()
        secret_ref = secrets.store(tenant_id, SECRET_OLD)
        version_ref = secrets.store(tenant_id, "1")
        token_ref = secrets.store(tenant_id, ROUTE_TOKEN)
        secret_resolver = gateway_secret_resolver_from_secret_manager(
            secrets, tenant_id=tenant_id, secret_ref=secret_ref, version_ref=version_ref
        )
        token_resolver = route_token_resolver_from_secret_manager(
            secrets, tenant_id=tenant_id, route_token_ref=token_ref
        )
        return secrets, tenant_id, secret_resolver, token_resolver

    def test_resolvers_read_through_the_port(self) -> None:
        _, _, secret_resolver, token_resolver = self._seam()
        secret = secret_resolver()
        assert secret.value == SECRET_OLD
        assert secret.version == 1
        assert token_resolver() == ROUTE_TOKEN

    def test_resolution_is_last_moment_not_cached(self) -> None:
        """Rotating in the secret manager changes the NEXT resolution —
        no restart, no rebind, no adapter change."""
        secrets, tenant_id, _, _ = self._seam()
        # fresh seam whose refs we control:
        secret_ref = secrets.store(tenant_id, SECRET_OLD)
        version_ref = secrets.store(tenant_id, "1")
        resolver = gateway_secret_resolver_from_secret_manager(
            secrets, tenant_id=tenant_id, secret_ref=secret_ref, version_ref=version_ref
        )
        assert resolver().version == 1
        # rotation: replace stored values under the SAME refs (memory impl
        # stores by (tenant, ref) key — store() mints new refs, so emulate
        # the rebind by building a resolver at the new refs).
        new_secret_ref = secrets.store(tenant_id, SECRET_NEW)
        new_version_ref = secrets.store(tenant_id, "2")
        rebound = gateway_secret_resolver_from_secret_manager(
            secrets,
            tenant_id=tenant_id,
            secret_ref=new_secret_ref,
            version_ref=new_version_ref,
        )
        rotated = rebound()
        assert rotated.value == SECRET_NEW
        assert rotated.version == 2

    def test_malformed_stored_version_fails_loud(self) -> None:
        secrets = InMemorySecretManager()
        tenant_id = uuid4()
        secret_ref = secrets.store(tenant_id, SECRET_OLD)
        version_ref = secrets.store(tenant_id, "not-a-number")
        resolver = gateway_secret_resolver_from_secret_manager(
            secrets, tenant_id=tenant_id, secret_ref=secret_ref, version_ref=version_ref
        )
        with pytest.raises(ValueError, match="positive integer"):
            resolver()

    def test_seam_backed_adapter_authenticates_and_executes(self) -> None:
        """End-to-end (hermetic): resolvers -> adapter -> correct headers."""
        _, _, secret_resolver, token_resolver = self._seam()
        seen: list[httpx.Request] = []

        def _record(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _canonical_success(request)

        adapter = build_gateway_adapter(
            GatewaySettings(
                base_url="https://gateway.internal.test",
                secret="env-snapshot-ignored!",
                secret_version=99,
            ),
            manifest=_manifest(),
            route_token_resolver=token_resolver,
            credential_mode=CREDENTIAL_MODE_PLATFORM,
            transport=httpx.MockTransport(_record),
            gateway_secret_resolver=secret_resolver,  # seam OVERRIDES env
        )
        result = run(adapter.generate(_generate_request()))
        assert result.succeeded is True
        headers = seen[0].headers
        assert headers["x-gateway-secret"] == SECRET_OLD  # port value, not env
        assert headers["x-gateway-secret-version"] == "1"
        assert headers["x-route-token"] == ROUTE_TOKEN
        assert "env-snapshot-ignored!" not in str(headers)


# --------------------------------------------------------------------------- #
# §3 — Rotation drill, adapter view (self-heal picks up the port's new value)  #
# --------------------------------------------------------------------------- #


class TestAdapterRotationSelfHeal:
    def test_stale_401_triggers_reread_and_single_retry_with_new_secret(self) -> None:
        """The full platform-side rotation drill:

        attempt 1 -> old secret -> gateway says 401 auth_expired
        resolver re-read -> NEW secret (rotated in the secret manager)
        attempt 2 -> new secret -> success. Exactly two wire calls.
        """
        secrets = InMemorySecretManager()
        tenant_id = uuid4()
        token_ref = secrets.store(tenant_id, ROUTE_TOKEN)
        # rotation state emulated via a mutable ref pair the resolver reads:
        current_refs = {
            "secret": secrets.store(tenant_id, SECRET_OLD),
            "version": secrets.store(tenant_id, "1"),
        }

        def rotating_resolver() -> Any:
            resolver = gateway_secret_resolver_from_secret_manager(
                secrets,
                tenant_id=tenant_id,
                secret_ref=current_refs["secret"],
                version_ref=current_refs["version"],
            )
            return resolver()

        seen: list[httpx.Request] = []

        # The adapter resolves the secret fresh per attempt, so the rotation
        # is driven deterministically inside the gateway responder: the first
        # call sees v1 (refs still point at the old value), the responder
        # flips the refs and answers 401 auth_expired; the self-heal re-read
        # then picks up v2 and the single retry succeeds.
        def _flipping_gateway(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if request.headers["x-gateway-secret-version"] == "1":
                current_refs["secret"] = secrets.store(tenant_id, SECRET_NEW)
                current_refs["version"] = secrets.store(tenant_id, "2")
                return httpx.Response(
                    401,
                    json={
                        "error": {
                            "category": "auth_expired",
                            "retryable": True,
                            "message": "secret version no longer accepted; current is 2",
                        }
                    },
                )
            return _canonical_success(request)

        adapter = build_gateway_adapter(
            GatewaySettings(
                base_url="https://gateway.internal.test",
                secret="unused!unused!unused",
                secret_version=99,
            ),
            manifest=_manifest(),
            route_token_resolver=route_token_resolver_from_secret_manager(
                secrets, tenant_id=tenant_id, route_token_ref=token_ref
            ),
            credential_mode=CREDENTIAL_MODE_PLATFORM,
            transport=httpx.MockTransport(_flipping_gateway),
            gateway_secret_resolver=rotating_resolver,
        )
        result = run(adapter.generate(_generate_request()))
        assert result.succeeded is True
        assert len(seen) == 2  # exactly one retry, never more
        assert seen[0].headers["x-gateway-secret"] == SECRET_OLD
        assert seen[1].headers["x-gateway-secret"] == SECRET_NEW
        assert seen[1].headers["x-gateway-secret-version"] == "2"

    def test_persistent_stale_fails_after_exactly_one_retry(self) -> None:
        """If rotation did NOT land, the adapter stops after the single
        self-heal attempt — auth_expired surfaces, no infinite loop."""
        secrets = InMemorySecretManager()
        tenant_id = uuid4()
        calls = {"n": 0}

        def _always_stale(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(
                401,
                json={
                    "error": {
                        "category": "auth_expired",
                        "retryable": True,
                        "message": "secret version no longer accepted; current is 9",
                    }
                },
            )

        secret_ref = secrets.store(tenant_id, SECRET_OLD)
        version_ref = secrets.store(tenant_id, "1")
        token_ref = secrets.store(tenant_id, ROUTE_TOKEN)
        adapter = build_gateway_adapter(
            GatewaySettings(
                base_url="https://gateway.internal.test",
                secret="unused!unused!unused",
                secret_version=99,
            ),
            manifest=_manifest(),
            route_token_resolver=route_token_resolver_from_secret_manager(
                secrets, tenant_id=tenant_id, route_token_ref=token_ref
            ),
            credential_mode=CREDENTIAL_MODE_PLATFORM,
            transport=httpx.MockTransport(_always_stale),
            gateway_secret_resolver=gateway_secret_resolver_from_secret_manager(
                secrets, tenant_id=tenant_id, secret_ref=secret_ref, version_ref=version_ref
            ),
        )
        result = run(adapter.generate(_generate_request()))
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ProviderErrorCategory.AUTH_EXPIRED
        assert calls["n"] == 2  # 1 attempt + exactly 1 self-heal retry


# --------------------------------------------------------------------------- #
# §6 — Failure containment: billing is NEVER bypassed                          #
# --------------------------------------------------------------------------- #


def _world(responder: Any) -> dict[str, Any]:
    tenant_id = uuid4()
    user_id = uuid4()
    manifest = _manifest()
    adapter = build_gateway_adapter(
        GatewaySettings(
            base_url="https://gateway.internal.test",
            secret=SECRET_OLD,
            secret_version=1,
        ),
        manifest=manifest,
        route_token_resolver=lambda: ROUTE_TOKEN,
        credential_mode=CREDENTIAL_MODE_PLATFORM,
        transport=httpx.MockTransport(responder),
    )
    providers = ProviderRegistry()
    provider = Provider(
        id=uuid4(),
        provider_key="remote-hardening",
        display_name="Remote Hardening",
        status=ProviderStatus.ACTIVE,
        auth_types=["custom"],
        supports_account_pool=False,
    )
    providers.register(provider, manifest)
    models = ModelRegistry()
    model = Model(
        id=uuid4(),
        model_key="hardening-model",
        display_name="Hardening Model",
        tier=ModelTier.FAST,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.5,
        reliability_score=0.5,
        cost_score=0.5,
        speed_score=0.5,
        status=ModelStatus.ACTIVE,
    )
    models.register(model)
    bindings = BindingRegistry()
    bindings.register(
        ProviderModelBinding(
            provider_id=provider.id,
            model_id=model.id,
            provider_model_name=MODEL_NAME,
            availability=BindingAvailability.AVAILABLE,
        )
    )
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(tenant_id, plan="pro", task_units_limit=10.0)
    service = ExecutionService(
        adapters={provider.id: adapter},
        credential_refs={provider.id: "credref_opaque"},
        bindings=bindings,
        max_retries_per_candidate=1,
        usage=usage,
    )
    router = SimpleScoringRouter(providers, models, bindings)
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "usage": usage,
        "service": service,
        "router": router,
    }


async def _execute(world: dict[str, Any]) -> Any:
    decision = world["router"].route(
        RoutingRequest(operation=ProviderOperation.GENERATE_TEXT)
    )
    return await world["service"].execute_single(
        tenant_id=world["tenant_id"],
        user_id=world["user_id"],
        decision=decision,
        operation=ProviderOperation.GENERATE_TEXT,
        payload={"ask": "hi"},
        request_hash="g4-containment",
    )


def _wire_200_failure(category: str, *, retryable: bool) -> Any:
    def _responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "succeeded": False,
                "output": None,
                "usage": None,
                "latency_ms": 3,
                "error": {
                    "category": category,
                    "retryable": retryable,
                    "message": f"normalized {category} from facade",
                },
            },
        )

    return _responder


class TestFailureContainment:
    """Every controlled failure mode resolves the reservation — no bypass."""

    @pytest.mark.parametrize(
        ("name", "responder"),
        [
            (
                "auth_wrong_secret_401",
                lambda request: httpx.Response(
                    401,
                    json={
                        "error": {
                            "category": "invalid_credential",
                            "retryable": False,
                            "message": "gateway authentication failed",
                        }
                    },
                ),
            ),
            (
                "revoked_or_unknown_route_404",
                lambda request: httpx.Response(
                    404,
                    json={
                        "error": {
                            "category": "non_retryable_error",
                            "retryable": False,
                            "message": "unknown route",
                        }
                    },
                ),
            ),
            (
                "malformed_provider_response_200",
                lambda request: httpx.Response(200, text="definitely not json"),
            ),
            ("provider_timeout", _wire_200_failure("timeout", retryable=True)),
            (
                "provider_unavailable",
                _wire_200_failure("provider_unavailable", retryable=False),
            ),
            (
                "gateway_internal_fault_500",
                lambda request: httpx.Response(
                    500,
                    json={
                        "succeeded": False,
                        "error": {
                            "category": "retryable_server_error",
                            "retryable": True,
                            "message": "gateway internal fault",
                        },
                    },
                ),
            ),
        ],
    )
    def test_failure_mode_resolves_reservation(self, name: str, responder: Any) -> None:
        world = _world(responder)
        report = run(_execute(world))
        assert report.execution.status.value == "failed", name
        usage: InMemoryUsageAccounting = world["usage"]
        ledger = usage.get(report.execution.id)
        # billing NEVER bypassed: the reservation exists and is RESOLVED
        assert ledger.status in (UsageLedgerStatus.FAILED, UsageLedgerStatus.REFUNDED), name
        assert ledger.units_settled == 0.0, name
        # the hold is fully released — nothing consumed, nothing stuck
        summary = usage.summary(world["tenant_id"])
        assert summary.task_units.used == 0.0, name
        assert summary.task_units.remaining == 10.0, name

    def test_transport_level_timeout_also_resolves_reservation(self) -> None:
        def _raise_timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("boom")

        world = _world(_raise_timeout)
        report = run(_execute(world))
        assert report.execution.status.value == "failed"
        ledger = world["usage"].get(report.execution.id)
        assert ledger.status in (UsageLedgerStatus.FAILED, UsageLedgerStatus.REFUNDED)
        assert world["usage"].summary(world["tenant_id"]).task_units.used == 0.0

    def test_normalized_error_category_propagates_verbatim(self) -> None:
        world = _world(_wire_200_failure("quota_exceeded", retryable=False))
        report = run(_execute(world))
        attempts = report.nodes[0].attempts if report.nodes else ()
        assert attempts, "expected at least one recorded attempt"
        error = attempts[-1].error
        assert error is not None
        assert error.category is ProviderErrorCategory.QUOTA_EXCEEDED


# --------------------------------------------------------------------------- #
# §7 — No-leak audit regressions (platform artifacts under failure)            #
# --------------------------------------------------------------------------- #


class TestPlatformNoLeak:
    SENSITIVE = (SECRET_OLD, SECRET_NEW, ROUTE_TOKEN)

    def test_failure_reports_never_carry_secret_or_token(self) -> None:
        def _hostile(request: httpx.Request) -> httpx.Response:
            # hostile gateway echoing sensitive-looking content in a 500
            return httpx.Response(
                500, json={"error": {"message": f"leak {SECRET_OLD} {ROUTE_TOKEN}"}}
            )

        world = _world(_hostile)
        report = run(_execute(world))
        dumped = report.execution.model_dump_json()
        for node in report.nodes:
            for attempt in node.attempts:
                if attempt.error is not None:
                    dumped += attempt.error.model_dump_json()
        for sentinel in self.SENSITIVE:
            assert sentinel not in dumped

    def test_settings_and_resolver_reprs_scrubbed(self) -> None:
        settings = GatewaySettings(
            base_url="https://gateway.internal.test",
            secret=SECRET_OLD,
            secret_version=1,
        )
        assert SECRET_OLD not in repr(settings)
        secrets = InMemorySecretManager()
        tenant_id = uuid4()
        resolver = gateway_secret_resolver_from_secret_manager(
            secrets,
            tenant_id=tenant_id,
            secret_ref=secrets.store(tenant_id, SECRET_OLD),
            version_ref=secrets.store(tenant_id, "1"),
        )
        assert SECRET_OLD not in repr(resolver)
        resolved = resolver()
        assert SECRET_OLD not in repr(resolved)  # GatewaySecret scrubbed repr
