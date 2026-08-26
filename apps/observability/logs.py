"""structlog JSON pipeline (ADR-0004): scrubbing first, correlation, JSON out.

Processor order is a security property (20 §5): the secret-scrubbing
processor sits at the PIPELINE HEAD so no later processor (or renderer)
ever sees credential material. Trace correlation injects ``trace_id`` /
``span_id`` from the active OTel span so logs join traces in any backend.
"""

from __future__ import annotations

from typing import Any

import structlog
from opentelemetry.trace import get_current_span
from structlog.types import EventDict, WrappedLogger

from apps.observability.config import ObservabilityConfig


def scrub_secrets(config: ObservabilityConfig) -> Any:
    """Build the head-of-pipeline scrubbing processor (20 §5).

    Any event-dict key containing a configured marker (case-insensitive
    substring match) has its value replaced. Values are scrubbed
    recursively through nested dicts/lists/tuples so structured payloads
    cannot smuggle credentials past the top level.
    """

    markers = tuple(m.lower() for m in config.scrub_key_markers)
    replacement = config.scrub_replacement

    def _scrub_value(key: str, value: object) -> object:
        lowered = key.lower()
        if any(marker in lowered for marker in markers):
            return replacement
        if isinstance(value, dict):
            return {k: _scrub_value(str(k), v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            scrubbed = [_scrub_value(key, item) for item in value]
            return scrubbed if isinstance(value, list) else tuple(scrubbed)
        return value

    def _processor(
        logger: WrappedLogger, method_name: str, event_dict: EventDict
    ) -> EventDict:
        return {k: _scrub_value(str(k), v) for k, v in event_dict.items()}

    return _processor


def inject_trace_context(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Inject trace_id/span_id from the active OTel span (correlation)."""

    span_context = get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
    return event_dict


def build_processors(config: ObservabilityConfig) -> list[Any]:
    """The full pipeline, scrubbing FIRST (20 §5), JSON renderer last."""

    return [
        scrub_secrets(config),  # MUST stay at index 0 — security property
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        inject_trace_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(sort_keys=True),
    ]


def configure_logging(config: ObservabilityConfig) -> None:
    """Configure structlog globally (idempotent; composition root only)."""

    structlog.configure(
        processors=build_processors(config),
        wrapper_class=structlog.make_filtering_bound_logger(0),
        cache_logger_on_first_use=True,
    )
