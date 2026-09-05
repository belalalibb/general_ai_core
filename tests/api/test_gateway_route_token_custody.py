"""R174 F-3 — route-token custody seam (``GATEWAY_ROUTE_TOKENS``) + 409 mapping.

Live finding (evidence/r174/05_platform_link, case E): the composition root
built a FRESH ``InMemorySecretManager`` for onboarding and nothing ever
stored a route token into it, so every ``POST /v1/admin/providers/onboard``
for a gateway provider died with an uncaught ``SecretNotFound`` → HTTP 500
"Internal error." before any request reached the gateway.

Pinned here:

- ``route_tokens_from_env`` parses ``ref=token,...``; absent ⇒ ``{}``;
  malformed / duplicate / gateway-not-configured ⇒ loud ValueError whose
  message never contains a token value (20 §5).
- ``onboarding_secrets_from_env`` returns the inner manager UNCHANGED when
  nothing is preloaded (pre-R174 behaviour), and a ``PreloadedSecrets``
  wrapper otherwise, under which the operator's ref resolves for the
  platform tenant ONLY (20 §6), ``store()`` still mints opaque refs, and
  the repr never shows a value.
- The onboarding route maps ``SecretNotFound`` raised during the walk to
  409 naming the ref — never a 500, never a value; nothing registered.
- The REAL composition root (``build_runtime_profile``) with
  ``GATEWAY_ROUTE_TOKENS`` set: the operator's ref resolves through the
  built adapter's resolver; the same ref WITHOUT the env var is a 409
  through the real admin door (the exact §5 case E, now honest).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from apps.api.app import Principal
from apps.api.provider_onboarding import (
    ProviderOnboardingSurface,
    create_provider_onboarding_router,
)
from apps.composition.gateway import (
    PreloadedSecrets,
    onboarding_secrets_from_env,
    route_tokens_from_env,
)
from apps.composition.provider_onboarding import PLATFORM_TENANT_ID, manifest_from_definition
from apps.composition.runtime import RuntimeProfile, build_runtime_profile
from core.contracts.provider import HealthScope, ProviderHealth
from core.providers import (
    BindingRegistry,
    ModelRegistry,
    ProviderOnboardingService,
    ProviderRegistry,
)
from core.providers.ports import ProviderAdapterPort
from core.secrets.errors import SecretNotFound
from core.secrets.memory import InMemorySecretManager
from tests.providers.test_onboarding_service import FakeAdapter, _manifest

TOKEN_A = "routetok_TEST_ONLY_alpha_value"  # noqa: S105 - test fixture
TOKEN_B = "routetok_TEST_ONLY_beta_value"  # noqa: S105 - test fixture
REF = "route-token-ref-alpha"
ADMIN = Principal(tenant_id=uuid4(), user_id=uuid4(), is_admin=True)
ADMIN_EMAIL = "custody-admin@example.test"
PASSWORD = "correct horse battery staple"  # noqa: S105 - test fixture


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


# --- env parsing -----------------------------------------------------------------


class TestRouteTokensFromEnv:
    def test_absent_or_blank_is_empty(self) -> None:
        assert route_tokens_from_env({}, gateway_configured=True) == {}
        assert route_tokens_from_env({"GATEWAY_ROUTE_TOKENS": "  "}, gateway_configured=True) == {}
        # Blank + no gateway is fine too (nothing configured at all).
        assert route_tokens_from_env({}, gateway_configured=False) == {}

    def test_pairs_parse_with_whitespace_and_stray_commas(self) -> None:
        env = {"GATEWAY_ROUTE_TOKENS": f" ref-a = {TOKEN_A} , ref-b={TOKEN_B},, "}
        assert route_tokens_from_env(env, gateway_configured=True) == {
            "ref-a": TOKEN_A,
            "ref-b": TOKEN_B,
        }

    @pytest.mark.parametrize("raw", ["noequals", "=tokvalue", "ref=", "ref-a=x,=tokvalue"])
    def test_malformed_is_loud_and_never_echoes_token(self, raw: str) -> None:
        with pytest.raises(ValueError, match="GATEWAY_ROUTE_TOKENS entry #") as exc:
            route_tokens_from_env({"GATEWAY_ROUTE_TOKENS": raw}, gateway_configured=True)
        assert "tokvalue" not in str(exc.value)

    def test_duplicate_ref_is_loud_and_never_echoes_tokens(self) -> None:
        env = {"GATEWAY_ROUTE_TOKENS": f"ref-a={TOKEN_A},ref-a={TOKEN_B}"}
        with pytest.raises(ValueError, match="twice") as exc:
            route_tokens_from_env(env, gateway_configured=True)
        assert TOKEN_A not in str(exc.value)
        assert TOKEN_B not in str(exc.value)

    def test_tokens_without_gateway_is_half_configuration(self) -> None:
        env = {"GATEWAY_ROUTE_TOKENS": f"ref-a={TOKEN_A}"}
        with pytest.raises(ValueError, match="GATEWAY_BASE_URL is not") as exc:
            route_tokens_from_env(env, gateway_configured=False)
        assert TOKEN_A not in str(exc.value)


# --- the decorator ----------------------------------------------------------------


class TestOnboardingSecretsFromEnv:
    def test_nothing_preloaded_returns_inner_unchanged(self) -> None:
        inner = InMemorySecretManager()
        out = onboarding_secrets_from_env(
            {}, tenant_id=PLATFORM_TENANT_ID, gateway_configured=True, inner=inner
        )
        assert out is inner

    def test_preloaded_ref_resolves_for_platform_tenant_only(self) -> None:
        inner = InMemorySecretManager()
        out = onboarding_secrets_from_env(
            {"GATEWAY_ROUTE_TOKENS": f"{REF}={TOKEN_A}"},
            tenant_id=PLATFORM_TENANT_ID,
            gateway_configured=True,
            inner=inner,
        )
        assert isinstance(out, PreloadedSecrets)
        assert out.resolve(PLATFORM_TENANT_ID, REF) == TOKEN_A
        assert out.exists(PLATFORM_TENANT_ID, REF)
        foreign = uuid4()
        assert not out.exists(foreign, REF)
        with pytest.raises(SecretNotFound):
            out.resolve(foreign, REF)

    def test_store_still_mints_opaque_refs_via_inner(self) -> None:
        inner = InMemorySecretManager()
        out = PreloadedSecrets(inner, tenant_id=PLATFORM_TENANT_ID, preloaded={REF: TOKEN_A})
        ref = out.store(PLATFORM_TENANT_ID, TOKEN_B)
        assert ref.startswith("credref_")
        assert out.resolve(PLATFORM_TENANT_ID, ref) == TOKEN_B
        assert inner.resolve(PLATFORM_TENANT_ID, ref) == TOKEN_B

    def test_unknown_ref_still_raises_secret_not_found(self) -> None:
        out = PreloadedSecrets(
            InMemorySecretManager(), tenant_id=PLATFORM_TENANT_ID, preloaded={REF: TOKEN_A}
        )
        with pytest.raises(SecretNotFound):
            out.resolve(PLATFORM_TENANT_ID, "never-provisioned")

    def test_revoke_preloaded_is_final(self) -> None:
        out = PreloadedSecrets(
            InMemorySecretManager(), tenant_id=PLATFORM_TENANT_ID, preloaded={REF: TOKEN_A}
        )
        out.revoke(PLATFORM_TENANT_ID, REF)
        assert not out.exists(PLATFORM_TENANT_ID, REF)
        with pytest.raises(SecretNotFound):
            out.resolve(PLATFORM_TENANT_ID, REF)
        with pytest.raises(SecretNotFound):
            out.revoke(PLATFORM_TENANT_ID, REF)

    def test_repr_never_shows_values(self) -> None:
        out = PreloadedSecrets(
            InMemorySecretManager(), tenant_id=PLATFORM_TENANT_ID, preloaded={REF: TOKEN_A}
        )
        assert TOKEN_A not in repr(out)
        assert TOKEN_A not in str(out)
        assert "preloaded_refs=1" in repr(out)

    def test_empty_ref_or_value_refused(self) -> None:
        with pytest.raises(ValueError):
            PreloadedSecrets(
                InMemorySecretManager(), tenant_id=PLATFORM_TENANT_ID, preloaded={"": "x"}
            )
        with pytest.raises(ValueError):
            PreloadedSecrets(
                InMemorySecretManager(), tenant_id=PLATFORM_TENANT_ID, preloaded={"r": ""}
            )


# --- route: SecretNotFound → 409 --------------------------------------------------


class _SecretNotFoundAdapter(FakeAdapter):
    """Mimics RemoteGatewayAdapter's first gateway call with an unresolvable ref."""

    def __init__(self, ref: str) -> None:
        super().__init__(manifest=_manifest(id="gw_alpha", name="Gateway Alpha"))
        self._ref = ref

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        raise SecretNotFound(self._ref)


def _route_app(adapter: ProviderAdapterPort) -> tuple[FastAPI, ProviderRegistry, list[object]]:
    providers = ProviderRegistry()
    persisted: list[object] = []
    service = ProviderOnboardingService(
        providers=providers,
        models=ModelRegistry(),
        bindings=BindingRegistry(),
        adapters={},
        credential_refs={},
    )
    surface = ProviderOnboardingSurface(
        onboarding=service,
        build_manifest=manifest_from_definition,
        build_adapter=lambda manifest, body: adapter,
        persist_registration=lambda pid, d: persisted.append((pid, d)),
    )

    def _resolve(request: Request) -> Principal | JSONResponse:
        return ADMIN

    app = FastAPI()
    app.include_router(create_provider_onboarding_router(surface, resolve=_resolve))
    return app, providers, persisted


def _body() -> dict[str, object]:
    return {
        "provider_key": "gw_alpha",
        "display_name": "Gateway Alpha",
        "operations": ["generate_text"],
        "capabilities": {},
        "credential_ref": "cred-ref-alpha",
        "route_token_ref": REF,
        "credential_mode": "platform",
    }


async def _post_onboard(app: FastAPI, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/admin/providers/onboard", json=_body(), headers=headers)


class TestRouteMapsSecretNotFoundTo409:
    def test_unresolvable_ref_is_409_naming_the_ref_not_500(self) -> None:
        app, providers, persisted = _route_app(_SecretNotFoundAdapter(REF))
        response = run(_post_onboard(app))
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert REF in error["message"]
        assert "GATEWAY_ROUTE_TOKENS" in error["message"]
        assert error["details"] == {"credential_ref": REF}
        # Walker refused before step 11 — no half-state, nothing persisted.
        assert providers.all_keys() == []
        assert persisted == []


# --- the REAL composition root ----------------------------------------------------


def _admin_session(profile: RuntimeProfile) -> dict[str, str]:
    identity = profile.identity
    assert identity is not None
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        identity.register(ADMIN_EMAIL, PASSWORD, "en")
    token = json.loads(stream.getvalue().strip().splitlines()[-1])["token"]
    identity.verify_email(token)
    return {"Authorization": f"Bearer {identity.login(ADMIN_EMAIL, PASSWORD).token}"}


_GATEWAY_ENV = {
    "GATEWAY_BASE_URL": "http://127.0.0.1:1",  # loopback; nothing listens — never reached here
    "GATEWAY_SECRET": "gwsecret_TEST_ONLY_value",
    "GATEWAY_SECRET_VERSION": "1",
    "ADMIN_EMAILS": ADMIN_EMAIL,
}


class TestRuntimeProfileCustody:
    def test_with_env_the_ref_resolves_and_the_walk_reaches_the_gateway(self) -> None:
        """Route token preloaded ⇒ the walker gets PAST custody and to step 6.

        Nothing listens on 127.0.0.1:1, so the adapter reports UNAVAILABLE and
        the walker refuses at the health step — a refusal that is only
        reachable if the route token RESOLVED (SecretNotFound would have
        fired inside the same request first). No gateway request needed.
        """
        profile = build_runtime_profile(
            {**_GATEWAY_ENV, "GATEWAY_ROUTE_TOKENS": f"{REF}={TOKEN_A}"}
        )
        response = run(_post_onboard(profile.app, headers=_admin_session(profile)))
        assert response.status_code == 409, response.text
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert "step-6" in error["message"], error["message"]
        assert error.get("details") in (None, {})
        assert TOKEN_A not in response.text
        assert "gw_alpha" not in profile.providers.all_keys()

    def test_tokens_without_gateway_refuse_at_composition(self) -> None:
        with pytest.raises(ValueError, match="GATEWAY_ROUTE_TOKENS is set but"):
            build_runtime_profile({"GATEWAY_ROUTE_TOKENS": f"{REF}={TOKEN_A}"})
