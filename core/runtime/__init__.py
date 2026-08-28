"""Runtime coordination — queue, lease, cache, rate limit, outbox, worker,
admission (MVP Phase 3 ports; FINAL Phase 10 async fabric, 41 §13).

Spec anchors: 40 §4 (reliability rules), 40 §5.1 (Redis is NEVER a source of
truth). Core defines the semantics as ports; ``infrastructure/redis/`` binds
them per ADR-0003. In-memory fakes here keep the gates hermetic.
"""

from core.runtime.admission import (
    AdmissionController,
    AdmissionDecision,
    ConcurrencyLimiter,
    FairScheduler,
    QueueDepthGauge,
)
from core.runtime.errors import (
    LeaseNotHeld,
    MessageNotPending,
    RecordNotPending,
    RuntimeCoordinationError,
    UnknownStream,
)
from core.runtime.memory import (
    InMemoryCache,
    InMemoryLeaseManager,
    InMemoryQueue,
    InMemoryRateLimiter,
)
from core.runtime.outbox import (
    InMemoryOutbox,
    OutboxPort,
    OutboxRecord,
    OutboxRelay,
)
from core.runtime.ports import (
    CachePort,
    Lease,
    LeasePort,
    QueueMessage,
    QueuePort,
    RateLimitPort,
)
from core.runtime.worker import (
    IdempotencyPort,
    InMemoryIdempotencyStore,
    PermanentTaskError,
    Worker,
    WorkerReport,
)

__all__ = [
    "AdmissionController",
    "AdmissionDecision",
    "CachePort",
    "ConcurrencyLimiter",
    "FairScheduler",
    "IdempotencyPort",
    "InMemoryCache",
    "InMemoryIdempotencyStore",
    "InMemoryLeaseManager",
    "InMemoryOutbox",
    "InMemoryQueue",
    "InMemoryRateLimiter",
    "Lease",
    "LeaseNotHeld",
    "LeasePort",
    "MessageNotPending",
    "OutboxPort",
    "OutboxRecord",
    "OutboxRelay",
    "PermanentTaskError",
    "QueueDepthGauge",
    "QueueMessage",
    "QueuePort",
    "RateLimitPort",
    "RecordNotPending",
    "RuntimeCoordinationError",
    "UnknownStream",
    "Worker",
    "WorkerReport",
]
