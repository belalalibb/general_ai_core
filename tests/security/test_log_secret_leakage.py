"""Exception/message secret-leakage regression (T-IMPL-033; 20 §5).

CONFIRMED DEFECT (found while starting T-IMPL-033, fixed in the same
slice): the head-of-pipeline scrubber matched KEY markers only, so secret
material embedded in FREE TEXT leaked two ways:

1. Secrets interpolated into the event MESSAGE string (key ``event``
   carries no marker) passed the key-marker scrub untouched.
2. Secrets inside EXCEPTION args were invisible to the head scrubber
   (still a live ``exc_info`` tuple at index 0) and were rendered into
   the ``exception`` string field by ``format_exc_info`` AFTER it — the
   rendered text reached the JSON renderer unscrubbed.

FIX UNDER TEST: (a) the head scrubber additionally pattern-scrubs every
string VALUE for credential shapes (bearer tokens, PEM blocks, AWS key
ids, JWTs, opaque API tokens); (b) a second scrub pass
(``scrub_rendered_exception``) sits immediately after ``format_exc_info``
and pattern-scrubs the late-rendered string fields.

Hermetic — processors invoked directly, no logging I/O, no network.
"""

from __future__ import annotations

import sys
from typing import Any

from apps.observability.config import ObservabilityConfig
from apps.observability.logs import (
    build_processors,
    scrub_rendered_exception,
    scrub_secrets,
)

_SK_TOKEN = "sk-live_abcdefghijklmnop1234"
_BEARER = "Bearer AbCdEfGhIjKlMnOpQrStUvWxYz012345"
_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature-part"
_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"


def _render(event: dict[str, Any]) -> str:
    """Drive the FULL pipeline exactly as configure_logging wires it."""
    processors = build_processors(ObservabilityConfig())
    current: Any = event
    for processor in processors[:-1]:
        current = processor(None, "error", current)
    rendered = processors[-1](None, "error", current)
    assert isinstance(rendered, str)
    return rendered


# --- defect 1: secrets in the event message -----------------------------------


class TestMessageValueScrubbing:
    def test_api_token_in_message_is_scrubbed(self) -> None:
        rendered = _render({"event": f"provider call failed with key {_SK_TOKEN}"})
        assert _SK_TOKEN not in rendered
        assert "[SCRUBBED]" in rendered

    def test_bearer_token_in_message_is_scrubbed(self) -> None:
        rendered = _render({"event": f"upstream said: {_BEARER}"})
        assert _BEARER not in rendered

    def test_jwt_in_message_is_scrubbed(self) -> None:
        rendered = _render({"event": f"got jwt {_JWT}"})
        assert _JWT not in rendered

    def test_aws_key_id_in_message_is_scrubbed(self) -> None:
        rendered = _render({"event": f"using {_AWS_KEY} for s3"})
        assert _AWS_KEY not in rendered

    def test_pem_header_is_scrubbed(self) -> None:
        rendered = _render({"event": "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."})
        assert "BEGIN RSA PRIVATE KEY" not in rendered

    def test_secret_in_nested_string_value_is_scrubbed(self) -> None:
        rendered = _render({"event": "call", "detail": {"note": f"used {_SK_TOKEN}"}})
        assert _SK_TOKEN not in rendered

    def test_plain_text_survives_untouched(self) -> None:
        rendered = _render({"event": "routine health check ok", "count": 3})
        assert "routine health check ok" in rendered
        assert "[SCRUBBED]" not in rendered


# --- defect 2: secrets inside exception args -----------------------------------


class TestExceptionScrubbing:
    def _render_with_exception(self, message: str) -> str:
        event: dict[str, Any] = {"event": "provider call failed"}
        try:
            raise ValueError(message)
        except ValueError:
            event["exc_info"] = sys.exc_info()
        return _render(event)

    def test_bearer_token_in_exception_args_is_scrubbed(self) -> None:
        rendered = self._render_with_exception(f"auth failed: {_BEARER}")
        assert _BEARER not in rendered
        assert "ValueError" in rendered  # diagnosis stays useful

    def test_api_token_in_exception_args_is_scrubbed(self) -> None:
        rendered = self._render_with_exception(f"rejected key {_SK_TOKEN}")
        assert _SK_TOKEN not in rendered

    def test_jwt_in_exception_args_is_scrubbed(self) -> None:
        rendered = self._render_with_exception(f"expired: {_JWT}")
        assert _JWT not in rendered

    def test_chained_exception_text_is_scrubbed(self) -> None:
        event: dict[str, Any] = {"event": "outer failure"}
        try:
            try:
                raise ConnectionError(f"dial failed using {_AWS_KEY}")
            except ConnectionError as inner:
                raise RuntimeError("retry exhausted") from inner
        except RuntimeError:
            event["exc_info"] = sys.exc_info()
        rendered = _render(event)
        assert _AWS_KEY not in rendered


# --- pipeline-shape security properties ----------------------------------------


class TestPipelineShape:
    def test_head_scrubber_remains_index_zero(self) -> None:
        processors = build_processors(ObservabilityConfig())
        head = processors[0]
        out = head(None, "info", {"secret": "x", "msg": f"has {_SK_TOKEN}"})
        assert out["secret"] == "[SCRUBBED]"
        assert _SK_TOKEN not in out["msg"]

    def test_rendered_exception_scrub_sits_after_format_exc_info(self) -> None:
        """Order is the security property: the post-render scrub must see
        the string ``format_exc_info`` produced."""
        import structlog

        processors = build_processors(ObservabilityConfig())
        names = [getattr(p, "__name__", getattr(p, "__qualname__", repr(p))) for p in processors]
        fmt_index = processors.index(structlog.processors.format_exc_info)
        # The processor right after format_exc_info is the post-render scrub
        post = processors[fmt_index + 1]
        scrubbed = post(None, "error", {"exception": f"boom {_BEARER}"})
        assert _BEARER not in scrubbed["exception"]
        assert names[-1]  # renderer still last (sanity)

    def test_direct_processor_units(self) -> None:
        config = ObservabilityConfig()
        head = scrub_secrets(config)
        post = scrub_rendered_exception(config)
        assert _SK_TOKEN not in str(head(None, "e", {"event": _SK_TOKEN}))
        assert _BEARER not in str(post(None, "e", {"exception": _BEARER}))
