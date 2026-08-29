"""Remote Provider Gateway adapter (G2; ADR-0008 ACCEPTED 2026-08-29).

Implements ``ProviderAdapterPort`` (30 §8.1) UNMODIFIED against the Remote
Provider Gateway data plane (gateway-service/, G1 baseline): the platform
stays the control plane; the gateway executes and returns raw evidence.

Wire surface consumed (gateway-service/gateway/contracts.py, Layer 3):

- ``POST /v1/execute``  — unified endpoint (OPEN-1); operation rides the
  envelope, never the URL.
- ``GET /v1/models``    — declared model list (discovery projection).
- ``GET /v1/health``    — provider health; UNKNOWN is a legal answer.

Posture rules enforced here (ADR-0008 + 20 §5 + 30 §14):

- Route token travels in the ``X-Route-Token`` HEADER only — NEVER in a
  URL path or query string (OPEN-3). Enforced by construction: the token
  is only ever placed into the headers dict.
- Gateway secret + version resolve at the LAST moment, per attempt, via an
  injected resolver. On 401 ``auth_expired`` (stale version during the
  OPEN-7 dual-accept rotation window) the adapter re-reads the secret and
  retries EXACTLY ONCE — the contract's self-healing rotation. This is an
  AUTH retry before any upstream execution; upstream execution retries
  remain ZERO in v1 (billing integrity, ADR-0008 §usage).
- user_key (BYOK) mode: the platform resolves the opaque ``credential_ref``
  and the key crosses TLS inside the envelope's ``credential.value``
  (ADR-0008 credential model). platform mode: no value crosses; the
  gateway resolves internally by slug — the platform never learns which.
- Secrets / route token / user keys NEVER appear in any returned object,
  error message, provider_code, repr, or log. Failure messages are fixed
  strings; gateway response bodies are never echoed into ``safe_message``.
- ``generate`` rejects undeclared operations with ``unsupported_capability``
  and rejects the OPEN-2 v1-excluded operations the same way, with no
  network call in either case.
- Raw failures never cross the boundary: everything funnels through
  :meth:`RemoteGatewayAdapter.normalize_error` (30 §14).

Hermeticity: the HTTP transport is injectable (``httpx.AsyncBaseTransport``)
so contract tests run against ``httpx.MockTransport`` with zero network.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

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
    ProviderHealthState,
    ProviderManifest,
)

# --- Wire constants (platform-side mirror of gateway-service/gateway/contracts.py;
# --- tests/providers/test_gateway_adapter.py proves parity mechanically) ----------

HEADER_GATEWAY_SECRET = "X-Gateway-Secret"
HEADER_GATEWAY_SECRET_VERSION = "X-Gateway-Secret-Version"
HEADER_ROUTE_TOKEN = "X-Route-Token"  # header ALWAYS — never URL (OPEN-3)

EXECUTE_PATH = "/v1/execute"
MODELS_PATH = "/v1/models"
HEALTH_PATH = "/v1/health"

#: OPEN-2 (ADR-0008): platform operations that exist but are OUT of Gateway v1.
#: Mirror of the gateway's ``EXCLUDED_OPERATIONS``; parity is test-enforced.
EXCLUDED_OPERATIONS_V1: frozenset[str] = frozenset(
    {"run_provider_agent", "upload_asset", "download_asset"}
)

#: Credential modes of the wire contract (mirror of gateway ``CredentialMode``).
CREDENTIAL_MODE_USER_KEY = "user_key"
CREDENTIAL_MODE_PLATFORM = "platform"
_CREDENTIAL_MODES = frozenset({CREDENTIAL_MODE_USER_KEY, CREDENTIAL_MODE_PLATFORM})

#: Gateway wire bound for timeout_ms (RequestEnvelope: ge=1, le=600_000).
_TIMEOUT_MS_MIN = 1
_TIMEOUT_MS_MAX = 600_000

#: gateway /v1/health status -> platform ProviderHealthState (30 §11).
#: UNKNOWN maps conservatively to UNAVAILABLE — "Unknown = ineligible"
#: (11 §5): an unverifiable provider is never treated as healthy.
_HEALTH_STATUS_MAP: dict[str, ProviderHealthState] = {
    "OK": ProviderHealthState.HEALTHY,
    "DEGRADED": ProviderHealthState.DEGRADED,
    "DOWN": ProviderHealthState.UNAVAILABLE,
    "UNKNOWN": ProviderHealthState.UNAVAILABLE,
}


@dataclass(frozen=True, slots=True)
class GatewaySecret:
    """One resolved gateway shared-secret value with its rotation version.

    The value NEVER appears in repr/logs (20 §5 — reprs get logged).
    """

    value: str
    version: int

    def __repr__(self) -> str:
        return f"GatewaySecret(version={self.version}, value='[SCRUBBED]')"


class GatewayCredentialCheckUnsupported(RuntimeError):
    """Gateway v1 exposes NO credential-validation wire surface.

    ``validate_credential`` raises this instead of inventing a definite
    ACTIVE/INVALID answer it cannot know (41 §49 never-fake; same
    raise-not-guess posture as ``GroqCredentialCheckInconclusive``).
    In platform credential mode the upstream credential is gateway-internal
    and structurally invisible to the platform; in user_key mode v1 has no
    validation endpoint. Callers normalize via ``normalize_error``.
    """


class RemoteGatewayAdapter:
    """``ProviderAdapterPort`` implementation backed by a remote gateway route.

    One adapter instance represents ONE platform-registered remote provider
    (one route token). The 5-layer identity rule holds: this class sees the
    platform manifest and an opaque route token; it never sees or invents
    the gateway-internal slug.

    Injected resolvers (composition root binds them; 20 §5):

    - ``gateway_secret_resolver`` -> :class:`GatewaySecret`, called fresh
      per attempt so the auth_expired self-healing retry picks up rotation.
    - ``route_token_resolver``    -> the opaque route token (header only).
    - ``user_key_resolver``       -> trades the platform ``credential_ref``
      for the BYOK key (required iff ``credential_mode='user_key'``).
    """

    def __init__(
        self,
        manifest: ProviderManifest,
        *,
        base_url: str,
        gateway_secret_resolver: Callable[[], GatewaySecret],
        route_token_resolver: Callable[[], str],
        credential_mode: str,
        user_key_resolver: Callable[[str], str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        default_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        if credential_mode not in _CREDENTIAL_MODES:
            msg = (
                f"credential_mode must be one of {sorted(_CREDENTIAL_MODES)}, "
                f"got {credential_mode!r}"
            )
            raise ValueError(msg)
        if credential_mode == CREDENTIAL_MODE_USER_KEY and user_key_resolver is None:
            msg = "user_key credential mode requires a user_key_resolver"
            raise ValueError(msg)
        if not (_TIMEOUT_MS_MIN <= default_timeout_ms <= _TIMEOUT_MS_MAX):
            msg = (
                f"default_timeout_ms must be within [{_TIMEOUT_MS_MIN}, "
                f"{_TIMEOUT_MS_MAX}], got {default_timeout_ms}"
            )
            raise ValueError(msg)
        self._manifest = manifest
        self._base_url = base_url.rstrip("/")
        self._resolve_gateway_secret = gateway_secret_resolver
        self._resolve_route_token = route_token_resolver
        self._credential_mode = credential_mode
        self._resolve_user_key = user_key_resolver
        self._transport = transport
        self._default_timeout_ms = default_timeout_ms
        self._clock = clock

    # -- declarative surface --------------------------------------------------------

    def get_manifest(self) -> ProviderManifest:
        return self._manifest

    async def get_capabilities(self) -> ProviderCapabilities:
        return self._manifest.capabilities

    # -- HTTP plumbing (transport injectable; secrets used at the last moment) ------

    def _client(self, timeout_seconds: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            transport=self._transport,
            timeout=timeout_seconds,
        )

    def _headers(self, secret: GatewaySecret, route_token: str) -> dict[str, str]:
        # The ONLY place the secret/route token are materialized: headers.
        return {
            HEADER_GATEWAY_SECRET: secret.value,
            HEADER_GATEWAY_SECRET_VERSION: str(secret.version),
            HEADER_ROUTE_TOKEN: route_token,
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> httpx.Response:
        """One authenticated gateway exchange with the self-healing auth retry.

        401 ``auth_expired`` (stale secret version — OPEN-7 rotation signal,
        not an attack signal) => re-read the gateway secret via the injected
        resolver and retry EXACTLY ONCE. Every other status returns as-is;
        transport errors propagate for ``normalize_error`` to classify.
        """
        response = await self._attempt(method, path, json_body, timeout_seconds)
        if response.status_code == 401 and _is_auth_expired(response):
            response = await self._attempt(method, path, json_body, timeout_seconds)
        return response

    async def _attempt(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None,
        timeout_seconds: float,
    ) -> httpx.Response:
        secret = self._resolve_gateway_secret()  # fresh per attempt (rotation)
        route_token = self._resolve_route_token()
        headers = self._headers(secret, route_token)
        async with self._client(timeout_seconds) as client:
            return await client.request(method, path, headers=headers, json=json_body)

    # -- credential validation (30 §8.1) ---------------------------------------------

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        """Gateway v1 cannot validate upstream credentials — honest refusal.

        Raises :class:`GatewayCredentialCheckUnsupported` (never a fake
        definite answer). The ref is not resolved and not echoed.
        """
        raise GatewayCredentialCheckUnsupported(
            "gateway v1 exposes no credential-validation surface"
        )

    # -- model discovery (30 §4.3: empty is valid, never invented) --------------------

    async def discover_models(self, account_id: UUID | None = None) -> list[DiscoveredModel]:
        """Report the remote provider's declared models via GET /v1/models.

        Unreachable/denied/malformed => [] honestly — never invented names
        (41 §49). The projection carries only what the gateway declares.
        """
        try:
            response = await self._request(
                "GET",
                MODELS_PATH,
                json_body=None,
                timeout_seconds=self._default_timeout_ms / 1000.0,
            )
        except httpx.HTTPError:
            return []
        if response.status_code != 200:
            return []
        try:
            declared = response.json().get("models", [])
        except ValueError:
            return []
        if not isinstance(declared, list):
            return []
        models: list[DiscoveredModel] = []
        for item in declared:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                continue
            limits: dict[str, Any] = {}
            context_window = item.get("context_window")
            if isinstance(context_window, int):
                limits["context_window"] = context_window
            models.append(
                DiscoveredModel(provider_model_name=name, limits_metadata=limits)
            )
        return models

    # -- generation (30 §8.1; wire: POST /v1/execute) ----------------------------------

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        operation = request.operation.value
        if operation in EXCLUDED_OPERATIONS_V1:
            return self._failed(
                request,
                ProviderError(
                    category=ProviderErrorCategory.UNSUPPORTED_CAPABILITY,
                    retryable=False,
                    provider_code="excluded_operation_v1",
                    safe_message=(
                        f"operation '{operation}' is excluded from gateway v1 "
                        "(ADR-0008 OPEN-2)"
                    ),
                ),
            )
        if request.operation not in self._manifest.operations:
            return self._failed(
                request,
                ProviderError(
                    category=ProviderErrorCategory.UNSUPPORTED_CAPABILITY,
                    retryable=False,
                    provider_code=None,
                    safe_message=(
                        f"operation '{operation}' is not declared by the "
                        f"'{self._manifest.id}' manifest"
                    ),
                ),
            )
        timeout_ms = (
            request.timeout_ms
            if request.timeout_ms is not None
            else self._default_timeout_ms
        )
        envelope = self._build_envelope(request, timeout_ms)
        started = time.monotonic()
        try:
            response = await self._request(
                "POST",
                EXECUTE_PATH,
                json_body=envelope,
                timeout_seconds=timeout_ms / 1000.0,
            )
        except Exception as exc:  # noqa: BLE001 — boundary: everything normalizes
            return self._failed(request, self.normalize_error(exc))
        latency_ms = int((time.monotonic() - started) * 1000)
        if response.status_code != 200:
            return self._failed(
                request, self._normalize_http_response(response), latency_ms=latency_ms
            )
        return self._parse_execute_body(request, response, latency_ms)

    def _build_envelope(
        self, request: ProviderGenerateRequest, timeout_ms: int
    ) -> dict[str, Any]:
        """Translate the core request into the wire RequestEnvelope (Layer 3).

        Documented boundary translations (parity report, G2): UUIDs
        serialize to str; ``provider_model_name`` -> ``model``; the opaque
        ``credential_ref`` becomes the ``credential`` block (user_key:
        resolved platform-side at the LAST moment; platform: no value).
        """
        credential: dict[str, Any] = {"mode": self._credential_mode}
        if self._credential_mode == CREDENTIAL_MODE_USER_KEY:
            if self._resolve_user_key is None:  # defensive; ctor already enforces
                msg = "user_key credential mode requires a user_key_resolver"
                raise ValueError(msg)
            credential["value"] = self._resolve_user_key(request.credential_ref)
        return {
            "operation": request.operation.value,
            "model": str(request.provider_model_name),
            "request_id": str(request.request_id),
            "tenant_id": str(request.tenant_id),
            "credential": credential,
            "payload": dict(request.payload),
            "timeout_ms": timeout_ms,
        }

    def _parse_execute_body(
        self,
        request: ProviderGenerateRequest,
        response: httpx.Response,
        latency_ms: int,
    ) -> ProviderGenerateResponse:
        """Defensively parse a 200 ResponseEnvelope; malformed => normalized.

        A gateway that answers 200 with a shape outside the contract is a
        DEFECT, not an excuse to crash or to echo the body: the caller gets
        ``non_retryable_error`` with a fixed safe message.
        """
        malformed = ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            provider_code="malformed_gateway_response",
            safe_message="gateway returned a malformed response envelope",
        )
        try:
            parsed = response.json()
        except ValueError:
            return self._failed(request, malformed, latency_ms=latency_ms)
        if not isinstance(parsed, dict):
            return self._failed(request, malformed, latency_ms=latency_ms)
        succeeded = parsed.get("succeeded")
        if succeeded is True:
            output = parsed.get("output")
            usage = parsed.get("usage")
            if not isinstance(output, dict):
                return self._failed(request, malformed, latency_ms=latency_ms)
            usage_obj = usage if isinstance(usage, dict) else {}
            return ProviderGenerateResponse(
                request_id=request.request_id,
                succeeded=True,
                output=output,
                usage=usage_obj,  # raw evidence only; the PLATFORM bills
                error=None,
                latency_ms=latency_ms,
            )
        if succeeded is False:
            error = _parse_wire_error(parsed.get("error"))
            if error is None:
                return self._failed(request, malformed, latency_ms=latency_ms)
            return self._failed(request, error, latency_ms=latency_ms)
        return self._failed(request, malformed, latency_ms=latency_ms)

    def _failed(
        self,
        request: ProviderGenerateRequest,
        error: ProviderError,
        *,
        latency_ms: int | None = None,
    ) -> ProviderGenerateResponse:
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=False,
            output={},
            usage={},
            error=error,
            latency_ms=latency_ms,
        )

    # -- health (30 §11; wire: GET /v1/health) ------------------------------------------

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        """Provider health via the gateway's /v1/health projection.

        ACCOUNT scope: upstream accounts (if any) are gateway-internal
        (Layer 1 freedom) and invisible here — reported as provider-scope
        evidence with an empty accounts map, mirroring the Groq posture.
        """
        checked_at = self._clock()
        try:
            response = await self._request(
                "GET",
                HEALTH_PATH,
                json_body=None,
                timeout_seconds=self._default_timeout_ms / 1000.0,
            )
        except httpx.HTTPError:
            return ProviderHealth(
                provider_id=self._manifest.id,
                state=ProviderHealthState.UNAVAILABLE,
                checked_at=checked_at,
                detail="gateway unreachable",
            )
        if response.status_code == 401:
            return ProviderHealth(
                provider_id=self._manifest.id,
                state=ProviderHealthState.DEGRADED,
                checked_at=checked_at,
                detail="gateway rejected platform authentication",
            )
        if response.status_code != 200:
            return ProviderHealth(
                provider_id=self._manifest.id,
                state=ProviderHealthState.UNAVAILABLE,
                checked_at=checked_at,
                detail=f"gateway returned http {response.status_code}",
            )
        try:
            status = response.json().get("status")
        except ValueError:
            status = None
        state = _HEALTH_STATUS_MAP.get(status) if isinstance(status, str) else None
        if state is None:
            return ProviderHealth(
                provider_id=self._manifest.id,
                state=ProviderHealthState.UNAVAILABLE,
                checked_at=checked_at,
                detail="gateway returned an unrecognized health status",
            )
        detail = (
            "gateway reported UNKNOWN health (treated as unavailable: "
            "unknown is never healthy)"
            if status == "UNKNOWN"
            else None
        )
        return ProviderHealth(
            provider_id=self._manifest.id,
            state=state,
            checked_at=checked_at,
            detail=detail,
        )

    # -- error normalization (30 §14) -----------------------------------------------------

    def normalize_error(self, error: object) -> ProviderError:
        """Map ANY raw failure object into the normalized 12-category shape.

        safe_message never embeds raw exception text, response bodies,
        secrets, tokens or slugs — fixed strings + short provider_code only.
        """
        if isinstance(error, ProviderError):
            return error
        if isinstance(error, httpx.Response):
            return self._normalize_http_response(error)
        if isinstance(error, httpx.TimeoutException):
            return ProviderError(
                category=ProviderErrorCategory.TIMEOUT,
                retryable=True,
                provider_code="timeout",
                safe_message="gateway request timed out",
            )
        if isinstance(error, httpx.HTTPError):
            return ProviderError(
                category=ProviderErrorCategory.PROVIDER_UNAVAILABLE,
                retryable=True,
                provider_code=type(error).__name__,
                safe_message="gateway is unreachable",
            )
        if isinstance(error, GatewayCredentialCheckUnsupported):
            return ProviderError(
                category=ProviderErrorCategory.UNSUPPORTED_CAPABILITY,
                retryable=False,
                provider_code="credential_check_unsupported",
                safe_message="gateway v1 exposes no credential-validation surface",
            )
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            provider_code=type(error).__name__ if isinstance(error, Exception) else None,
            safe_message="gateway call failed",
        )

    def _normalize_http_response(self, response: httpx.Response) -> ProviderError:
        """Non-200 gateway status -> normalized category (wire status map §9)."""
        status = response.status_code
        body_error = _safe_body_error(response)
        code = body_error.get("provider_code") if body_error else None
        provider_code = code if isinstance(code, str) and code else f"http_{status}"
        if status == 400:
            return ProviderError(
                category=ProviderErrorCategory.BAD_REQUEST,
                retryable=False,
                provider_code=provider_code,
                safe_message="gateway rejected the request envelope",
            )
        if status == 401:
            if _is_auth_expired(response):
                # Stale secret version even after the single self-healing
                # retry: rotation window missed — retryable once ops syncs.
                return ProviderError(
                    category=ProviderErrorCategory.AUTH_EXPIRED,
                    retryable=True,
                    provider_code=provider_code,
                    safe_message="gateway secret version no longer accepted",
                )
            return ProviderError(
                category=ProviderErrorCategory.INVALID_CREDENTIAL,
                retryable=False,
                provider_code=provider_code,
                safe_message="gateway authentication failed",
            )
        if status == 404:
            # Uniform anti-enumeration body: unknown == revoked == disabled.
            return ProviderError(
                category=ProviderErrorCategory.PROVIDER_UNAVAILABLE,
                retryable=False,
                provider_code=provider_code,
                safe_message="gateway does not recognize the provider route",
            )
        if status in (500, 502, 503, 504):
            return ProviderError(
                category=ProviderErrorCategory.RETRYABLE_SERVER_ERROR,
                retryable=True,
                provider_code=provider_code,
                safe_message="gateway internal error",
            )
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            provider_code=provider_code,
            safe_message="gateway returned an unexpected response",
        )


# --- module-private wire parsing helpers (fully deterministic) -----------------------


def _safe_body_error(response: httpx.Response) -> dict[str, Any] | None:
    """Extract the body's ``error`` object if (and only if) it is a dict."""
    try:
        parsed = response.json()
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    error = parsed.get("error")
    return error if isinstance(error, dict) else None


def _is_auth_expired(response: httpx.Response) -> bool:
    """True iff a 401 body carries category ``auth_expired`` (OPEN-7 signal)."""
    error = _safe_body_error(response)
    return error is not None and error.get("category") == "auth_expired"


def _parse_wire_error(raw: object) -> ProviderError | None:
    """Wire GatewayError dict -> normalized ProviderError; None if malformed.

    1:1 category mapping (parity is test-proven): the wire ``message``
    becomes ``safe_message`` — the gateway contract already guarantees it is
    sanitized (Layer 2 facades map to fixed safe strings). Unknown category
    values are treated as malformed, never guessed into a bucket.
    """
    if not isinstance(raw, dict):
        return None
    category_raw = raw.get("category")
    if not isinstance(category_raw, str):
        return None
    try:
        category = ProviderErrorCategory(category_raw)
    except ValueError:
        return None
    retryable = raw.get("retryable")
    message = raw.get("message")
    if not isinstance(retryable, bool) or not isinstance(message, str) or not message:
        return None
    retry_after_ms = raw.get("retry_after_ms")
    if retry_after_ms is not None and (
        not isinstance(retry_after_ms, int) or retry_after_ms < 0
    ):
        return None
    provider_code = raw.get("provider_code")
    if provider_code is not None and not isinstance(provider_code, str):
        return None
    if provider_code == "":  # wire tolerates ""; BoundedStr does not — drop, not fail
        provider_code = None
    return ProviderError(
        category=category,
        retryable=retryable,
        retry_after_ms=retry_after_ms,
        provider_code=provider_code,
        safe_message=message,
    )
