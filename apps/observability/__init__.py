"""Observability composition root (MVP Phase 3, 41 §42 "OpenTelemetry setup").

Authority: engineering/adr/ADR-0004-observability-setup.md (ACCEPTED).

This package is the ONLY place the OpenTelemetry SDK and the structlog
pipeline are configured (composition-root rule). ``core/`` must not import
``opentelemetry`` or ``structlog`` — enforced by the 7th import-linter
contract in pyproject.toml.

Dev/test default to console/no-op exporters so all gates stay hermetic;
the OTLP exporter dependency is DEFERRED until a collector exists (per ADR).
The audit port (T-IMPL-014) is untouched: telemetry references audit event
ids only and never duplicates audit content.
"""

from apps.observability.config import ObservabilityConfig
from apps.observability.logs import build_processors, configure_logging, scrub_secrets
from apps.observability.metrics import build_meter_provider
from apps.observability.sampler import AdaptiveSampler
from apps.observability.setup import build_tracer_provider, configure_observability

__all__ = [
    "AdaptiveSampler",
    "ObservabilityConfig",
    "build_meter_provider",
    "build_processors",
    "build_tracer_provider",
    "configure_logging",
    "configure_observability",
    "scrub_secrets",
]
