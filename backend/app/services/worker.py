"""[P1] In-process asyncio worker (PRD §5.3, FR-19).

`enqueue()` is the only way to start background work. Job names and payloads match the
[P2] internal endpoints (INT-1..INT-6), so `TASKS_MODE=cloud` can swap in Cloud Tasks
without changing callers.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import get_settings
from app.util.logging import get_logger

log = get_logger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]
_registry: dict[str, Handler] = {}
_tasks: dict[str, set[asyncio.Task]] = defaultdict(set)
_seen: set[str] = set()
_waiting: set[asyncio.Task] = set()
_stopped: set[str] = set()
_checkin_sem: asyncio.Semaphore | None = None


def job(name: str) -> Callable[[Handler], Handler]:
    """Decorator registering a job handler under `name`."""

    def wrap(fn: Handler) -> Handler:
        _registry[name] = fn
        return fn

    return wrap


def checkin_semaphore() -> asyncio.Semaphore:
    """Caps simultaneous check-ins at MAX_CONCURRENT_CHECKINS."""
    global _checkin_sem
    if _checkin_sem is None:
        _checkin_sem = asyncio.Semaphore(get_settings().MAX_CONCURRENT_CHECKINS)
    return _checkin_sem


def enqueue(
    job_name: str, payload: dict[str, Any], delay_s: float = 0, dedupe_key: str | None = None
) -> bool:
    """Schedule `job_name(payload)` after `delay_s`. Returns False if `dedupe_key` was seen."""
    if get_settings().TASKS_MODE != "inline":
        raise NotImplementedError("TASKS_MODE=cloud is a [P2] feature")
    if job_name not in _registry:
        raise KeyError(f"Unknown job {job_name}")
    inc = payload.get("incident_id", "_global")
    if inc in _stopped:
        return False
    if dedupe_key:
        if dedupe_key in _seen:
            return False
        _seen.add(dedupe_key)
    task = asyncio.get_running_loop().create_task(_run(job_name, payload, delay_s))
    _tasks[inc].add(task)
    task.add_done_callback(lambda t: _tasks[inc].discard(t))
    return True


async def _run(job_name: str, payload: dict[str, Any], delay_s: float) -> None:
    inc = payload.get("incident_id", "_global")
    try:
        if delay_s > 0:
            task = asyncio.current_task()
            _waiting.add(task)
            try:
                await asyncio.sleep(delay_s)
            finally:
                _waiting.discard(task)
        if inc in _stopped:
            return
        await _registry[job_name](payload)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception(
            "job failed",
            extra={
                "job": job_name,
                "incident_id": payload.get("incident_id"),
                "resident_id": payload.get("resident_id"),
            },
        )


def cancel_incident(incident_id: str) -> int:
    """Kill switch: cancel every job still waiting to run and refuse new ones.

    Running jobs are not cancelled mid-flight (that would abandon open Firestore
    transactions); they check `is_stopped()` / the incident status and end quickly.
    Returns the number of jobs cancelled.
    """
    _stopped.add(incident_id)
    waiting = [t for t in _tasks.get(incident_id, ()) if t in _waiting]
    for t in waiting:
        t.cancel()
    return len(waiting)


def is_stopped(incident_id: str) -> bool:
    """True once the kill switch has been used for this incident in this process."""
    return incident_id in _stopped


def pending_count(incident_id: str | None = None) -> int:
    """Number of jobs not yet finished (for tests and health)."""
    if incident_id:
        return len(_tasks.get(incident_id, ()))
    return sum(len(v) for v in _tasks.values())


async def drain(incident_id: str | None = None, limit_s: float = 120) -> None:
    """Wait until no jobs remain (tests only)."""
    loop = asyncio.get_running_loop()
    end = loop.time() + limit_s
    while pending_count(incident_id):
        if loop.time() > end:
            raise TimeoutError(f"{pending_count(incident_id)} jobs still pending")
        await asyncio.sleep(0.05)


def reset_state() -> None:
    """Forget dedupe keys and the semaphore (tests and full resets)."""
    global _checkin_sem
    _seen.clear()
    _stopped.clear()
    _checkin_sem = None
