"""Gateway configuration — env-driven; misconfiguration fails LOUD at startup.

No secrets appear in defaults, logs, or error messages. Explicit validation,
never ``assert`` (asserts are deleted under ``python -O``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GatewayConfig:
    """Immutable process configuration.

    secrets_by_version: dual-accept map {version: secret_value} (OPEN-7).
      During a rotation grace window the gateway accepts the CURRENT and
      PREVIOUS versions; the window length is OPERATIONAL CONFIGURATION
      (default 10 minutes), not domain identity.
    route_map: {route_token: internal_slug}. Reloadable without restart
      (route_registry). Provisioned OUT-OF-BAND only — no HTTP
      registration endpoint exists, by design.
    """

    secrets_by_version: dict[int, str]
    current_secret_version: int
    route_map: dict[str, str] = field(default_factory=dict)
    dual_accept_window_seconds: int = 600  # OPEN-7 initial value: 10 minutes
    disabled_slugs: frozenset[str] = frozenset()
    #: Epoch seconds when the current rotation began (OPEN-7). None =>
    #: window tracking not configured: a configured previous secret stays
    #: accepted (pre-G4 behavior, honest). When set, non-current versions
    #: expire at rotation_started_at + dual_accept_window_seconds.
    #: OPERATIONAL configuration — never domain identity.
    rotation_started_at: float | None = None

    def __repr__(self) -> str:
        """G4 leak fix: secret VALUES and route TOKENS never appear in repr.

        Dataclass auto-reprs reach logs and tracebacks; this repr carries
        only non-sensitive shape facts (versions, counts, window).
        """
        return (
            "GatewayConfig("
            f"secret_versions={sorted(self.secrets_by_version)}, "
            f"current_secret_version={self.current_secret_version}, "
            f"route_count={len(self.route_map)}, "
            f"dual_accept_window_seconds={self.dual_accept_window_seconds}, "
            f"disabled_count={len(self.disabled_slugs)}, "
            f"rotation_started_at={self.rotation_started_at}, "
            "secrets='[SCRUBBED]', route_tokens='[SCRUBBED]')"
        )

    def __post_init__(self) -> None:
        if not self.secrets_by_version:
            msg = "GatewayConfig: at least one gateway secret version is required"
            raise ValueError(msg)
        if self.current_secret_version not in self.secrets_by_version:
            msg = (
                "GatewayConfig: current_secret_version "
                f"{self.current_secret_version} not present in secrets_by_version"
            )
            raise ValueError(msg)
        for version, value in self.secrets_by_version.items():
            if version < 1:
                msg = "GatewayConfig: secret versions must be >= 1"
                raise ValueError(msg)
            if len(value) < 16:
                msg = "GatewayConfig: gateway secret must be at least 16 characters"
                raise ValueError(msg)
        if self.dual_accept_window_seconds < 0:
            msg = "GatewayConfig: dual_accept_window_seconds must be >= 0"
            raise ValueError(msg)
        if self.rotation_started_at is not None and self.rotation_started_at < 0:
            msg = "GatewayConfig: rotation_started_at must be >= 0 epoch seconds"
            raise ValueError(msg)


def load_config_from_env(environ: dict[str, str] | None = None) -> GatewayConfig:
    """Build config from environment variables. Missing/invalid = loud ValueError.

    GW_SECRET_CURRENT          current secret value    (required)
    GW_SECRET_CURRENT_VERSION  integer version         (required)
    GW_SECRET_PREVIOUS         previous secret value   (optional, rotation)
    GW_SECRET_PREVIOUS_VERSION integer version         (required if PREVIOUS set)
    GW_ROUTE_MAP               "token1:slug1,token2:slug2" (optional at boot)
    GW_DUAL_ACCEPT_WINDOW_S    seconds (optional, default 600 — OPEN-7)
    GW_ROTATION_STARTED_AT     epoch seconds the rotation began (optional;
                               set by the rotation runbook — enables window
                               EXPIRY for the previous secret version)
    """

    env = environ if environ is not None else dict(os.environ)

    current = env.get("GW_SECRET_CURRENT")
    current_version_raw = env.get("GW_SECRET_CURRENT_VERSION")
    if not current or not current_version_raw:
        msg = "GW_SECRET_CURRENT and GW_SECRET_CURRENT_VERSION are required"
        raise ValueError(msg)
    if not current_version_raw.isdigit():
        msg = "GW_SECRET_CURRENT_VERSION must be a positive integer"
        raise ValueError(msg)
    secrets_by_version = {int(current_version_raw): current}

    previous = env.get("GW_SECRET_PREVIOUS")
    previous_version_raw = env.get("GW_SECRET_PREVIOUS_VERSION")
    if previous is not None:
        if not previous_version_raw or not previous_version_raw.isdigit():
            msg = "GW_SECRET_PREVIOUS_VERSION (integer) is required with GW_SECRET_PREVIOUS"
            raise ValueError(msg)
        secrets_by_version[int(previous_version_raw)] = previous

    route_map: dict[str, str] = {}
    raw_map = env.get("GW_ROUTE_MAP", "")
    if raw_map:
        for pair in raw_map.split(","):
            token, sep, slug = pair.strip().partition(":")
            if not sep or not token or not slug:
                msg = "GW_ROUTE_MAP entries must be 'token:slug'"
                raise ValueError(msg)
            if token in route_map:
                msg = "GW_ROUTE_MAP: duplicate route token"
                raise ValueError(msg)
            route_map[token] = slug

    window_raw = env.get("GW_DUAL_ACCEPT_WINDOW_S", "600")
    if not window_raw.isdigit():
        msg = "GW_DUAL_ACCEPT_WINDOW_S must be a non-negative integer"
        raise ValueError(msg)

    rotation_started_raw = env.get("GW_ROTATION_STARTED_AT", "").strip()
    rotation_started_at: float | None = None
    if rotation_started_raw:
        try:
            rotation_started_at = float(rotation_started_raw)
        except ValueError as exc:
            msg = "GW_ROTATION_STARTED_AT must be epoch seconds (number)"
            raise ValueError(msg) from exc

    return GatewayConfig(
        secrets_by_version=secrets_by_version,
        current_secret_version=int(current_version_raw),
        route_map=route_map,
        dual_accept_window_seconds=int(window_raw),
        rotation_started_at=rotation_started_at,
    )
