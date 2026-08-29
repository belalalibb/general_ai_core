"""PROVIDER FACADE TEMPLATE (Layer 2) — the only layer the platform sees.

═══════════════════════════════════════════════════════════════════════════
THREE-LAYER MODEL — read this before writing any code:

  BELOW this layer (Layer 1 — YOUR territory, 100% free):
      implement whatever you want, in any structure: one file or thirty,
      any SDK, any auth (OAuth/session/cookies), account pools, rotation,
      caching, N chained upstream calls, internal fallback, renormalization.
      None of it is visible to the platform. (Gateway-level retries are
      ZERO in v1 — internal retry behavior is subject to the gateway's
      usage/billing integrity rules, ADR-0008.)

  ABOVE this layer (Layer 3 — fixed, never changes):
      gateway.contracts — RequestEnvelope / ResponseEnvelope / the 12-
      category error taxonomy / Usage shape / security headers. You
      cannot break, extend, or bypass it.

  THIS layer (Layer 2 — the MANDATORY translator, the only one the
      platform sees): each handler receives a ProviderContext and returns
      a FacadeResult — EITHER a canonical success matching the operation's
      output schema below, OR an error mapped to ONE of the 12 categories.
      No third shape. You never see the slug, the route_token, or the
      caller's identity.

ONE REQUEST -> ONE CANONICAL RESPONSE: one gateway request may internally
produce any workflow (auth + account selection + several upstream calls +
internal fallback + normalization) but exactly ONE canonical result comes
out. The platform never sees your internal call count.
═══════════════════════════════════════════════════════════════════════════

IMPORT RULE: this file imports ONLY from gateway.contracts (and
gateway.errors helpers). NEVER `from app import ...` — providers do not
depend on the application; the dependency arrow points the other way.

THE 12 ERROR CATEGORIES (map every failure to exactly one):

    auth_expired            credential/session was valid and expired; a
                            refresh may fix it            (retryable: yes)
    invalid_credential      key/session is wrong/revoked  (retryable: no)
    rate_limited            upstream 429/throttle — set retry_after_ms
                                                          (retryable: yes)
    quota_exceeded          hard quota/billing cap        (retryable: no)
    model_unavailable       requested model missing upstream (no)
    provider_unavailable    upstream down/unreachable     (no*)
    unsupported_capability  operation/feature not supported (no)
    bad_request             caller payload invalid        (no)
    content_rejected        safety/policy refusal         (no)
    timeout                 upstream exceeded timeout_ms  (yes)
    retryable_server_error  upstream 5xx/transient        (yes)
    non_retryable_error     everything else, permanent    (no)

    (*) provider_unavailable retryable=False by default here; the
    PLATFORM decides failover — never retry inside the gateway in v1.

TYPICAL HTTP MAPPING: 401/403 -> invalid_credential (or auth_expired if a
refresh path exists) · 404 model -> model_unavailable · 408/timeout ->
timeout · 413/422/400 -> bad_request · 429 -> rate_limited (+retry_after_ms)
· 402/quota -> quota_exceeded · 5xx -> retryable_server_error · safety
block -> content_rejected · connection refused -> provider_unavailable.

Fill in ONLY the operations you actually support; delete the rest; keep
HANDLERS in exact parity with DEFINITION["operations"] (checked at startup).
"""

from __future__ import annotations

from gateway.contracts import (  # Layer 3 — the fixed contract; NEVER from `app`
    ErrorCategory,
    FacadeResult,
    GatewayOperation,
    ProviderContext,
    Usage,
)
from gateway.errors import make_error

# Silence "imported but unused" while this is an unfilled template; delete
# this line once you implement your first handler.
_TEMPLATE_CONTRACT_TYPES = (ErrorCategory, Usage, make_error)


async def generate_text(context: ProviderContext) -> FacadeResult:
    """generate_text — chat/completion style text generation.

    (a) RECEIVES — context.payload fields:
        messages     list[{role: str, content: str}]   REQUIRED, non-empty
        temperature  float                              optional
        max_tokens   int                                optional
        (context.model = exact upstream model name — NEVER substitute it;
         context.credential_value = user key when mode is user_key;
         context.timeout_ms = enforce it toward upstream.)

    (b) MUST RETURN — canonical success output (exact fields):
        {"text": str, "finish_reason": str}   # "stop" | "length" | "filter"
        plus Usage(input_tokens, output_tokens, units=1) when known.

    (c) ERROR MAPPING: upstream 429 -> rate_limited (+retry_after_ms);
        401 -> invalid_credential; expired session -> auth_expired;
        unknown model -> model_unavailable; safety block ->
        content_rejected; 5xx -> retryable_server_error; deadline ->
        timeout; bad payload -> bad_request.

    (d) EXAMPLE:
        in : {"messages": [{"role": "user", "content": "hi"}]}
        out: {"text": "Hello!", "finish_reason": "stop"}
    """

    raise NotImplementedError("fill in or remove — see docstring")


async def generate_image(context: ProviderContext) -> FacadeResult:
    """generate_image — text-to-image.

    (a) RECEIVES — context.payload fields:
        prompt   str    REQUIRED
        size     str    optional, e.g. "1024x1024"
        count    int    optional, default 1

    (b) MUST RETURN:
        {"images": [{"b64": str, "format": str}]}   # format: "png"|"jpeg"|...
        plus Usage(units=<images generated>).

    (c) ERROR MAPPING: policy refusal -> content_rejected; 429 ->
        rate_limited; quota cap -> quota_exceeded; unknown model ->
        model_unavailable; 5xx -> retryable_server_error.

    (d) EXAMPLE:
        in : {"prompt": "a red cube", "count": 1}
        out: {"images": [{"b64": "<base64>", "format": "png"}]}
    """

    raise NotImplementedError("fill in or remove — see docstring")


async def transcribe_audio(context: ProviderContext) -> FacadeResult:
    """transcribe_audio — speech-to-text.

    (a) RECEIVES — context.payload fields:
        audio_b64     str   REQUIRED (base64-encoded audio bytes)
        audio_format  str   REQUIRED, e.g. "mp3" | "wav"
        language      str   optional BCP-47 hint

    (b) MUST RETURN:
        {"text": str, "language": str | null}
        plus Usage(units=1) (or provider-reported seconds as units).

    (c) ERROR MAPPING: undecodable/oversized audio -> bad_request;
        unsupported format -> bad_request; 429 -> rate_limited;
        5xx -> retryable_server_error; deadline -> timeout.

    (d) EXAMPLE:
        in : {"audio_b64": "<base64>", "audio_format": "wav"}
        out: {"text": "hello world", "language": "en"}
    """

    raise NotImplementedError("fill in or remove — see docstring")


async def synthesize_speech(context: ProviderContext) -> FacadeResult:
    """synthesize_speech — text-to-speech.

    (a) RECEIVES — context.payload fields:
        text          str   REQUIRED
        voice         str   optional (provider-declared voice name)
        audio_format  str   optional, default "mp3"

    (b) MUST RETURN:
        {"audio_b64": str, "audio_format": str}
        plus Usage(input_tokens=<chars or tokens>, units=1).

    (c) ERROR MAPPING: unknown voice -> bad_request; text too long ->
        bad_request; policy refusal -> content_rejected; 429 ->
        rate_limited; 5xx -> retryable_server_error.

    (d) EXAMPLE:
        in : {"text": "hello", "voice": "alloy"}
        out: {"audio_b64": "<base64>", "audio_format": "mp3"}
    """

    raise NotImplementedError("fill in or remove — see docstring")


async def create_embeddings(context: ProviderContext) -> FacadeResult:
    """create_embeddings — vector embeddings for a batch of inputs.

    (a) RECEIVES — context.payload fields:
        inputs   list[str]   REQUIRED, non-empty

    (b) MUST RETURN:
        {"embeddings": [[float, ...], ...], "dimensions": int}
        # embeddings[i] corresponds to inputs[i], ORDER PRESERVED.
        plus Usage(input_tokens=<total>, units=len(inputs)).

    (c) ERROR MAPPING: empty/oversized batch -> bad_request; unknown
        model -> model_unavailable; 429 -> rate_limited; 5xx ->
        retryable_server_error.

    (d) EXAMPLE:
        in : {"inputs": ["hello"]}
        out: {"embeddings": [[0.01, -0.02, 0.5]], "dimensions": 3}
    """

    raise NotImplementedError("fill in or remove — see docstring")


async def rerank_documents(context: ProviderContext) -> FacadeResult:
    """rerank_documents — relevance-order documents against a query.

    (a) RECEIVES — context.payload fields:
        query      str         REQUIRED
        documents  list[str]   REQUIRED, non-empty
        top_n      int         optional, default len(documents)

    (b) MUST RETURN:
        {"results": [{"index": int, "relevance_score": float}]}
        # index refers to the CALLER's documents list; sorted by
        # relevance_score descending; at most top_n entries.
        plus Usage(units=len(documents)).

    (c) ERROR MAPPING: empty documents -> bad_request; 429 ->
        rate_limited; 5xx -> retryable_server_error.

    (d) EXAMPLE:
        in : {"query": "cats", "documents": ["dog", "cat"]}
        out: {"results": [{"index": 1, "relevance_score": 0.97},
                          {"index": 0, "relevance_score": 0.12}]}
    """

    raise NotImplementedError("fill in or remove — see docstring")


async def moderate_content(context: ProviderContext) -> FacadeResult:
    """moderate_content — safety classification of content.

    (a) RECEIVES — context.payload fields:
        content   str   REQUIRED

    (b) MUST RETURN:
        {"flagged": bool, "categories": {str: bool}}
        # categories keys are the provider's own taxonomy (free), values
        # are booleans; "flagged" is the overall verdict.
        plus Usage(units=1).

    (c) ERROR MAPPING: NOTE — a "flagged" verdict is a SUCCESS (the
        moderation ran and answered), NOT content_rejected.
        content_rejected is only for the upstream REFUSING to process.
        Empty content -> bad_request; 429 -> rate_limited; 5xx ->
        retryable_server_error.

    (d) EXAMPLE:
        in : {"content": "some text"}
        out: {"flagged": false, "categories": {"hate": false}}
    """

    raise NotImplementedError("fill in or remove — see docstring")


async def analyze_vision(context: ProviderContext) -> FacadeResult:
    """analyze_vision — answer an instruction about an image.

    (a) RECEIVES — context.payload fields:
        image_b64     str   REQUIRED (base64-encoded image bytes)
        image_format  str   REQUIRED, e.g. "png" | "jpeg"
        instruction   str   REQUIRED (what to analyze/answer)

    (b) MUST RETURN:
        {"text": str}    # the analysis/answer
        plus Usage(input_tokens, output_tokens, units=1) when known.

    (c) ERROR MAPPING: undecodable/oversized image -> bad_request;
        model without vision -> unsupported_capability; policy refusal ->
        content_rejected; 429 -> rate_limited; 5xx ->
        retryable_server_error.

    (d) EXAMPLE:
        in : {"image_b64": "<base64>", "image_format": "png",
              "instruction": "what color is the cube?"}
        out: {"text": "The cube is red."}
    """

    raise NotImplementedError("fill in or remove — see docstring")


# ═══════════════════════════════════════════════════════════════════════
# HANDLERS — keep in EXACT parity with DEFINITION["operations"].
# Declared-without-handler OR handler-without-declaration = STARTUP failure.
# An unsupported operation is NOT declared at all (no empty declared stubs
# — declaration IS the source of eligibility). Delete unused stubs above.
# ═══════════════════════════════════════════════════════════════════════
HANDLERS: dict[GatewayOperation, object] = {
    # GatewayOperation.GENERATE_TEXT: generate_text,
    # GatewayOperation.GENERATE_IMAGE: generate_image,
    # GatewayOperation.TRANSCRIBE_AUDIO: transcribe_audio,
    # GatewayOperation.SYNTHESIZE_SPEECH: synthesize_speech,
    # GatewayOperation.CREATE_EMBEDDINGS: create_embeddings,
    # GatewayOperation.RERANK_DOCUMENTS: rerank_documents,
    # GatewayOperation.MODERATE_CONTENT: moderate_content,
    # GatewayOperation.ANALYZE_VISION: analyze_vision,
}
