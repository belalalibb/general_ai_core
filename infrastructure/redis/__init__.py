"""Redis bindings for the core runtime ports (ADR-0003, ACCEPTED 2026-08-25).

Implements ``core.runtime.ports`` against redis-py asyncio:

- ``RedisQueue``     — Redis Streams + consumer groups (XADD/XREADGROUP/
                       XACK/XAUTOCLAIM), DLQ stream per 40 §4.7.
- ``RedisLeaseManager`` — SET NX PX + INCR fencing counter + Lua
                       compare-and-delete release (40 §4.4).
- ``RedisCache``     — tenant-scoped keys with PX TTL (never truth, 40 §5.1).
- ``RedisRateLimiter`` — fixed-window INCR+PEXPIRE counter (40 §4.5).

Core never imports this package (import-linter contract, same commit as the
dependency pin). Hermetic gates run against ``core.runtime.memory`` fakes;
these bindings are exercised against a real Redis when one is available.
"""

from infrastructure.redis.binding import (
    RedisCache,
    RedisLeaseManager,
    RedisQueue,
    RedisRateLimiter,
)

__all__ = [
    "RedisCache",
    "RedisLeaseManager",
    "RedisQueue",
    "RedisRateLimiter",
]
