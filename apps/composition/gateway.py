"""Remote Provider Gateway composition wiring (G2; ADR-0008 binding at the root).

Environment contract (deployment surface — Lane C), same posture as
``apps/composition/secrets.py``:

- ``GATEWAY_BASE_URL``        — REQUIRED to enable the binding. The gateway
  data-plane URL. MUST be https:// (ADR-0008 OPEN-4: private network + TLS;
  threat model row 1 — the platform never speaks plaintext to the gateway).
  A plaintext exception exists ONLY for explicit loopback development
  (http://localhost / http://127.0.0.1), never for production hosts.
- ``GATEWAY_SECRET``          — REQUIRED. Current shared-secret value.
  Handed to the adapter's resolver and NEVER logged (20 §5).
- ``GATEWAY_SECRET_VERSION``  — REQUIRED. Integer version of that secret
  (OPEN-7 dual-accept rotation: the gateway accepts current + previous
  for the operational window; the platform always sends its current one).

"Not configured ⇒ absent": without GATEWAY_BASE_URL there is nothing to
bind and ``gateway_settings_from_env`` returns None — the platform simply
has no remote gateway providers (dev/test default). A half-configured
gateway (URL without secret/version, or a malformed version) is an ERROR,
never a silent guess (20 §5 — custody is all-or-nothing).

Per-provider registration (route tokens, manifests) is platform DATA
(admin/config, report §25) — deliberately NOT environment variables here.
This module provides :func:`build_gateway_adapter` so the registry wiring
constructs one adapter per registered remote provider from that data; the
route token reaches it as an injected resolver (e.g. bound to
``SecretManagerPort.resolve`` on a ``route_token_ref``), never inline.

Route-token CUSTODY seam (R174 F-3, evidence/r174/05_platform_link):

- ``GATEWAY_ROUTE_TOKENS`` — OPTIONAL. ``ref=token,ref2=token2``. Each pair
  is preloaded into the onboarding secret manager under the platform tenant
  at composition time, so an operator's ``route_token_ref`` on
  ``POST /v1/admin/providers/onboard`` can actually resolve. This mirrors
  how real-provider env keys reach their manager (``runtime.py``
  ``_bind_real_providers``: env → ``secrets.store`` → opaque ref). Before
  this seam nothing ever stored a route token, so every gateway onboarding
  died with an uncaught ``SecretNotFound`` (HTTP 500) before any request
  reached the gateway. Values never appear in reprs, errors, or logs.
  Setting it WITHOUT ``GATEWAY_BASE_URL`` is half-configuration ⇒ error.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import httpx

from core.contracts.provider import ProviderManifest
from core.secrets import SecretManagerPort
from providers.real.gateway import GatewaySecret, RemoteGatewayAdapter

_ENV_BASE_URL = "GATEWAY_BASE_URL"
_ENV_SECRET = "GATEWAY_SECRET"  # noqa: S105 - env var NAME, not a credential
_ENV_SECRET_VERSION = "GATEWAY_SECRET_VERSION"  # noqa: S105 - env var NAME
_ENV_ROUTE_TOKENS = "GATEWAY_ROUTE_TOKENS"  # noqa: S105 - env var NAME

#: Loopback origins allowed to use plaintext http (dev only; OPEN-4).
_LOOPBACK_PREFIXES = ("http://localhost", "http://127.0.0.1")


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    """Validated gateway deployment settings (no secrets in repr)."""

    base_url: str
    secret: str
    secret_version: int

    def __repr__(self) -> str:  # 20 §5: the secret never appears in repr/logs
        return (
            f"GatewaySettings(base_url={self.base_url!r}, "
            f"secret_version={self.secret_version}, secret='[SCRUBBED]')"
        )


def gateway_settings_from_env(
    environ: dict[str, str] | None = None,
) -> GatewaySettings | None:
    """Read settings from the environment; None when not configured.

    ``environ`` is injectable for hermetic tests; production callers pass
    nothing and get ``os.environ``.
    """
    env = os.environ if environ is None else environ
    base_url = env.get(_ENV_BASE_URL, "").strip()
    if not base_url:
        return None  # not configured ⇒ binding absent (recorded posture)

    _validate_base_url(base_url)

    secret = env.get(_ENV_SECRET, "").strip()
    version_raw = env.get(_ENV_SECRET_VERSION, "").strip()
    if not secret or not version_raw:
        raise ValueError(
            "Gateway misconfigured: GATEWAY_BASE_URL is set but GATEWAY_SECRET "
            "and/or GATEWAY_SECRET_VERSION is missing — a half-configured "
            "gateway binding must never fall back silently (20 §5)."
        )
    if not version_raw.isdigit() or int(version_raw) < 1:
        raise ValueError(
            "Gateway misconfigured: GATEWAY_SECRET_VERSION must be a positive "
            f"integer, got {version_raw!r}."
        )

    return GatewaySettings(
        base_url=base_url.rstrip("/"),
        secret=secret,
        secret_version=int(version_raw),
    )


def _validate_base_url(base_url: str) -> None:
    """OPEN-4 / threat model row 1: TLS to the gateway, always.

    https:// is required; plaintext http:// is tolerated ONLY for explicit
    loopback development origins. Anything else is a loud error.
    """
    if base_url.startswith("https://"):
        return
    if any(
        base_url == prefix or base_url.startswith(prefix + ":") or base_url.startswith(prefix + "/")
        for prefix in _LOOPBACK_PREFIXES
    ):
        return
    raise ValueError(
        "Gateway misconfigured: GATEWAY_BASE_URL must use https:// "
        "(ADR-0008 OPEN-4 — TLS to the gateway; plaintext is allowed only "
        f"for loopback development), got {base_url!r}."
    )


def gateway_secret_resolver_from_secret_manager(
    secrets: SecretManagerPort,
    *,
    tenant_id: UUID,
    secret_ref: str,
    version_ref: str,
) -> Callable[[], GatewaySecret]:
    """Bind the gateway shared secret to the SecretManagerPort seam (G4 §2).

    The adapter re-reads the secret PER ATTEMPT via this resolver, so a
    rotation performed in the secret manager (store new value+version under
    the same refs' replacement, then rebind) is picked up by the OPEN-7
    self-heal retry with no restart and no code change. Rules preserved:

    - resolution happens at the LAST moment (20 §5) — nothing is cached here;
    - only opaque refs are held; the value never lands in any attribute;
    - a malformed stored version fails LOUD (never a silent guess);
    - no vendor path/token appears here — the port hides the backend.
    """

    def _resolve() -> GatewaySecret:
        value = secrets.resolve(tenant_id, secret_ref)
        version_raw = secrets.resolve(tenant_id, version_ref).strip()
        if not version_raw.isdigit() or int(version_raw) < 1:
            msg = (
                "Gateway secret version stored in the secret manager must be "
                "a positive integer (20 §5: custody is all-or-nothing)."
            )
            raise ValueError(msg)
        return GatewaySecret(value=value, version=int(version_raw))

    return _resolve


def route_token_resolver_from_secret_manager(
    secrets: SecretManagerPort,
    *,
    tenant_id: UUID,
    route_token_ref: str,
) -> Callable[[], str]:
    """Bind one provider's opaque route token to the SecretManagerPort seam.

    Same last-moment posture: the token is re-read per attempt, so token
    rotation (revoke old line + store new token under a new ref + rebind)
    needs no process restart. The token is a CREDENTIAL (5-layer identity)
    and gets full custody treatment — it never appears in settings, repr,
    or environment dumps.
    """

    def _resolve() -> str:
        return secrets.resolve(tenant_id, route_token_ref)

    return _resolve


def build_gateway_adapter(
    settings: GatewaySettings,
    *,
    manifest: ProviderManifest,
    route_token_resolver: Callable[[], str],
    credential_mode: str,
    user_key_resolver: Callable[[str], str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    gateway_secret_resolver: Callable[[], GatewaySecret] | None = None,
) -> RemoteGatewayAdapter:
    """Construct ONE remote-provider adapter from validated settings.

    Called once per platform-registered remote provider (report §25: the
    registration record supplies ``manifest`` — provider_key/display_name/
    declared surface — and the ``route_token_resolver`` bound to that
    provider's ``route_token_ref``). The gateway secret resolver re-reads
    the settings snapshot per attempt; when secret delivery moves to the
    secret manager, only this binding changes — the adapter is oblivious.

    ``transport`` is injectable for hermetic tests (httpx.MockTransport);
    production callers pass nothing and get the real transport.

    ``gateway_secret_resolver`` (G4 §2): when provided — e.g. built by
    :func:`gateway_secret_resolver_from_secret_manager` — it OVERRIDES the
    env-settings snapshot, moving secret custody to the SecretManagerPort
    seam without the adapter noticing. Default keeps the G2 env binding.
    """

    def _gateway_secret() -> GatewaySecret:
        return GatewaySecret(value=settings.secret, version=settings.secret_version)

    return RemoteGatewayAdapter(
        manifest,
        base_url=settings.base_url,
        gateway_secret_resolver=gateway_secret_resolver or _gateway_secret,
        route_token_resolver=route_token_resolver,
        credential_mode=credential_mode,
        user_key_resolver=user_key_resolver,
        transport=transport,
    )


# --- R174 F-3: route-token custody seam -------------------------------------


def route_tokens_from_env(
    environ: dict[str, str] | None = None,
    *,
    gateway_configured: bool,
) -> dict[str, str]:
    """Parse ``GATEWAY_ROUTE_TOKENS`` (``ref=token,...``) into ``{ref: token}``.

    Absent/blank ⇒ ``{}`` (nothing preloaded — pre-R174 behaviour). Malformed
    entries, duplicate refs, or tokens set while the gateway itself is NOT
    configured are loud errors (20 §5: half-configuration never guesses).
    Error messages name the entry POSITION, never the token value.
    """
    env = os.environ if environ is None else environ
    raw = env.get(_ENV_ROUTE_TOKENS, "").strip()
    if not raw:
        return {}
    if not gateway_configured:
        raise ValueError(
            f"Gateway misconfigured: {_ENV_ROUTE_TOKENS} is set but "
            f"{_ENV_BASE_URL} is not — route tokens without a gateway are a "
            "half-configured binding (20 §5)."
        )
    tokens: dict[str, str] = {}
    for position, entry in enumerate(raw.split(","), start=1):
        entry = entry.strip()
        if not entry:
            continue  # tolerate trailing / doubled commas
        ref, sep, token = entry.partition("=")
        ref, token = ref.strip(), token.strip()
        if not sep or not ref or not token:
            raise ValueError(
                f"Gateway misconfigured: {_ENV_ROUTE_TOKENS} entry #{position} "
                "must be 'ref=token' with a non-empty ref and token."
            )
        if ref in tokens:
            raise ValueError(f"Gateway misconfigured: {_ENV_ROUTE_TOKENS} names ref {ref!r} twice.")
        tokens[ref] = token
    return tokens


class PreloadedSecrets:
    """``SecretManagerPort`` decorator: operator-named refs over an inner manager.

    ``preloaded`` refs resolve for ``tenant_id`` ONLY (20 §6 — a ref minted
    for one tenant never resolves for another). Everything else — including
    ``store`` (which still mints opaque ``credref_`` handles) — delegates to
    ``inner``. Revoking a preloaded ref is final. Values never appear in
    ``repr``.
    """

    def __init__(
        self,
        inner: SecretManagerPort,
        *,
        tenant_id: UUID,
        preloaded: dict[str, str],
    ) -> None:
        for ref, value in preloaded.items():
            if not ref or not value:
                raise ValueError("preloaded route tokens need a non-empty ref and value")
        self._inner = inner
        self._tenant_id = tenant_id
        self._preloaded = dict(preloaded)

    def store(self, tenant_id: UUID, secret_value: str) -> str:
        return self._inner.store(tenant_id, secret_value)

    def resolve(self, tenant_id: UUID, credential_ref: str) -> str:
        if tenant_id == self._tenant_id and credential_ref in self._preloaded:
            return self._preloaded[credential_ref]
        return self._inner.resolve(tenant_id, credential_ref)

    def revoke(self, tenant_id: UUID, credential_ref: str) -> None:
        if tenant_id == self._tenant_id and credential_ref in self._preloaded:
            del self._preloaded[credential_ref]
            return
        self._inner.revoke(tenant_id, credential_ref)

    def exists(self, tenant_id: UUID, credential_ref: str) -> bool:
        if tenant_id == self._tenant_id and credential_ref in self._preloaded:
            return True
        return self._inner.exists(tenant_id, credential_ref)

    def __repr__(self) -> str:  # 20 §5: refs counted, values never shown
        return f"<PreloadedSecrets preloaded_refs={len(self._preloaded)} inner={self._inner!r}>"


def onboarding_secrets_from_env(
    environ: dict[str, str] | None = None,
    *,
    tenant_id: UUID,
    gateway_configured: bool,
    inner: SecretManagerPort,
) -> SecretManagerPort:
    """Compose the onboarding secret manager with any env-preloaded route tokens.

    No ``GATEWAY_ROUTE_TOKENS`` ⇒ ``inner`` is returned UNCHANGED (byte-for-
    byte pre-R174 behaviour). Otherwise ``inner`` is wrapped so the operator's
    refs resolve for ``tenant_id``. The plaintext leaves this function only
    inside the manager — never in a return value, log, or repr.
    """
    tokens = route_tokens_from_env(environ, gateway_configured=gateway_configured)
    if not tokens:
        return inner
    return PreloadedSecrets(inner, tenant_id=tenant_id, preloaded=tokens)


__all__ = [
    "GatewaySettings",
    "PreloadedSecrets",
    "build_gateway_adapter",
    "gateway_secret_resolver_from_secret_manager",
    "gateway_settings_from_env",
    "onboarding_secrets_from_env",
    "route_token_resolver_from_secret_manager",
    "route_tokens_from_env",
]
