"""Single-worker guard (Phase 6 B2): a Postgres session-level advisory lock.

The worker takes the lock on a dedicated connection and keeps that connection open for its whole
life; Postgres releases the lock when the connection closes (process exit, crash, container
stop). A second copy (an accidental extra replica, or the new container during a redeploy
overlap) blocks here, polling, until the first copy is gone, so jobs never run twice.
SQLite (local dev/tests) has no advisory locks and needs none.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from sqlalchemy import Connection, Engine, text

log = logging.getLogger("edgefront.worker.lock")
LOCK_KEY = 0x45444746_574B5231 & 0x7FFFFFFFFFFFFFFF  # "EDGF" "WKR1"


class _NoLock:
    def close(self) -> None:
        return None


class WorkerLock:
    """The held lock. `close()` unlocks explicitly: closing a pooled SQLAlchemy connection only
    returns it to the pool, where a session-level advisory lock would stay held."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def close(self) -> None:
        try:
            self.conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            self.conn.commit()
        finally:
            self.conn.invalidate()  # never hand this session back to the pool
            self.conn.close()


def hold_worker_lock(
    engine: Engine,
    *,
    poll_seconds: float = 10.0,
    sleep: Callable[[float], None] = time.sleep,
    max_wait_seconds: float | None = None,
) -> WorkerLock | _NoLock:
    if engine.dialect.name != "postgresql":
        return _NoLock()
    conn = engine.connect()
    waited = 0.0
    while True:
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar_one()
        conn.commit()
        if got:
            log.info("worker lock acquired", extra={"lock_key": LOCK_KEY, "waited_s": waited})
            return WorkerLock(conn)
        if max_wait_seconds is not None and waited >= max_wait_seconds:
            conn.close()
            raise TimeoutError("another worker holds the lock")
        if waited == 0 or waited % 60 < poll_seconds:
            log.warning(
                "another worker holds the lock; waiting (jobs are not running here)",
                extra={"lock_key": LOCK_KEY, "waited_s": waited},
            )
        sleep(poll_seconds)
        waited += poll_seconds
