"""Runtime coordination ports — queue, lease, cache, rate limit (MVP Phase 3).

Spec anchors: 40 §4 (reliability rules), 40 §5.1 (Redis is NEVER a source of
truth). Core defines the semantics as ports; ``infrastructure/redis/``
binds them per ADR-0003. In-memory fakes here keep gates hermetic.
"""
