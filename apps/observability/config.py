"""Observability configuration (ADR-0004: policy thresholds live in config).

No secrets here (20 §5) — this is sampling policy + wiring switches only.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    """Composition-root observability settings.

    ``exporter`` selects the span exporter wiring:

    - ``"none"``  — no exporter at all (unit tests / fully hermetic gates)
    - ``"console"`` — stdout spans (local dev; still hermetic, no network)
    - ``"otlp"``  — REJECTED at runtime until the OTLP exporter dependency
      lands with a collector (ADR-0004 defers it); kept in the enum so the
      config shape is stable when it arrives.
    """

    service_name: str = "ai-orchestration-platform"
    environment: str = "dev"
    exporter: str = "none"

    # Adaptive sampling policy (40 §5.3): normal → reduced; error/slow/
    # high-value/debug → full.
    normal_sample_ratio: float = 0.1
    slow_threshold_ms: float = 2_000.0

    # Span attribute names that force full sampling when truthy at root
    # span creation time (head sampling can only see creation attributes;
    # errors/latency discovered later are handled by the error/slow flags
    # set by callers on child spans and by tail marking — see sampler doc).
    high_value_attribute: str = "orchestration.high_value"
    debug_attribute: str = "orchestration.debug"
    error_attribute: str = "orchestration.error_expected"
    slow_attribute: str = "orchestration.slow_expected"

    # structlog secret scrubbing (20 §5): keys matched case-insensitively
    # as substrings of the event-dict key.
    scrub_key_markers: tuple[str, ...] = (
        "secret",
        "password",
        "passwd",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "private_key",
        "session_key",
        "cookie",
    )
    scrub_replacement: str = "[SCRUBBED]"

    # Free-form resource attributes (tenant-safe only — never per-tenant or
    # per-user identifiers at resource level).
    extra_resource_attributes: dict[str, str] = field(default_factory=dict)
