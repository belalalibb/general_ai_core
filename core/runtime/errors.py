"""Runtime port errors."""

from __future__ import annotations


class RuntimeCoordinationError(Exception):
    """Base class for runtime coordination failures."""


class UnknownStream(RuntimeCoordinationError):
    """Consume/ack referenced a stream or group that does not exist."""


class MessageNotPending(RuntimeCoordinationError):
    """Ack/dead-letter referenced a message not pending for that group."""


class LeaseNotHeld(RuntimeCoordinationError):
    """Release/renew by an owner that does not hold the lease (fencing)."""
