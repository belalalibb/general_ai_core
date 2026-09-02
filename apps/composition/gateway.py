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
