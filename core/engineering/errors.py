"""Typed refusals of the shared engineering engine (ADR-0012)."""

from __future__ import annotations


class EngineeringRefused(Exception):
    """The engine refused an act; ``reason`` is loggable data."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class WorkspaceRefused(EngineeringRefused):
    """A path or file operation was refused by the workspace jail."""


class CommandRefused(EngineeringRefused):
    """A command was refused before it ran (allowlist / cwd / timeout)."""


class GitRefused(EngineeringRefused):
    """A Git act was refused (bad ref, unconfigured remote, ...)."""


class AuthorizationRefused(EngineeringRefused):
    """No valid Admin authorization covers the requested act."""


__all__ = [
    "AuthorizationRefused",
    "CommandRefused",
    "EngineeringRefused",
    "GitRefused",
    "WorkspaceRefused",
]
