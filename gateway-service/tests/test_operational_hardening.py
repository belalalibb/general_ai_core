"""G4 operational hardening — secret lifecycle, rotation drill, route-token
lifecycle, health semantics, failure containment, no-leak. ALL hermetic.

Nothing here invents new architecture: every test pins behavior of the
already-accepted contract (ADR-0008, CONTRACT.md, wire examples H/I) under
rotation, revocation, lifecycle changes and controlled failures.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import build_app
from gateway.auth import AuthOutcome, auth_error_body, authenticate
from gateway.config import GatewayConfig, load_config_from_env
from gateway.provider_registry import ProviderRegistry
from gateway.route_registry import RouteRegistry
from providers._example.definition import DEFINITION as EXAMPLE_DEFINITION
from tests.conftest import (
    EXAMPLE_SLUG,
    ROUTE_TOKEN,
    SECRET_V7,
    auth_headers,
    routed_headers,
    valid_envelope,
)

# Test-only sentinels — never real credentials.
NEW_SECRET_V8 = "unit-test-secret-version-eight!"
SECOND_TOKEN = "rtk_unit_test_second_opaque_token"

WINDOW_S = 600
T0 = 1_000_000.0  # deterministic rotation start (epoch seconds)


def _rotating_config(
    *,
    rotation_started_at: float | None = T0,
    window: int = WINDOW_S,
) -> GatewayConfig:
    """Post-rotation config: v8 current, v7 previous inside the window."""
    return GatewayConfig(
        secrets_by_version={8: NEW_SECRET_V8, 7: SECRET_V7},
        current_secret_version=8,
        route_map={ROUTE_TOKEN: EXAMPLE_SLUG},
        dual_accept_window_seconds=window,
        rotation_started_at=rotation_started_at,
    )


def _providers() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        slug=EXAMPLE_SLUG,
        raw_definition=dict(EXAMPLE_DEFINITION),
        facade_module="providers._example.adapter",
    )
    return registry


# --------------------------------------------------------------------------- #
# 1. Secret lifecycle (window ENFORCEMENT — the G4 hardening)                  #
# --------------------------------------------------------------------------- #


class TestSecretLifecycle:
    def test_current_secret_accepted_at_any_time(self) -> None:
        config = _rotating_config()
        for now in (T0, T0 + WINDOW_S - 1, T0 + WINDOW_S, T0 + 10 * WINDOW_S):
            result = authenticate(config, NEW_SECRET_V8, "8", clock=lambda n=now: n)
            assert result.outcome is AuthOutcome.OK

    def test_previous_secret_accepted_only_inside_window(self) -> None:
        config = _rotating_config()
        inside = authenticate(config, SECRET_V7, "7", clock=lambda: T0 + WINDOW_S - 1)
        assert inside.outcome is AuthOutcome.OK

    def test_previous_secret_rejected_at_and_after_window_boundary(self) -> None:
        config = _rotating_config()
        for now in (T0 + WINDOW_S, T0 + WINDOW_S + 1, T0 + 10 * WINDOW_S):
            result = authenticate(config, SECRET_V7, "7", clock=lambda n=now: n)
            assert result.outcome is AuthOutcome.STALE_VERSION
            body = auth_error_body(result)
            assert body["error"]["category"] == "auth_expired"  # type: ignore[index]
            assert body["error"]["retryable"] is True  # type: ignore[index]

    def test_expired_version_rejected_even_with_correct_value(self) -> None:
        """Expiry is about the VERSION's lifecycle, not the value: a correct
        old value after the window is auth_expired, never OK."""
        config = _rotating_config()
        result = authenticate(config, SECRET_V7, "7", clock=lambda: T0 + WINDOW_S)
        assert result.outcome is AuthOutcome.STALE_VERSION

    def test_wrong_value_on_current_version_is_invalid_credential(self) -> None:
        config = _rotating_config()
        result = authenticate(config, "wrong-value-entirely!", "8", clock=lambda: T0)
        assert result.outcome is AuthOutcome.WRONG_SECRET
        body = auth_error_body(result)
        assert body["error"]["category"] == "invalid_credential"  # type: ignore[index]
        assert body["error"]["retryable"] is False  # type: ignore[index]

    def test_unknown_version_stays_stale_semantics(self) -> None:
        config = _rotating_config()
        result = authenticate(config, NEW_SECRET_V8, "5", clock=lambda: T0)
        assert result.outcome is AuthOutcome.STALE_VERSION

    def test_no_rotation_tracking_keeps_pre_g4_behavior(self) -> None:
        """rotation_started_at unset => previous version accepted while
        configured (honest: no fabricated expiry without a start time)."""
        config = _rotating_config(rotation_started_at=None)
        result = authenticate(config, SECRET_V7, "7", clock=lambda: T0 + 10 * WINDOW_S)
        assert result.outcome is AuthOutcome.OK

    def test_constant_time_comparison_is_used(self) -> None:
        """The value compare goes through hmac.compare_digest — pinned by
        source inspection (a timing regression would change the callsite)."""
        import inspect

        import gateway.auth as auth_module

        source = inspect.getsource(auth_module.authenticate)
        assert "hmac.compare_digest" in source
        assert "== expected" not in source  # no plain equality on secrets

    def test_zero_window_expires_previous_immediately(self) -> None:
        config = _rotating_config(window=0)
        result = authenticate(config, SECRET_V7, "7", clock=lambda: T0)
        assert result.outcome is AuthOutcome.STALE_VERSION


# --------------------------------------------------------------------------- #
# 2. Rotation drill — old -> dual-accept -> new current -> old expires         #
# --------------------------------------------------------------------------- #


class TestRotationDrill:
    def test_full_rotation_drill_deterministic(self) -> None:
        """The complete OPEN-7 lifecycle as one deterministic sequence."""
        # Phase 0 — before rotation: v7 is current and the only secret.
        before = GatewayConfig(
            secrets_by_version={7: SECRET_V7},
            current_secret_version=7,
        )
        assert authenticate(before, SECRET_V7, "7").outcome is AuthOutcome.OK

        # Phase 1 — rotation begins at T0: v8 becomes current, v7 kept as
        # previous; BOTH accepted inside the window (dual-accept).
        during = _rotating_config(rotation_started_at=T0)
        t_in = T0 + 1
        assert (
            authenticate(during, NEW_SECRET_V8, "8", clock=lambda: t_in).outcome
            is AuthOutcome.OK
        )
        assert (
            authenticate(during, SECRET_V7, "7", clock=lambda: t_in).outcome
            is AuthOutcome.OK
        )

        # Phase 2 — window elapses: v8 still OK; v7 expires as auth_expired
        # (retryable — the adapter self-heals by re-reading the secret).
        t_out = T0 + WINDOW_S
        assert (
            authenticate(during, NEW_SECRET_V8, "8", clock=lambda: t_out).outcome
            is AuthOutcome.OK
        )
        expired = authenticate(during, SECRET_V7, "7", clock=lambda: t_out)
        assert expired.outcome is AuthOutcome.STALE_VERSION
        assert auth_error_body(expired)["error"]["category"] == "auth_expired"  # type: ignore[index]

        # Phase 3 — rotation completed: v7 removed from the map entirely.
        after = GatewayConfig(
            secrets_by_version={8: NEW_SECRET_V8},
            current_secret_version=8,
            route_map={ROUTE_TOKEN: EXAMPLE_SLUG},
        )
        assert authenticate(after, NEW_SECRET_V8, "8").outcome is AuthOutcome.OK
        assert authenticate(after, SECRET_V7, "7").outcome is AuthOutcome.STALE_VERSION

    def test_drill_at_http_level_stale_body_advertises_current_version(self) -> None:
        """The 401 auth_expired body tells the adapter which version is
        current — the self-heal signal — without leaking any secret value."""
        config = _rotating_config(rotation_started_at=T0, window=0)
        client = TestClient(build_app(config, _providers()))
        headers = {
            "X-Gateway-Secret": SECRET_V7,
            "X-Gateway-Secret-Version": "7",
            "X-Route-Token": ROUTE_TOKEN,
        }
        response = client.post("/v1/execute", headers=headers, json=valid_envelope())
        assert response.status_code == 401
        body = response.json()
        assert body["error"]["category"] == "auth_expired"
        assert "current is 8" in body["error"]["message"]
        assert SECRET_V7 not in response.text
        assert NEW_SECRET_V8 not in response.text

    def test_env_loader_parses_rotation_started_at(self) -> None:
        config = load_config_from_env(
            {
                "GW_SECRET_CURRENT": NEW_SECRET_V8,
                "GW_SECRET_CURRENT_VERSION": "8",
                "GW_SECRET_PREVIOUS": SECRET_V7,
                "GW_SECRET_PREVIOUS_VERSION": "7",
                "GW_DUAL_ACCEPT_WINDOW_S": "600",
                "GW_ROTATION_STARTED_AT": str(T0),
            }
        )
        assert config.rotation_started_at == T0
        assert config.secrets_by_version == {8: NEW_SECRET_V8, 7: SECRET_V7}

    def test_env_loader_rejects_garbage_rotation_started_at(self) -> None:
        with pytest.raises(ValueError, match="GW_ROTATION_STARTED_AT"):
            load_config_from_env(
                {
                    "GW_SECRET_CURRENT": NEW_SECRET_V8,
                    "GW_SECRET_CURRENT_VERSION": "8",
                    "GW_ROTATION_STARTED_AT": "not-a-number",
                }
            )


# --------------------------------------------------------------------------- #
# 3. Route-token lifecycle at the HTTP boundary                                #
# --------------------------------------------------------------------------- #


class TestRouteTokenLifecycle:
    def _world(self) -> tuple[TestClient, RouteRegistry]:
        config = GatewayConfig(
            secrets_by_version={7: SECRET_V7},
            current_secret_version=7,
            route_map={ROUTE_TOKEN: EXAMPLE_SLUG},
        )
        routes = RouteRegistry(config.route_map)
        client = TestClient(build_app(config, _providers(), routes))
        return client, routes

    def test_token_accepted_from_header_only_never_query(self) -> None:
        """A token in the query string is IGNORED (OPEN-3): addressing
        exists only via X-Route-Token."""
        client, _ = self._world()
        response = client.post(
            f"/v1/execute?route_token={ROUTE_TOKEN}&token={ROUTE_TOKEN}",
            headers=auth_headers(),  # authenticated but NO route header
            json=valid_envelope(),
        )
        assert response.status_code == 404  # uniform unknown-route

    def test_revocation_fails_closed_instantly_no_restart(self) -> None:
        client, routes = self._world()
        ok = client.post("/v1/execute", headers=routed_headers(), json=valid_envelope())
        assert ok.status_code == 200
        routes.revoke(ROUTE_TOKEN)
        revoked = client.post(
            "/v1/execute", headers=routed_headers(), json=valid_envelope()
        )
        assert revoked.status_code == 404

    def test_unknown_revoked_and_disabled_are_indistinguishable(self) -> None:
        """Anti-enumeration: identical status AND identical body bytes."""
        client, routes = self._world()

        unknown_headers = auth_headers()
        unknown_headers["X-Route-Token"] = "rtk_never_existed"
        unknown = client.post(
            "/v1/execute", headers=unknown_headers, json=valid_envelope()
        )

        routes.set_disabled(EXAMPLE_SLUG, True)
        disabled = client.post(
            "/v1/execute", headers=routed_headers(), json=valid_envelope()
        )
        routes.set_disabled(EXAMPLE_SLUG, False)

        routes.revoke(ROUTE_TOKEN)
        revoked = client.post(
            "/v1/execute", headers=routed_headers(), json=valid_envelope()
        )

        assert unknown.status_code == disabled.status_code == revoked.status_code == 404
        assert unknown.content == disabled.content == revoked.content

    def test_token_rotation_does_not_mutate_provider_identity(self) -> None:
        """Swapping the token (revoke old + issue new -> same slug) leaves
        the provider — and its declared surface — byte-identical."""
        client, routes = self._world()
        before = client.get("/v1/describe", headers=routed_headers())
        assert before.status_code == 200

        routes.reload({SECOND_TOKEN: EXAMPLE_SLUG})  # rotation: new token, same slug

        old_headers = routed_headers()
        assert client.get("/v1/describe", headers=old_headers).status_code == 404

        new_headers = auth_headers()
        new_headers["X-Route-Token"] = SECOND_TOKEN
        after = client.get("/v1/describe", headers=new_headers)
        assert after.status_code == 200
        assert after.content == before.content  # identity unchanged

    def test_neither_token_nor_slug_in_any_lifecycle_response(self) -> None:
        client, routes = self._world()
        responses = [client.post("/v1/execute", headers=routed_headers(), json=valid_envelope())]
        routes.revoke(ROUTE_TOKEN)
        responses.append(
            client.post("/v1/execute", headers=routed_headers(), json=valid_envelope())
        )
        for response in responses:
            assert ROUTE_TOKEN not in response.text
            assert SECOND_TOKEN not in response.text
            assert EXAMPLE_SLUG not in response.text


# --------------------------------------------------------------------------- #
# 4. Health / readiness semantics                                              #
# --------------------------------------------------------------------------- #


class TestHealthSemantics:
    def test_liveness_is_distinct_from_provider_health(self) -> None:
        """/healthz answers without auth and without any provider/route
        context; /v1/health requires BOTH — they are different questions."""
        config = GatewayConfig(
            secrets_by_version={7: SECRET_V7},
            current_secret_version=7,
            route_map={ROUTE_TOKEN: EXAMPLE_SLUG},
        )
        client = TestClient(build_app(config, _providers()))

        liveness = client.get("/healthz")
        assert liveness.status_code == 200
        assert liveness.json() == {"status": "ok"}

        assert client.get("/v1/health").status_code == 401  # auth required
        assert client.get("/v1/health", headers=auth_headers()).status_code == 404

    def test_liveness_carries_no_versions_secrets_providers(self) -> None:
        config = GatewayConfig(
            secrets_by_version={7: SECRET_V7},
            current_secret_version=7,
            route_map={ROUTE_TOKEN: EXAMPLE_SLUG},
        )
        client = TestClient(build_app(config, _providers()))
        text = client.get("/healthz").text
        for sensitive in (SECRET_V7, ROUTE_TOKEN, EXAMPLE_SLUG, "7", "version"):
            assert sensitive not in text

    def test_unsupported_provider_health_is_unknown_never_fabricated(self, client) -> None:
        response = client.get("/v1/health", headers=routed_headers())
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "UNKNOWN"  # honest: health_supported=false
        assert body["checked_at"] is None  # no fabricated timestamp

    def test_health_response_leaks_no_internal_details(self, client) -> None:
        text = client.get("/v1/health", headers=routed_headers()).text
        for sensitive in (EXAMPLE_SLUG, ROUTE_TOKEN, SECRET_V7, "mock", "upstream"):
            assert sensitive not in text


# --------------------------------------------------------------------------- #
# 5. Config no-leak (G4 leakage fix regression)                                #
# --------------------------------------------------------------------------- #


class TestConfigNoLeak:
    def test_config_repr_scrubs_secrets_and_tokens(self) -> None:
        config = _rotating_config()
        rendered = repr(config)
        assert NEW_SECRET_V8 not in rendered
        assert SECRET_V7 not in rendered
        assert ROUTE_TOKEN not in rendered
        assert EXAMPLE_SLUG not in rendered
        assert "[SCRUBBED]" in rendered

    def test_config_repr_keeps_operational_shape_facts(self) -> None:
        rendered = repr(_rotating_config())
        assert "current_secret_version=8" in rendered
        assert "route_count=1" in rendered

    def test_config_validation_errors_never_carry_values(self) -> None:
        try:
            GatewayConfig(secrets_by_version={1: "short"}, current_secret_version=1)
        except ValueError as exc:
            assert "short" not in str(exc)
        else:  # pragma: no cover — the config must reject this
            pytest.fail("short secret was accepted")
