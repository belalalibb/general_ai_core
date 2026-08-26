"""AdaptiveSampler — 40 §5.3 sampling policy (ADR-0004).

Policy: normal traffic → reduced rate; error / slow / high-value / debug →
full rate. Implemented as a head sampler over span-creation attributes,
composed under ``ParentBased(root=AdaptiveSampler(...))`` so an already-
sampled trace keeps all its children (and a dropped trace stays dropped).

Head sampling can only observe what is known at span creation. Errors and
latency discovered mid-span are the callers' responsibility to signal via
the configured attributes on the ROOT span (e.g. a retry loop re-entering a
high-value execution sets ``orchestration.error_expected``); tail-based
sampling at a collector can tighten this later without touching this code
(OTLP deferral, ADR-0004).
"""

from __future__ import annotations

from collections.abc import Sequence

from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import (
    Decision,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)
from opentelemetry.trace import Link, SpanKind, TraceState, get_current_span
from opentelemetry.util.types import Attributes

from apps.observability.config import ObservabilityConfig


class AdaptiveSampler(Sampler):
    """40 §5.3 adaptive policy as an OTel head sampler."""

    def __init__(self, config: ObservabilityConfig) -> None:
        self._config = config
        self._full_attributes = frozenset(
            {
                config.high_value_attribute,
                config.debug_attribute,
                config.error_attribute,
                config.slow_attribute,
            }
        )
        self._reduced = TraceIdRatioBased(config.normal_sample_ratio)

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        parent_span_context = get_current_span(parent_context).get_span_context()
        parent_trace_state = (
            parent_span_context.trace_state if parent_span_context.is_valid else None
        )

        if attributes:
            for key in self._full_attributes:
                if attributes.get(key):
                    return SamplingResult(
                        Decision.RECORD_AND_SAMPLE,
                        attributes,
                        parent_trace_state,
                    )

        # Normal traffic → reduced ratio (deterministic on trace id).
        return self._reduced.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )

    def get_description(self) -> str:
        return (
            "AdaptiveSampler(40 §5.3: error/slow/high-value/debug → full; "
            f"normal → TraceIdRatioBased({self._config.normal_sample_ratio}))"
        )
