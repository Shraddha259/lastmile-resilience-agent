"""One place to call Gemini (PRD §8 `genai.py`).

- `GENAI_MODE=fake` returns scripted outputs passed by the caller (tests, keyless local dev).
- `GENAI_MODE=real` calls the Gemini API with a per-process rate limiter (free tier),
  exponential backoff on 429, and a switch to GEMINI_FALLBACK_MODEL after two 404/5xx errors.
Callers treat any raised UpstreamModelError as "model unavailable" and fall back to policy.
"""

from __future__ import annotations

import asyncio
import heapq
import json
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.services import db
from app.util.errors import UpstreamModelError
from app.util.logging import get_logger

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class _RateLimiter:
    """Spaces requests evenly to stay under GEMINI_RPM (D-047).

    Slots are handed out one at a time by a single pump task, in order: priority requests
    (a live caller waiting on the result) before normal ones, then first come first served.
    A slot is only assigned when it is due, so a waiter cancelled while queued (for example a
    decision hitting AGENT_TIMEOUT_S) never uses one up.
    """

    def __init__(self) -> None:
        self._waiters: list[tuple[int, int, asyncio.Future[None]]] = []
        self._seq = 0
        self._last = float("-inf")
        self._interval = 0.0
        self._pump: asyncio.Task[None] | None = None

    async def wait(self, rpm: int, *, priority: bool = False) -> None:
        loop = asyncio.get_running_loop()
        self._interval = 60.0 / max(rpm, 1)
        fut: asyncio.Future[None] = loop.create_future()
        self._seq += 1
        heapq.heappush(self._waiters, (0 if priority else 1, self._seq, fut))
        if self._pump is None or self._pump.done() or self._pump.get_loop() is not loop:
            # Waiters from an earlier event loop (tests) can never be resolved here.
            self._waiters = [w for w in self._waiters if w[2].get_loop() is loop]
            heapq.heapify(self._waiters)
            self._pump = loop.create_task(self._run())
        await fut  # cancelling this marks the future cancelled; the pump skips it

    def _next_waiter(self) -> asyncio.Future[None] | None:
        while self._waiters:
            fut = self._waiters[0][2]
            if not fut.done():
                return fut
            heapq.heappop(self._waiters)  # cancelled while queued: drop without a slot
        return None

    async def _run(self) -> None:
        while self._next_waiter() is not None:
            delay = self._last + self._interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            fut = self._next_waiter()  # re-read: a priority request may have arrived meanwhile
            if fut is None:
                break
            heapq.heappop(self._waiters)
            self._last = time.monotonic()
            fut.set_result(None)


_limiter = _RateLimiter()
_client = None
# Last model error, reported by /api/health so the team can see why AI fell back.
last_error: dict[str, Any] = {}


def _get_client():
    global _client
    if _client is None:
        from google import genai

        s = get_settings()
        if s.GENAI_USE_VERTEX:
            _client = genai.Client(
                vertexai=True, project=s.GCP_PROJECT_ID, location=s.VERTEX_LOCATION
            )
        else:
            if not s.GEMINI_API_KEY:
                raise UpstreamModelError("GEMINI_API_KEY is not set (GENAI_MODE=real)")
            _client = genai.Client(api_key=s.GEMINI_API_KEY.get_secret_value())
    return _client


def get_live_client():
    """Client for the Live API: AI Studio key when LIVE_USE_AI_STUDIO (D-001), else shared."""
    from google import genai

    s = get_settings()
    if s.LIVE_USE_AI_STUDIO:
        if not s.GEMINI_API_KEY:
            raise UpstreamModelError("GEMINI_API_KEY is not set (live voice)")
        return genai.Client(api_key=s.GEMINI_API_KEY.get_secret_value())
    return _get_client()


def _status_code(exc: Exception) -> int | None:
    return getattr(exc, "code", None) or getattr(exc, "status_code", None)


async def generate_json[T: BaseModel](
    *,
    system: str,
    prompt: str,
    schema: type[T],
    fake: T | dict[str, Any] | None = None,
    model: str | None = None,
    priority: bool = False,
) -> tuple[T, str]:
    """Return a structured response validated against `schema`, plus the model ID used.

    In fake mode `fake` is returned as-is (validated). Raises UpstreamModelError on failure.
    `priority=True` (a live resident is waiting on the result) goes ahead of queued requests.
    """
    s = get_settings()
    if s.GENAI_MODE == "fake":
        if fake is None:
            raise UpstreamModelError("Fake GenAI has no scripted output for this call")
        db.STATS["llm_calls_fake"] += 1
        return schema.model_validate(fake if isinstance(fake, dict) else fake.model_dump()), "fake"

    from google.genai import types

    models = [model or s.GEMINI_AGENT_MODEL, s.GEMINI_FALLBACK_MODEL]
    errors_on_primary = 0
    attempt = 0
    while attempt < 5:
        current = models[0] if errors_on_primary < 2 else models[1]
        await _limiter.wait(s.GEMINI_RPM, priority=priority)
        try:
            db.STATS["llm_calls"] += 1
            resp = await _get_client().aio.models.generate_content(
                model=current,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.2,
                ),
            )
            data = resp.parsed if isinstance(resp.parsed, schema) else json.loads(resp.text)
            result = schema.model_validate(data)
            db.STATS["llm_ok"] += 1
            return result, current
        except (ValidationError, json.JSONDecodeError) as exc:
            db.STATS["llm_errors"] += 1
            last_error.update(model=current, code="INVALID_JSON", at=time.time())
            raise UpstreamModelError(f"Invalid JSON from model: {exc}") from exc
        except UpstreamModelError:
            raise
        except Exception as exc:  # SDK errors carry an HTTP code
            code = _status_code(exc)
            attempt += 1
            db.STATS["llm_errors"] += 1
            last_error.update(model=current, code=code, at=time.time())
            log.warning("genai error", extra={"model": current, "error_code": code})
            if code == 429:
                await asyncio.sleep(min(30, 2**attempt))
                continue
            if code == 404 or (isinstance(code, int) and code >= 500):
                if current == models[1]:
                    break
                errors_on_primary += 1
                continue
            raise UpstreamModelError(f"Model call failed: {type(exc).__name__}") from exc
    raise UpstreamModelError("Model unavailable after retries")
