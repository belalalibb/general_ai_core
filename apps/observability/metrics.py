"""MeterProvider wiring — 41 §23 "OpenTelemetry: metrics" (FINAL Phase 20).

Contract authority:

- 41_IMPLEMENTATION_PLAN_AND_MVP.md §23 (Phase 20 lists the OpenTelemetry
  data types verbatim: ``logs / metrics / traces``) — logs and traces were
  wired in MVP Phase 3 (T-IMPL-017, ADR-0004); this module closes the
  remaining ``metrics`` line.
- 40_ENGINEERING_PROTOCOL.md §5.3 (Standard = OpenTelemetry; data types
  include metrics).
- engineering/adr/ADR-0004-observability-setup.md (ACCEPTED): the SDK
  packages are ``opentelemetry-api`` + ``opentelemetry-sdk`` — the metrics
  SDK ships INSIDE those already-accepted packages, so no new dependency
  is introduced here; the OTLP exporter stays DEFERRED until a collector
  exists (same rejection posture as spans in ``setup.py``).

Recorded derivations (explicit, no invention hidden):

- NO metric-instrument catalog is defined anywhere in the docs (41 §23 and
  40 §5.3 name the DATA TYPE only). This module therefore wires the
  MeterProvider at the composition root and STOPS — inventing counter/
  histogram names here would fabricate an observability contract (41 §49).
  Instruments belong to the surfaces that emit them, in their own phases,
  against whatever doc names them.
- Exporter selection mirrors ``build_tracer_provider`` exactly: ``"none"``
  (hermetic default — metrics are recordable but not exported), ``"console"``
  (local dev, no network), anything else rejected loudly per ADR-0004.
- Readers must be attached at construction time (SDK constraint — unlike
  span processors they cannot be added later), so tests inject an
  ``InMemoryMetricReader`` via ``extra_readers``.
- The Resource is built from the SAME config fields as the tracer resource
  so traces and metrics agree on service identity.
"""

from __future__ import annotations

from collections.abc import Sequence

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource

from apps.observability.config import ObservabilityConfig


def build_meter_provider(
    config: ObservabilityConfig,
    extra_readers: Sequence[MetricReader] = (),
) -> MeterProvider:
    """Build (but do not globally install) the MeterProvider.

    Kept separate from :func:`~apps.observability.setup.configure_observability`
    so tests can build isolated providers without mutating process-global
    state — the same split ``build_tracer_provider`` uses.
    """

    if config.exporter not in ("none", "console"):
        # Same ADR-0004 deferral as spans: OTLP (or anything else) is
        # rejected until the exporter dependency + a collector exist.
        raise ValueError(
            f"exporter '{config.exporter}' is not available: ADR-0004 defers "
            "OTLP until a collector exists; use 'none' or 'console'"
        )

    readers: list[MetricReader] = list(extra_readers)
    if config.exporter == "console":
        readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter()))
    # "none": no exporter-backed reader — instruments record, nothing leaves
    # the process (hermetic gates stay hermetic).

    resource = Resource.create(
        {
            "service.name": config.service_name,
            "deployment.environment.name": config.environment,
            **config.extra_resource_attributes,
        }
    )
    return MeterProvider(resource=resource, metric_readers=readers)
