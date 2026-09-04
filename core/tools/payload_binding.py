"""Canonical payload hashing for approval binding (R172 C6).

Pure functions, no I/O. The dev surface calls :func:`check_payload_binding`
BEFORE the gate for write-class permissions when the composition enables
``payload_binding``. The gate itself (``core/tools/gate.py``) is untouched.

Canonical form: ``json.dumps(payload, sort_keys=True, separators=(",", ":"),
ensure_ascii=False, allow_nan=False)`` encoded as UTF-8, after a recursive
type check that rejects floats (no stable textual form across producers),
non-string dict keys and any non-JSON value. ``bool``/``int``/``str``/``None``
scalars, ``list``/``tuple`` sequences and ``dict`` objects are accepted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from core.contracts.approval_binding import ApprovalBindingRefusalCode

__all__ = [
    "NonCanonicalPayload",
    "canonical_json",
    "check_payload_binding",
    "payload_hash",
]


class NonCanonicalPayload(ValueError):
    """The payload contains a value with no canonical JSON form."""


def _check(value: Any, path: str) -> None:
    if value is None or isinstance(value, bool | int | str):
        return
    if isinstance(value, float):
        msg = f"float at {path or '$'} has no canonical form"
        raise NonCanonicalPayload(msg)
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                msg = f"non-string key at {path or '$'}"
                raise NonCanonicalPayload(msg)
            _check(item, f"{path}.{key}")
        return
    if isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _check(item, f"{path}[{index}]")
        return
    msg = f"unsupported type {type(value).__name__} at {path or '$'}"
    raise NonCanonicalPayload(msg)


def canonical_json(payload: Any) -> bytes:
    """Return the canonical UTF-8 JSON bytes of ``payload``.

    Raises :class:`NonCanonicalPayload` for floats, non-string keys or values
    outside the JSON model.
    """
    _check(payload, "")
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return text.encode("utf-8")


def payload_hash(payload: Any) -> str:
    """sha256 hex digest of :func:`canonical_json`."""
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def check_payload_binding(
    *, payload: Any, approved_hash: str | None
) -> ApprovalBindingRefusalCode | None:
    """Return the refusal code, or ``None`` when the payload matches the approval.

    Order: canonicalisation first (a non-canonicalisable payload is refused
    regardless of the hash supplied), then a missing hash, then the compare.
    """
    try:
        actual = payload_hash(payload)
    except NonCanonicalPayload:
        return ApprovalBindingRefusalCode.PAYLOAD_NOT_CANONICALISABLE
    if approved_hash is None:
        return ApprovalBindingRefusalCode.APPROVAL_HASH_REQUIRED
    if not hmac.compare_digest(actual, approved_hash):
        return ApprovalBindingRefusalCode.APPROVAL_PAYLOAD_MISMATCH
    return None
