"""Publish modes for repository bindings (R169 A6 contract; INV-1).

The dev agent never pushes "by default": :class:`PublishMode` is a closed set,
``PULL_REQUEST`` is the default, and ``DIRECT_PUSH`` is selectable only when a
binding lists it explicitly in ``allowed_modes``. The read model
(:class:`PublishModesResponse`) mirrors the ``GET /v1/models`` posture: every
mode is listed, each with ``selectable`` and a machine-readable ``reason`` when
it is not — the UI binds to this list and never hard-codes it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from core.contracts.base import ContractModel


class PublishMode(StrEnum):
    """Closed set of ways a ``git.publish`` call may leave the local root."""

    DRY_RUN = "dry_run"
    LOCAL_COMMIT_ONLY = "local_commit_only"
    PULL_REQUEST = "pull_request"
    DIRECT_PUSH = "direct_push"


DEFAULT_PUBLISH_MODE: PublishMode = PublishMode.PULL_REQUEST

#: Modes a binding gets when none are configured — DIRECT_PUSH is never implied.
DEFAULT_ALLOWED_MODES: tuple[PublishMode, ...] = (
    PublishMode.DRY_RUN,
    PublishMode.LOCAL_COMMIT_ONLY,
    PublishMode.PULL_REQUEST,
)

#: Human-facing label + description per mode (the dropdown text).
PUBLISH_MODE_LABELS: dict[PublishMode, tuple[str, str]] = {
    PublishMode.DRY_RUN: ("Dry run", "Compute the diff; write nothing to the remote."),
    PublishMode.LOCAL_COMMIT_ONLY: (
        "Local commit only",
        "Commit in the binding's local root; never touch the remote.",
    ),
    PublishMode.PULL_REQUEST: (
        "Pull request",
        "Push a work branch and open a pull request against the bound branch.",
    ),
    PublishMode.DIRECT_PUSH: ("Direct push", "Push directly to the bound branch."),
}

#: Reason code when DIRECT_PUSH is listed but not selectable for a binding.
REASON_DIRECT_PUSH_NOT_ENABLED = "direct_push_not_enabled_for_binding"
#: Reason code for any other mode a binding excludes.
REASON_MODE_NOT_IN_BINDING = "mode_not_in_binding_allowed_modes"


class PublishModeOption(ContractModel):
    """One row of the publish-mode list."""

    id: PublishMode
    label: str
    description: str
    selectable: bool
    reason: str | None = None


class PublishModesResponse(ContractModel):
    """``GET /v1/dev/bindings/{binding_id}/publish-modes`` body."""

    binding_id: str
    default: PublishMode = DEFAULT_PUBLISH_MODE
    modes: list[PublishModeOption] = Field(default_factory=list)


def publish_mode_options(
    allowed: frozenset[PublishMode] | set[PublishMode],
) -> list[PublishModeOption]:
    """Enumerate every mode, marking selectability against ``allowed``."""
    options: list[PublishModeOption] = []
    for mode in PublishMode:
        label, description = PUBLISH_MODE_LABELS[mode]
        selectable = mode in allowed
        reason: str | None = None
        if not selectable:
            reason = (
                REASON_DIRECT_PUSH_NOT_ENABLED
                if mode is PublishMode.DIRECT_PUSH
                else REASON_MODE_NOT_IN_BINDING
            )
        options.append(
            PublishModeOption(
                id=mode, label=label, description=description, selectable=selectable, reason=reason
            )
        )
    return options


__all__ = [
    "DEFAULT_ALLOWED_MODES",
    "DEFAULT_PUBLISH_MODE",
    "PUBLISH_MODE_LABELS",
    "REASON_DIRECT_PUSH_NOT_ENABLED",
    "REASON_MODE_NOT_IN_BINDING",
    "PublishMode",
    "PublishModeOption",
    "PublishModesResponse",
    "publish_mode_options",
]
