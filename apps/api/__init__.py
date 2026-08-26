"""API composition root (MVP Phase 5 slice 3, T-IMPL-023; 41 §44; 10 §2-§5).

FastAPI is confined to this package per ADR-0001 — the import-linter
contract in pyproject.toml keeps core/ and providers/ framework-free.
"""

from apps.api.app import Principal, create_app
from apps.api.errors import HTTP_STATUS_BY_CODE, error_response, execution_failure_detail
from apps.api.store import ExecutionNotFound, InMemoryExecutionStore

__all__ = [
    "HTTP_STATUS_BY_CODE",
    "ExecutionNotFound",
    "InMemoryExecutionStore",
    "Principal",
    "create_app",
    "error_response",
    "execution_failure_detail",
]
