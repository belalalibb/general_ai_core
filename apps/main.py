"""P-B — the ONE local-first entrypoint (Operator directive, Option A).

Run:  ``python3 -m apps.main``  (or ``uvicorn`` against the factory below).

Shape (verbatim the authorized recommendation): env → bindings →
``create_app`` → uvicorn, with the worker and outbox relay as in-process
asyncio background tasks on the SAME loop — they already share the
bus/outbox objects the profile composed. Smallest deployable unit: one
process serves the API, drains the outbox, and executes queued work.

Lifecycle (owner disposes — recorded posture):

- startup: spawn the relay loop and the worker loop (run_once cadence +
  periodic recover_once for crash-claimed messages).
- shutdown: cancel both tasks, dispose the engine ON THE BRIDGE LOOP
  (asyncpg connections are loop-bound — disposing from the server loop
  raised "attached to a different loop" in the live smoke; observed and
  fixed), then close the bridge (durable profile only).

Cadence numbers are composition DATA (41 §19 posture — no doc defines
them): 0.2s poll keeps local latency invisible while costing nothing
measurable; recovery every 5s with a 30s idle threshold mirrors the
proven core defaults' spirit. Change them here, never in core.

``create_runtime_app`` is a uvicorn FACTORY (composition happens at
call time, never at import time — hermetic imports stay side-effect
free): ``uvicorn --factory apps.main:create_runtime_app`` for operators
who prefer their own server flags; ``python3 -m apps.main`` runs the
same factory with our defaults (HOST/PORT env overridable).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from collections.abc import AsyncIterator

from fastapi import FastAPI

from apps.composition.runtime import RuntimeProfile, build_runtime_profile

__all__ = ["create_runtime_app", "main"]

#: Composition DATA — local cadence (see module docstring).
RELAY_POLL_SECONDS = 0.2
WORKER_POLL_SECONDS = 0.2
RECOVER_EVERY_SECONDS = 5.0
RECOVER_IDLE_MS = 30_000
_BATCH = 16


async def _relay_loop(profile: RuntimeProfile) -> None:
    """Drain the outbox onto the bus forever (40 §4.2 relay cadence)."""
    while True:
        relayed = await profile.relay.relay_once(max_records=_BATCH)
        if relayed == 0:
            await asyncio.sleep(RELAY_POLL_SECONDS)


async def _worker_loop(profile: RuntimeProfile) -> None:
    """Consume + process queued executions forever; recover stale claims."""
    last_recover = 0.0
    loop = asyncio.get_running_loop()
    while True:
        report = await profile.worker.run_once(max_messages=_BATCH)
        now = loop.time()
        if now - last_recover >= RECOVER_EVERY_SECONDS:
            await profile.worker.recover_once(RECOVER_IDLE_MS, max_messages=_BATCH)
            last_recover = now
        if not report.processed and not report.duplicates:
            await asyncio.sleep(WORKER_POLL_SECONDS)


def _startup_banner(profile: RuntimeProfile) -> None:
    """One structured line — facts only, never secrets (20 §5)."""
    banner = {
        "event": "runtime_started",
        "profile": "durable" if profile.durable else "in-memory",
        "providers": list(profile.provider_keys),
        "auth": "session (register/login)" if profile.demo_principal is None
        else "demo principal (in-memory profile)",
        "section_14_gate": "authoritative_applier=None (R3 NEVER active)",
    }
    if profile.demo_principal is not None:
        banner["demo_tenant_id"] = str(profile.demo_principal.tenant_id)
    print(json.dumps(banner), file=sys.stdout, flush=True)  # noqa: T201


def create_runtime_app(profile: RuntimeProfile | None = None) -> FastAPI:
    """Attach the background-task lifespan to the profile's app.

    ``profile`` is injectable for hermetic tests; production callers pass
    nothing and the profile composes from ``os.environ``.
    """
    runtime = profile if profile is not None else build_runtime_profile()
    inner_app = runtime.app

    @contextlib.asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        _startup_banner(runtime)
        relay_task = asyncio.create_task(_relay_loop(runtime), name="outbox-relay")
        worker_task = asyncio.create_task(_worker_loop(runtime), name="exec-worker")
        try:
            yield
        finally:
            for task in (worker_task, relay_task):
                task.cancel()
            for task in (worker_task, relay_task):
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            # S2: release pooled provider HTTP clients BEFORE the DB pool —
            # workers are stopped, so no in-flight provider call remains.
            await runtime.release_adapters()
            # Owner disposes (recorded posture) — and loop affinity holds
            # at shutdown too: the pool's connections live on the BRIDGE
            # loop, so dispose must run THERE (crossing via run_async),
            # and only then may the bridge close. Disposing on the server
            # loop raises "attached to a different loop" (observed live).
            if runtime.bridge is not None and runtime.bindings is not None:
                await runtime.bridge.run_async(runtime.bindings.engine.dispose())
                runtime.bridge.close()
            elif runtime.bindings is not None:  # pragma: no cover — durable
                await runtime.bindings.engine.dispose()  # implies a bridge

    # FastAPI accepts a router-level lifespan swap post-construction: the
    # app object was built injection-only by create_app; the RUNTIME owns
    # process lifecycle — exactly the composition-root division of labor.
    inner_app.router.lifespan_context = _lifespan
    return inner_app


def main() -> None:
    """Blocking entrypoint: compose from env and serve."""
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "apps.main:create_runtime_app",
        factory=True,
        host=host,
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
