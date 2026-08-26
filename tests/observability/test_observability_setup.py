"""Observability composition-root gates (T-IMPL-017; 40 §5.3, ADR-0004).

Hermetic — no collector, no network. Uses in-memory span exporters and
direct processor invocation. Covers:

- AdaptiveSampler policy: error/slow/high-value/debug → full; normal →
  reduced deterministic ratio; ParentBased keeps child spans consistent.
- Secret scrubbing (20 §5): head-of-pipeline position, key-marker matching,
  recursive scrubbing through nested payloads.
- Trace correlation: trace_id/span_id injected inside an active span,
  absent outside one.
- Boundary: OTLP exporter rejected (deferred per ADR-0004); core purity is
  enforced separately by the import-linter contract.
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.sampling import Decision, ParentBased
from opentelemetry.trace import get_current_span

from apps.observability import (
    AdaptiveSampler,
    ObservabilityConfig,
    build_processors,
    build_tracer_provider,
    scrub_secrets,
)
from apps.observability.logs import inject_trace_context

# ---------------------------------------------------------------------------
# AdaptiveSampler policy (40 §5.3)
# ---------------------------------------------------------------------------


def _sample(sampler: AdaptiveSampler, trace_id: int, attributes: dict[str, Any]) -> Decision:
    result = sampler.should_sample(None, trace_id, "span", attributes=attributes)
    return result.decision


class TestAdaptiveSampler:
    def test_full_sampling_attributes_always_sampled(self) -> None:
        config = ObservabilityConfig(normal_sample_ratio=0.0)  # normal → drop
        sampler = AdaptiveSampler(config)
        for attr in (
            config.high_value_attribute,
            config.debug_attribute,
            config.error_attribute,
            config.slow_attribute,
        ):
            assert _sample(sampler, 12345, {attr: True}) is Decision.RECORD_AND_SAMPLE

    def test_falsy_flag_does_not_force_sampling(self) -> None:
        config = ObservabilityConfig(normal_sample_ratio=0.0)
        sampler = AdaptiveSampler(config)
        decision = _sample(sampler, 12345, {config.debug_attribute: False})
        assert decision is Decision.DROP

    def test_normal_traffic_reduced_ratio_deterministic(self) -> None:
        config = ObservabilityConfig(normal_sample_ratio=0.5)
        sampler = AdaptiveSampler(config)
        first = _sample(sampler, 777, {})
        assert all(_sample(sampler, 777, {}) is first for _ in range(5))

    def test_ratio_zero_drops_all_normal_traffic(self) -> None:
        sampler = AdaptiveSampler(ObservabilityConfig(normal_sample_ratio=0.0))
        assert all(_sample(sampler, tid, {}) is Decision.DROP for tid in range(1, 50))

    def test_ratio_one_samples_all_normal_traffic(self) -> None:
        sampler = AdaptiveSampler(ObservabilityConfig(normal_sample_ratio=1.0))
        assert all(
            _sample(sampler, tid, {}) is Decision.RECORD_AND_SAMPLE for tid in range(1, 50)
        )

    def test_parent_based_children_follow_sampled_root(self) -> None:
        config = ObservabilityConfig(normal_sample_ratio=0.0)
        exporter = InMemorySpanExporter()
        provider = TracerProvider(sampler=ParentBased(root=AdaptiveSampler(config)))
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        with tracer.start_as_current_span(
            "root-debug", attributes={config.debug_attribute: True}
        ):
            with tracer.start_as_current_span("child"):
                pass
        provider.shutdown()
        names = {span.name for span in exporter.get_finished_spans()}
        assert names == {"root-debug", "child"}

    def test_parent_based_children_follow_dropped_root(self) -> None:
        config = ObservabilityConfig(normal_sample_ratio=0.0)
        exporter = InMemorySpanExporter()
        provider = TracerProvider(sampler=ParentBased(root=AdaptiveSampler(config)))
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("test")

        with tracer.start_as_current_span("root-normal"):
            with tracer.start_as_current_span("child"):
                pass
        provider.shutdown()
        assert exporter.get_finished_spans() == ()

    def test_description_mentions_policy(self) -> None:
        sampler = AdaptiveSampler(ObservabilityConfig())
        assert "40 §5.3" in sampler.get_description()


# ---------------------------------------------------------------------------
# Secret scrubbing (20 §5)
# ---------------------------------------------------------------------------


class TestSecretScrubbing:
    def _scrub(self, event: dict[str, Any]) -> dict[str, Any]:
        config = ObservabilityConfig()
        processor = scrub_secrets(config)
        return cast(dict[str, Any], processor(None, "info", event))

    def test_marker_keys_scrubbed(self) -> None:
        out = self._scrub(
            {
                "event": "login",
                "password": "hunter2",
                "Api_Key": "abc",
                "AUTHORIZATION": "Bearer xyz",
                "refresh_token": "rrr",
            }
        )
        assert out["event"] == "login"
        for key in ("password", "Api_Key", "AUTHORIZATION", "refresh_token"):
            assert out[key] == "[SCRUBBED]"

    def test_nested_payloads_scrubbed_recursively(self) -> None:
        out = self._scrub(
            {
                "event": "call",
                "payload": {
                    "user": "u1",
                    "credentials": {"api_key": "k"},
                    "items": [{"session_key": "s"}, {"safe": "v"}],
                },
            }
        )
        assert out["payload"]["credentials"] == "[SCRUBBED]"  # key itself matches
        assert out["payload"]["items"][0]["session_key"] == "[SCRUBBED]"
        assert out["payload"]["items"][1]["safe"] == "v"
        assert out["payload"]["user"] == "u1"

    def test_scrubbing_is_pipeline_head(self) -> None:
        """Security property (20 §5): scrubbing MUST be processor index 0."""
        processors = build_processors(ObservabilityConfig())
        head = processors[0]
        scrubbed = head(None, "info", {"secret": "x", "ok": 1})
        assert scrubbed == {"secret": "[SCRUBBED]", "ok": 1}

    def test_full_pipeline_renders_scrubbed_json(self) -> None:
        processors = build_processors(ObservabilityConfig())
        event: dict[str, Any] = {"event": "e", "db_password": "p"}
        for processor in processors:
            event = processor(None, "info", event)  # type: ignore[assignment]
        rendered = json.loads(cast(str, event))
        assert rendered["db_password"] == "[SCRUBBED]"
        assert "hunter" not in cast(str, json.dumps(rendered))
        assert rendered["level"] == "info"
        assert "timestamp" in rendered


# ---------------------------------------------------------------------------
# Trace correlation
# ---------------------------------------------------------------------------


class TestTraceCorrelation:
    def test_ids_injected_inside_active_span(self) -> None:
        provider = TracerProvider()  # default always-on sampler
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("op"):
            span_context = get_current_span().get_span_context()
            out = inject_trace_context(None, "info", {"event": "e"})
            assert out["trace_id"] == format(span_context.trace_id, "032x")
            assert out["span_id"] == format(span_context.span_id, "016x")
        provider.shutdown()

    def test_no_ids_outside_span(self) -> None:
        out = inject_trace_context(None, "info", {"event": "e"})
        assert "trace_id" not in out
        assert "span_id" not in out


# ---------------------------------------------------------------------------
# Composition-root wiring / boundary
# ---------------------------------------------------------------------------


class TestCompositionRoot:
    def test_build_provider_none_exporter_has_no_processors(self) -> None:
        provider = build_tracer_provider(ObservabilityConfig(exporter="none"))
        # No span processors registered — nothing can leave the process.
        active = provider._active_span_processor._span_processors  # noqa: SLF001
        assert active == ()
        provider.shutdown()

    def test_build_provider_sets_resource_and_sampler(self) -> None:
        config = ObservabilityConfig(
            service_name="svc-x",
            environment="test",
            extra_resource_attributes={"custom.attr": "v"},
        )
        provider = build_tracer_provider(config)
        attrs = provider.resource.attributes
        assert attrs["service.name"] == "svc-x"
        assert attrs["deployment.environment.name"] == "test"
        assert attrs["custom.attr"] == "v"
        assert "AdaptiveSampler" in provider.sampler.get_description()
        provider.shutdown()

    def test_otlp_rejected_until_collector_exists(self) -> None:
        with pytest.raises(ValueError, match="ADR-0004"):
            build_tracer_provider(ObservabilityConfig(exporter="otlp"))

    def test_console_exporter_allowed(self) -> None:
        provider = build_tracer_provider(ObservabilityConfig(exporter="console"))
        active = provider._active_span_processor._span_processors  # noqa: SLF001
        assert len(active) == 1
        provider.shutdown()
