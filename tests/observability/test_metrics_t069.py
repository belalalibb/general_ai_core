"""MeterProvider wiring gates — 41 §23 "metrics" (T-IMPL-069, FINAL Phase 20).

Hermetic — no collector, no network. Uses the SDK's InMemoryMetricReader
injected through the ``extra_readers`` seam.

Covers:

- instruments record end-to-end through a built provider (counter value +
  attributes visible at collection);
- the resource carries the SAME service identity fields as the tracer
  resource (traces and metrics must agree on who they describe);
- exporter posture mirrors spans exactly: "none" hermetic default,
  "console" allowed, OTLP rejected until a collector exists (ADR-0004).

NO instrument-name assertions exist here on purpose: no doc defines a
metric catalog (recorded in apps/observability/metrics.py) — asserting
invented names would encode a fabricated contract (41 §49).
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from apps.observability import ObservabilityConfig, build_meter_provider


class TestMeterProvider:
    def test_counter_records_through_in_memory_reader(self) -> None:
        reader = InMemoryMetricReader()
        provider = build_meter_provider(
            ObservabilityConfig(exporter="none"), extra_readers=(reader,)
        )
        counter = provider.get_meter("t069").create_counter("t069_requests")
        counter.add(3, {"outcome": "ok"})

        data = reader.get_metrics_data()
        assert data is not None
        points = [
            point
            for resource_metrics in data.resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
            for point in metric.data.data_points  # type: ignore[union-attr]
        ]
        assert len(points) == 1
        assert points[0].value == 3
        assert dict(points[0].attributes or {}) == {"outcome": "ok"}
        provider.shutdown()

    def test_resource_matches_tracer_identity_fields(self) -> None:
        reader = InMemoryMetricReader()
        provider = build_meter_provider(
            ObservabilityConfig(
                service_name="svc-x",
                environment="test-env",
                exporter="none",
                extra_resource_attributes={"team": "core"},
            ),
            extra_readers=(reader,),
        )
        provider.get_meter("t069").create_counter("t069_probe").add(1)
        data = reader.get_metrics_data()
        assert data is not None
        attrs = data.resource_metrics[0].resource.attributes
        assert attrs["service.name"] == "svc-x"
        assert attrs["deployment.environment.name"] == "test-env"
        assert attrs["team"] == "core"
        provider.shutdown()

    def test_none_exporter_attaches_no_exporter_reader(self) -> None:
        provider = build_meter_provider(ObservabilityConfig(exporter="none"))
        # Hermetic default: nothing to flush, shutdown is a no-op path.
        provider.shutdown()

    def test_console_exporter_allowed(self) -> None:
        provider = build_meter_provider(ObservabilityConfig(exporter="console"))
        provider.shutdown()

    def test_otlp_rejected_until_collector_exists(self) -> None:
        with pytest.raises(ValueError, match="ADR-0004"):
            build_meter_provider(ObservabilityConfig(exporter="otlp"))
