"""SDK wiring at the composition root (ADR-0004).

The ONLY module that instantiates the OTel SDK ``TracerProvider``. Dev and
test default to console/no-op exporters — all gates stay hermetic; the OTLP
exporter is rejected until its dependency + a collector exist (per ADR).
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased

from apps.observability.config import ObservabilityConfig
from apps.observability.logs import configure_logging
from apps.observability.sampler import AdaptiveSampler


def build_tracer_provider(config: ObservabilityConfig) -> TracerProvider:
    """Build (but do not globally install) the TracerProvider.

    Kept separate from :func:`configure_observability` so tests can build
    isolated providers without mutating process-global state.
    """

    if config.exporter not in ("none", "console"):
        # OTLP (or anything else) is DEFERRED per ADR-0004: the exporter
        # dependency must not be added until a collector exists.
        raise ValueError(
            f"exporter '{config.exporter}' is not available: ADR-0004 defers "
            "OTLP until a collector exists; use 'none' or 'console'"
        )

    resource = Resource.create(
        {
            "service.name": config.service_name,
            "deployment.environment.name": config.environment,
            **config.extra_resource_attributes,
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(root=AdaptiveSampler(config)),
    )
    if config.exporter == "console":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    # "none": no exporter/processor — spans are sampled but not exported.
    return provider


def configure_observability(config: ObservabilityConfig) -> TracerProvider:
    """Full composition-root wiring: tracing + structlog. Call ONCE at app
    startup (e.g. FastAPI lifespan when the API app lands in its phase)."""

    provider = build_tracer_provider(config)
    trace.set_tracer_provider(provider)
    configure_logging(config)
    return provider
