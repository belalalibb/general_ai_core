"""Genspark LLM Proxy real provider adapter (T-IMPL-037; 31 §19, §20 Type A).

The SECOND real provider, onboarded after groq (the reference
implementation). Implements ``ProviderAdapterPort`` (30 §8.1) against the
Genspark LLM proxy's OpenAI-compatible HTTP API
(https://www.genspark.ai/api/llm_proxy/v1). Independent implementation per
30 §7 ("every provider implementation is independent") — same architecture,
contracts, and security/recovery posture as groq, NOT a shared base class.

Posture rules enforced here (identical to the groq reference):

- 20 §5 credential handling: the adapter NEVER sees where secrets live.
  An injected ``secret_resolver`` trades an opaque ``credential_ref`` for
  the API key at the LAST possible moment; the resolved value is used
  solely for the Authorization header — never logged, never echoed, never
  placed in any returned object or error message.
- 30 §8.1: ``generate`` rejects operations the manifest does not declare
  with normalized ``unsupported_capability`` BEFORE any network call.
- 30 §14: ``safe_message`` carries a generic safe description only.
  Genspark-specific: the proxy reports errors as ``{"detail": str}``
  (FastAPI-style) or a 422 ``{"errors": [{"type": ...}]}`` validation
  shape — NEITHER raw message ever crosses; only a short machine code
  rides ``provider_code``. Verified live 2026-08-28: a disallowed model
  returns HTTP 400 (not 404) with a "Model '...' is not allowed" detail —
  detected structurally and mapped to ``model_unavailable``.
- 30 §11: provider health and credential health stay separate surfaces.

Hermeticity: the HTTP transport is injectable (``httpx.AsyncBaseTransport``)
so contract tests run against ``httpx.MockTransport`` with zero network;
the live binding uses the default transport. The gates never touch the
network.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from core.contracts.domain import CredentialStatus
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
    ProviderOperation,
)

#: Genspark LLM proxy's OpenAI-compatible base URL (31 §20 Type A).
GENSPARK_LLM_BASE_URL = "https://www.genspark.ai/api/llm_proxy/v1"

#: Generation parameters a caller may pass through ``payload["generation"]``.
#: Whitelist (deny-by-default): unknown keys are dropped, never forwarded.
_GENERATION_PARAM_WHITELIST = frozenset(
    {"temperature", "top_p", "max_tokens", "max_completion_tokens", "seed", "stop"}
)

#: Default completion budget when the caller does not set one.
_DEFAULT_MAX_COMPLETION_TOKENS = 1024

#: S2 pool bounds (mirror the gateway adapter): bounded connections per
#: adapter instance — no unbounded socket growth under fan-out.
_POOL_MAX_CONNECTIONS = 32
_POOL_MAX_KEEPALIVE = 8


class GensparkLLMCredentialCheckInconclusive(RuntimeError):
    """Credential validation could not reach a definite answer.

    Raised (never swallowed into a false INVALID/ACTIVE) when the provider
    is unreachable or errors server-side during validation — an inconclusive
    check is NOT evidence about the credential (30 §11 honesty).
    """


class GensparkLLMAdapter:
    """Real Genspark LLM proxy adapter implementing ``ProviderAdapterPort``.

    ``secret_resolver`` maps an opaque credential_ref to the API key —
    the composition root binds it to ``SecretManagerPort.resolve`` with
    the owning tenant already scoped. ``health_credential_ref`` is the ref
    used for provider-scope health checks and model discovery (both need
    an authenticated call); absent, those surfaces report honestly that
    they cannot check rather than faking an answer.
    """

    def __init__(
        self,
        manifest: ProviderManifest,
        *,
        secret_resolver: Callable[[str], str],
        health_credential_ref: str | None = None,
        base_url: str = GENSPARK_LLM_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        default_timeout_seconds: float = 60.0,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._manifest = manifest
        self._resolve = secret_resolver
        self._health_ref = health_credential_ref
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = default_timeout_seconds
        self._clock = clock
        # S2: ONE long-lived pooled client per adapter instance (connection
        # reuse across calls) — the same posture as the gateway adapter.
        # Created lazily on first use; ``aclose`` releases it.
        self._pooled_client: httpx.AsyncClient | None = None
        self._pool_limits = httpx.Limits(
            max_connections=_POOL_MAX_CONNECTIONS,
            max_keepalive_connections=_POOL_MAX_KEEPALIVE,
        )

    # -- lifecycle (S2) ---------------------------------------------------------------

    async def aclose(self) -> None:
        """Release the pooled HTTP client (idempotent; safe to call twice)."""
        client, self._pooled_client = self._pooled_client, None
        if client is not None:
            await client.aclose()

    # -- declarative surface ---------------------------------------------------------

    def get_manifest(self) -> ProviderManifest:
        return self._manifest

    async def get_capabilities(self) -> ProviderCapabilities:
        return self._manifest.capabilities

    # -- HTTP plumbing (transport injectable; secret used at the last moment) --------

    def _client(self) -> httpx.AsyncClient:
        """The pooled client, (re)created lazily if absent or closed (S2).

        Per-request timeouts ride the request call (``timeout=``), so one
        pooled client serves every operation's own deadline.
        """
        client = self._pooled_client
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                base_url=self._base_url,
                transport=self._transport,
                timeout=self._timeout,
                limits=self._pool_limits,
            )
            self._pooled_client = client
        return client

    @staticmethod
    def _auth_headers(api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    # -- credential validation (31 §19 step 5; 20 §5) ---------------------------------

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        """Check the credential via GET /models (cheapest authenticated call).

        Definite answers only: 200 => active; 401/403 => invalid. Anything
        else (network failure, 5xx, timeouts) raises
        :class:`GensparkLLMCredentialCheckInconclusive` — inconclusive is
        NOT evidence about the credential.
        """
        api_key = self._resolve(credential_ref)
        try:
            response = await self._client().get(
                "/models", headers=self._auth_headers(api_key), timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            raise GensparkLLMCredentialCheckInconclusive(
                "credential check could not reach the provider"
            ) from exc
        if response.status_code == 200:
            status = CredentialStatus.ACTIVE
            detail = None
        elif response.status_code in (401, 403):
            status = CredentialStatus.INVALID
            detail = "provider rejected the credential"
        else:
            raise GensparkLLMCredentialCheckInconclusive(
                f"credential check inconclusive (http {response.status_code})"
            )
        return CredentialHealth(
            credential_ref=credential_ref,
            status=status,
            checked_at=self._clock(),
            detail=detail,
        )

    # -- model discovery (31 §19 step 12; 30 §4.3) -------------------------------------

    async def discover_models(self, account_id: UUID | None = None) -> list[DiscoveredModel]:
        """Report the proxy's declared models via GET /models.

        Requires the health credential ref; without one this surface cannot
        authenticate and returns [] honestly (30 §4.3) — it never invents
        model names (41 §49).
        """
        if self._health_ref is None:
            return []
        api_key = self._resolve(self._health_ref)
        try:
            response = await self._client().get(
                "/models", headers=self._auth_headers(api_key), timeout=self._timeout
            )
        except httpx.HTTPError:
            return []
        if response.status_code != 200:
            return []
        models: list[DiscoveredModel] = []
        for item in response.json().get("data", []):
            model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue
            models.append(
                DiscoveredModel(
                    provider_model_name=model_id,
                    modalities=["text"],
                )
            )
        return models

    # -- generation (31 §19 step 4: only declared operations) --------------------------

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        if request.operation not in self._manifest.operations:
            return self._failed(
                request,
                ProviderError(
                    category=ProviderErrorCategory.UNSUPPORTED_CAPABILITY,
                    retryable=False,
                    provider_code=None,
                    safe_message=(
                        f"operation '{request.operation.value}' is not declared "
                        "by the genspark_llm manifest"
                    ),
                ),
            )
        if request.operation is ProviderOperation.CREATE_EMBEDDINGS:
            path = "/embeddings"
            body = _embeddings_body(request)
            if body is None:
                return self._failed(
                    request,
                    ProviderError(
                        category=ProviderErrorCategory.BAD_REQUEST,
                        retryable=False,
                        provider_code="missing_input",
                        safe_message=(
                            "create_embeddings requires payload['input'] as a "
                            "non-empty string or list of strings"
                        ),
                    ),
                )
        else:
            path = "/chat/completions"
            body = _chat_completion_body(request)
        timeout_s = request.timeout_ms / 1000.0 if request.timeout_ms is not None else self._timeout
        api_key = self._resolve(request.credential_ref)  # last-moment resolve (20 §5)
        started = time.monotonic()
        try:
            response = await self._client().post(
                path,
                headers=self._auth_headers(api_key),
                json=body,
                timeout=timeout_s,
            )
        except Exception as exc:  # noqa: BLE001 — boundary: everything normalizes
            return self._failed(request, self.normalize_error(exc))
        latency_ms = int((time.monotonic() - started) * 1000)
        if response.status_code != 200:
            return self._failed(
                request, self._normalize_http_response(response), latency_ms=latency_ms
            )
        try:
            parsed = response.json()
            if request.operation is ProviderOperation.CREATE_EMBEDDINGS:
                output = _extract_embeddings(parsed)
            else:
                content, finish_reason = _extract_content(parsed)
                output = {"content": content, "finish_reason": finish_reason}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            return self._failed(request, self.normalize_error(exc), latency_ms=latency_ms)
        usage = _extract_usage(parsed)
        if request.operation is not ProviderOperation.CREATE_EMBEDDINGS and _is_plan_refusal(
            str(output.get("content", "")), usage
        ):
            # D-01 (R168): an in-band HTTP-200 refusal is NOT a completion. The
            # gateway performed no inference (zero reported usage) and answered
            # with its plan-refusal notice instead of the model. Book it as a
            # FAILED, account-indicting call so the run fails, settles 0 units
            # and the router may fail over. The refusal text never crosses.
            return self._failed(
                request,
                ProviderError(
                    category=ProviderErrorCategory.QUOTA_EXCEEDED,
                    retryable=False,
                    provider_code="plan_refusal_200",
                    safe_message="provider plan refused inference; no tokens were consumed",
                ),
                latency_ms=latency_ms,
            )
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output=output,
            usage=usage,
            error=None,
            latency_ms=latency_ms,
        )

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

    # -- health (31 §19 step 6; 30 §11 separation) --------------------------------------

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        """Provider-scope health via GET /models with the health credential.

        No health credential configured => UNAVAILABLE with an honest
        detail (cannot verify is not healthy). The proxy has no account
        pool (manifest declares supported=false).
        """
        checked_at = self._clock()
        if self._health_ref is None:
            return ProviderHealth(
                provider_id=self._manifest.id,
                state=ProviderHealthState.UNAVAILABLE,
                checked_at=checked_at,
                detail="no health credential configured; health cannot be verified",
            )
        api_key = self._resolve(self._health_ref)
        try:
            response = await self._client().get(
                "/models", headers=self._auth_headers(api_key), timeout=self._timeout
            )
        except httpx.HTTPError:
            return ProviderHealth(
                provider_id=self._manifest.id,
                state=ProviderHealthState.UNAVAILABLE,
                checked_at=checked_at,
                detail="provider unreachable",
            )
        if response.status_code == 200:
            state = ProviderHealthState.HEALTHY
            detail = None
        elif response.status_code in (401, 403):
            state = ProviderHealthState.DEGRADED
            detail = "health credential rejected by provider"
        elif response.status_code == 429:
            state = ProviderHealthState.DEGRADED
            detail = "provider rate-limiting the health credential"
        else:
            state = ProviderHealthState.UNAVAILABLE
            detail = f"provider returned http {response.status_code}"
        return ProviderHealth(
            provider_id=self._manifest.id,
            state=state,
            checked_at=checked_at,
            detail=detail,
        )

    # -- error normalization (31 §19 step 7; 30 §14) -------------------------------------

    def normalize_error(self, error: object) -> ProviderError:
        """Map ANY raw failure object into the normalized 12-category shape.

        The safe_message NEVER embeds raw exception text or response bodies;
        the raw signal is reduced to a short provider_code for diagnostics.
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
                safe_message="provider request timed out",
            )
        if isinstance(error, httpx.HTTPError):
            return ProviderError(
                category=ProviderErrorCategory.PROVIDER_UNAVAILABLE,
                retryable=True,
                provider_code=type(error).__name__,
                safe_message="provider is unreachable",
            )
        if isinstance(error, GensparkLLMCredentialCheckInconclusive):
            return ProviderError(
                category=ProviderErrorCategory.PROVIDER_UNAVAILABLE,
                retryable=True,
                provider_code="credential_check_inconclusive",
                safe_message="credential check could not reach the provider",
            )
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            provider_code=type(error).__name__ if isinstance(error, Exception) else None,
            safe_message="provider call failed",
        )

    def _normalize_http_response(self, response: httpx.Response) -> ProviderError:
        """HTTP status -> normalized category (30 §14 mapping, genspark shapes).

        Live-verified shapes (2026-08-28): errors come as ``{"detail": str}``
        or a 422 ``{"errors": [{"type": ...}]}`` validation report. A
        disallowed model returns HTTP **400** (not 404) with a detail
        starting "Model '...' is not allowed" — detected structurally and
        mapped to ``model_unavailable``. Raw detail text NEVER crosses.
        """
        status = response.status_code
        code = _safe_error_code(response)
        if status in (401, 403):
            return ProviderError(
                category=ProviderErrorCategory.INVALID_CREDENTIAL,
                retryable=False,
                provider_code=code or f"http_{status}",
                safe_message="provider rejected the credential",
            )
        if status == 429:
            return ProviderError(
                category=ProviderErrorCategory.RATE_LIMITED,
                retryable=True,
                retry_after_ms=_retry_after_ms(response),
                provider_code=code or "http_429",
                safe_message="provider rate limit reached",
            )
        if status == 404:
            return ProviderError(
                category=ProviderErrorCategory.MODEL_UNAVAILABLE,
                retryable=False,
                provider_code=code or "http_404",
                safe_message="requested model is not available at the provider",
            )
        if status in (400, 413, 422):
            if _is_model_not_allowed(response):
                return ProviderError(
                    category=ProviderErrorCategory.MODEL_UNAVAILABLE,
                    retryable=False,
                    provider_code="model_not_allowed",
                    safe_message="requested model is not available at the provider",
                )
            return ProviderError(
                category=ProviderErrorCategory.BAD_REQUEST,
                retryable=False,
                provider_code=code or f"http_{status}",
                safe_message="provider rejected the request",
            )
        if status in (500, 502, 503, 504):
            return ProviderError(
                category=ProviderErrorCategory.RETRYABLE_SERVER_ERROR,
                retryable=True,
                provider_code=code or f"http_{status}",
                safe_message="provider server error",
            )
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            provider_code=code or f"http_{status}",
            safe_message="provider returned an unexpected response",
        )


# --- request/response shaping helpers (module-private, fully deterministic) ----------


def _chat_completion_body(request: ProviderGenerateRequest) -> dict[str, Any]:
    """Build the OpenAI-compatible chat body from the normalized payload.

    Same documented mapping as the groq reference (kept minimal/explicit):

    - ``payload["role"]["objective"]`` (str) -> system message, verbatim.
    - ``payload["context"]`` (object)       -> system message carrying the
      composed 13 §5 context as compact JSON.
    - ``payload["previous_output"]["content"]`` (str) -> assistant message.
    - ``payload["ask"]`` (str) -> user message.
    - ``payload["generation"]`` (object) -> whitelisted sampling params.
    """
    payload = request.payload
    messages: list[dict[str, str]] = []
    role = payload.get("role")
    if isinstance(role, dict) and isinstance(role.get("objective"), str):
        messages.append({"role": "system", "content": role["objective"]})
    context = payload.get("context")
    if isinstance(context, dict) and context:
        messages.append(
            {"role": "system", "content": "Context:\n" + json.dumps(context, sort_keys=True)}
        )
    previous = payload.get("previous_output")
    if isinstance(previous, dict) and isinstance(previous.get("content"), str):
        messages.append({"role": "assistant", "content": previous["content"]})
    ask = payload.get("ask")
    messages.append({"role": "user", "content": ask if isinstance(ask, str) else ""})

    body: dict[str, Any] = {
        "model": str(request.provider_model_name),
        "messages": messages,
        "max_completion_tokens": _DEFAULT_MAX_COMPLETION_TOKENS,
        "stream": False,
    }
    generation = payload.get("generation")
    if isinstance(generation, dict):
        for key, value in generation.items():
            if key in _GENERATION_PARAM_WHITELIST:
                body[key] = value
    return body


def _embeddings_body(request: ProviderGenerateRequest) -> dict[str, Any] | None:
    """Build the OpenAI-compatible embeddings body from the normalized payload.

    ``payload["input"]`` must be a non-empty string or a non-empty list of
    strings; anything else returns None and the caller reports a normalized
    ``bad_request`` WITHOUT any network call (fail-before-spend).
    """
    raw = request.payload.get("input")
    if isinstance(raw, str) and raw:
        input_value: str | list[str] = raw
    elif isinstance(raw, list) and raw and all(isinstance(item, str) and item for item in raw):
        input_value = raw
    else:
        return None
    return {"model": str(request.provider_model_name), "input": input_value}


def _extract_embeddings(parsed: dict[str, Any]) -> dict[str, Any]:
    """Extract vectors from the OpenAI-compatible embeddings response.

    Output shape: ``{"embeddings": [[float, ...], ...], "dimensions": int}``
    preserving provider order (index-sorted, honest to the provider's own
    index field). Raises on malformed payloads — the caller normalizes.
    """
    data = parsed["data"]
    if not isinstance(data, list) or not data:
        raise ValueError("embeddings response carried no data items")
    items = sorted(data, key=lambda item: item.get("index", 0))
    vectors: list[list[float]] = []
    for item in items:
        vector = item["embedding"]
        if not isinstance(vector, list) or not vector:
            raise ValueError("embeddings response carried an empty vector")
        vectors.append([float(component) for component in vector])
    return {"embeddings": vectors, "dimensions": len(vectors[0])}


def _extract_content(parsed: dict[str, Any]) -> tuple[str, str | None]:
    choice = parsed["choices"][0]
    message = choice.get("message", {})
    content = message.get("content")
    if not isinstance(content, str):
        content = ""
    finish = choice.get("finish_reason")
    return content, finish if isinstance(finish, str) else None


def _extract_usage(parsed: dict[str, Any]) -> dict[str, Any]:
    usage = parsed.get("usage")
    if not isinstance(usage, dict):
        return {}
    return {
        key: usage[key]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if isinstance(usage.get(key), int)
    }


# D-01 (R168): signature of the gateway's in-band plan refusal (captured shape
# evidence/failure_shapes/genspark_llm_200_plan_refusal.json). Matching is
# case-insensitive and requires *both* signals — zero reported usage (no
# inference happened) AND the refusal wording — so a genuine completion that
# merely quotes the wording (and therefore consumed tokens) stays a success.
_PLAN_REFUSAL_MARKERS: tuple[str, ...] = (
    "free-plan credits",
    "genspark.ai/pricing",
    "purchase credits",
)


def _is_plan_refusal(content: str, usage: dict[str, Any]) -> bool:
    if not usage:
        return False  # no usage block at all: cannot prove "no inference"
    if usage.get("total_tokens", 0) != 0 or usage.get("completion_tokens", 0) != 0:
        return False
    lowered = content.lower()
    return any(marker in lowered for marker in _PLAN_REFUSAL_MARKERS)


def _retry_after_ms(response: httpx.Response) -> int | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0, int(float(raw) * 1000))
    except ValueError:
        return None


def _safe_error_code(response: httpx.Response) -> str | None:
    """Extract only a short machine error code — never the raw message.

    Genspark proxy shapes: OpenAI-style ``error.code`` when upstream relays
    it; FastAPI 422 validation ``errors[0].type`` (a machine token like
    ``list_type``); plain ``{"detail": str}`` bodies carry NO machine code
    (returns None — the caller falls back to ``http_<status>``).
    """
    try:
        parsed = response.json()
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    error = parsed.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str) and code:
            return code
    errors = parsed.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        etype = errors[0].get("type")
        if isinstance(etype, str) and etype:
            return f"validation_{etype}"
    return None


def _is_model_not_allowed(response: httpx.Response) -> bool:
    """Structurally detect the proxy's model-allowlist rejection.

    Live-verified shape: HTTP 400 ``{"detail": "Model '<name>' is not
    allowed. Allowed models: ..."}``. Only the boolean verdict leaves this
    function — the detail text (which echoes the requested model name and
    the allowlist) never crosses the boundary.
    """
    try:
        parsed = response.json()
    except ValueError:
        return False
    if not isinstance(parsed, dict):
        return False
    detail = parsed.get("detail")
    return isinstance(detail, str) and detail.startswith("Model ") and "is not allowed" in detail
