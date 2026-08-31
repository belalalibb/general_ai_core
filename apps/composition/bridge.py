"""Sync-over-async bridge — the ONE shared primitive for the P-A divide.

Why this exists (R138 reality-check, recorded): every app-level store
surface is SYNC (``apps/api/store.py``, ``core/memory/ports.py``, the
``core/sourcechange/store.py`` ports) while every V1 Postgres repository
is ASYNC (asyncpg).  P-A durability must let the EXISTING sync call
sites persist through the EXISTING async repositories without touching
either side (P2 — extend by injection, never rewrite call sites).

Design (P1 — fix once, benefit everywhere):

- ONE dedicated background thread runs its OWN asyncio event loop for
  the bridge's whole lifetime.  Repository coroutines are submitted with
  ``asyncio.run_coroutine_threadsafe`` and the CALLER thread blocks on
  the returned concurrent future.
- Safe from BOTH worlds: a plain sync caller simply blocks; a caller
  inside a RUNNING event loop (FastAPI handler) also works, because the
  submitted coroutine executes on the bridge's loop, never the caller's
  — there is no re-entrancy and no deadlock.  The caller's loop IS
  blocked for the DB round-trip: that is the recorded local-first
  tradeoff (R138) — durability lands without an async rewrite of the
  store surfaces; revisited only if evidence (latency under real load)
  demands it.
- Failures propagate verbatim: the awaited coroutine's exception is
  re-raised in the caller (named errors like ``ExecutionNotFound``
  cross the bridge unchanged — refusals stay data, 11 §14).

Lifecycle: ``close()`` stops the loop and joins the thread; the
composition root that builds a bridge owns shutting it down (same
posture as ``DatabaseBindings.engine`` — the binding owner disposes).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

_T = TypeVar("_T")

#: Guard against silent hangs: a repository call that exceeds this many
#: seconds raises loudly instead of blocking the caller forever.  Local
#: Postgres round-trips are milliseconds; 30s only trips on a genuinely
#: broken backend (named failure > silent freeze, P6).
_DEFAULT_TIMEOUT_S = 30.0


class BridgeClosed(RuntimeError):
    """The bridge was closed; no further submissions are accepted."""


class AsyncBridge:
    """Run coroutines on a dedicated background event loop, synchronously.

    One instance per composition (shared across all durable stores —
    one thread, one loop, one truth about how sync meets async here).
    """

    def __init__(self, *, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s
        self._loop = asyncio.new_event_loop()
        self._closed = False
        self._thread = threading.Thread(
            target=self._run_loop, name="composition-async-bridge", daemon=True
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro: Coroutine[Any, Any, _T]) -> _T:
        """Execute ``coro`` on the bridge loop; block; return its result.

        The coroutine's exception (if any) re-raises HERE, unchanged —
        named repository refusals cross the bridge as themselves.
        """
        if self._closed:
            # A closed bridge must not silently swallow work (P6) — and
            # the un-awaited coroutine must be closed to avoid a warning.
            coro.close()
            raise BridgeClosed("AsyncBridge is closed")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=self._timeout_s)

    def close(self) -> None:
        """Stop the loop and join the thread (idempotent)."""
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5.0)
        self._loop.close()

    def __enter__(self) -> AsyncBridge:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
