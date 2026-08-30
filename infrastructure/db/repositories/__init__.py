"""Persistence repositories — contract↔row bindings (ADR-0002; Vision V1).

The repository layer is the missing X²-5 shared primitive (capability
assessment §11): the schema (infrastructure/db/tables.py, 12 migrations)
and the consumers (ports across core/ and the apps-level store protocols)
both exist — this package supplies the bindings between them.

Layer rules (enforced by import-linter, 12 contracts):

- infrastructure imports core contracts, never apps/providers.
- Each repository converts rows↔frozen contract models at the boundary
  (engine.py: ``expire_on_commit=False`` — no live ORM state escapes).
- Tenant isolation is structural (20 §6): every read is tenant-scoped
  in SQL; a foreign row and an absent row raise the SAME named error
  (anti-enumeration), and lists simply omit foreign rows.
"""

from infrastructure.db.repositories.audit import PostgresAuditLogRepository
from infrastructure.db.repositories.catalog import (
    PostgresModelCatalog,
    PostgresProviderCatalog,
    PostgresRoleCatalog,
    PostgresSkillCatalog,
)
from infrastructure.db.repositories.conversations import PostgresConversationRepository
from infrastructure.db.repositories.errors import (
    DuplicateIdempotencyKey,
    ExecutionNotFound,
    RepositoryError,
)
from infrastructure.db.repositories.executions import (
    ExecutionRecord,
    PostgresExecutionRepository,
)
from infrastructure.db.repositories.idempotency import PostgresIdempotencyStore
from infrastructure.db.repositories.memory import PostgresMemoryRepository
from infrastructure.db.repositories.outbox import PostgresOutbox
from infrastructure.db.repositories.usage import PostgresUsageRepository

__all__ = [
    "DuplicateIdempotencyKey",
    "ExecutionNotFound",
    "ExecutionRecord",
    "PostgresAuditLogRepository",
    "PostgresConversationRepository",
    "PostgresExecutionRepository",
    "PostgresIdempotencyStore",
    "PostgresMemoryRepository",
    "PostgresModelCatalog",
    "PostgresOutbox",
    "PostgresProviderCatalog",
    "PostgresRoleCatalog",
    "PostgresSkillCatalog",
    "PostgresUsageRepository",
    "RepositoryError",
]
