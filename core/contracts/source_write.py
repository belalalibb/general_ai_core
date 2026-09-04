"""Typed request/result/refusal shapes for the bounded source-write primitive.

R169 A2. The write capability is a *separate* primitive from the reader and
follows INV-2: every refusal is returned as typed data carrying a
machine-readable ``code`` — never a bare exception crossing the tool boundary.

Precondition semantics
----------------------
* ``create``    – target must not exist; ``expected_sha256`` is ignored.
* ``overwrite`` – target must exist and ``expected_sha256`` is REQUIRED and
  must equal the SHA-256 of the current on-disk bytes.
* ``delete``    – target must exist and ``expected_sha256`` is REQUIRED and
  must match, exactly as for ``overwrite``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

from core.contracts.base import ContractModel

Sha256Hex = Annotated[str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]
RelPath = Annotated[str, Field(min_length=1, max_length=1024)]


class SourceWriteOp(StrEnum):
    """The closed set of write operations the primitive understands."""

    CREATE = "create"
    OVERWRITE = "overwrite"
    DELETE = "delete"


class SourceWriteRefusalCode(StrEnum):
    """Machine-readable refusal codes (INV-2)."""

    PATH_NOT_RELATIVE = "path_not_relative"
    PATH_OUTSIDE_ROOT = "path_outside_root"
    PATH_DENIED = "path_denied"
    FILE_EXISTS = "file_exists"
    FILE_MISSING = "file_missing"
    NOT_A_FILE = "not_a_file"
    PRECONDITION_REQUIRED = "precondition_required"
    PRECONDITION_MISMATCH = "precondition_mismatch"
    WRITE_TOO_LARGE = "write_too_large"
    OP_CAP_EXCEEDED = "op_cap_exceeded"
    CONTENT_REQUIRED = "content_required"
    IO_ERROR = "io_error"


class SourceWriteRequest(ContractModel):
    """Arguments accepted by the ``source.write`` tool."""

    op: SourceWriteOp
    path: RelPath
    content: str | None = None
    expected_sha256: Sha256Hex | None = None


class SourceWriteRefusal(ContractModel):
    """A refused write, returned as data."""

    ok: bool = False
    code: SourceWriteRefusalCode
    reason: str
    path: str


class SourceWriteResult(ContractModel):
    """A completed write."""

    ok: bool = True
    op: SourceWriteOp
    path: str
    bytes_written: int
    sha256: Sha256Hex | None
    previous_sha256: Sha256Hex | None = None
    ops_remaining: int
