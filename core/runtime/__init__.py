"""Runtime coordination ports — queue, lease, cache, rate limit (MVP Phase 3).

Spec anchors: 40 §4 (reliability rules), 40 §5.1 (Redis is NEVER a source of
truth). Core defines the semantics as ports; ``infrastructure/redis/`` binds
them per ADR-0003. In-memory fakes here keep the gates hermetic.
"""

from core.runtime.errors import (
    LeaseNotHeld,
    MessageNotPending,
    RuntimeCoordinationError,
    UnknownStream,
)
from core.runtime.memory import (
    InMemoryCache,
    InMemoryLeaseManager,
    InMemoryQueue,
    InMemoryRateLimiter,
)
from core.runtime.ports import (
    CachePort,
    Lease,
    LeasePort,
    QueueMessage,
    QueuePort,
    RateLimitPort,
)

__all__ = [
    "CachePort",
    "InMemoryCache",
    "InMemoryLeaseManager",
    "InMemoryQueue",
    "InMemoryRateLimiter",
    "Lease",
    "LeaseNotHeld",
    "LeasePort",
    "MessageNotPending",
    "QueueMessage",
    "QueuePort",
    "RateLimitPort",
    "RuntimeCoordinationError",
    "UnknownStream",
]
