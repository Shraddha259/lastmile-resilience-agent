"""D-047: the Gemini rate limiter puts live calls first and never wastes a cancelled wait's slot."""

import asyncio
import time

from app.config import get_settings
from app.models import CaseStatus
from app.services import classifier, genai

RPM = 600  # 0.1 s between slots keeps the tests fast


async def test_AC_8_live_call_request_goes_before_queued_ones():
    lim = genai._RateLimiter()
    order: list[str] = []

    async def wait(name: str, priority: bool) -> None:
        await lim.wait(RPM, priority=priority)
        order.append(name)

    queued = [asyncio.create_task(wait(f"sim-{i}", False)) for i in range(3)]
    await asyncio.sleep(0.01)  # sim-0 gets the first slot; sim-1 and sim-2 are queued
    live = asyncio.create_task(wait("live", True))
    await asyncio.gather(*queued, live)

    assert order == ["sim-0", "live", "sim-1", "sim-2"]


async def test_AC_8_cancelled_wait_does_not_use_a_slot():
    lim = genai._RateLimiter()
    await lim.wait(RPM)  # takes the first slot
    start = time.monotonic()
    timed_out = asyncio.create_task(lim.wait(RPM))  # e.g. a decision about to hit its timeout
    waiting = asyncio.create_task(lim.wait(RPM))
    await asyncio.sleep(0.01)
    timed_out.cancel()
    await waiting

    # The next slot (0.1 s) goes to `waiting`; before D-047 it waited for a second slot (0.2 s).
    assert time.monotonic() - start < 0.17


async def test_AC_8_slots_stay_spaced_by_rpm():
    lim = genai._RateLimiter()
    start = time.monotonic()
    for _ in range(4):
        await lim.wait(RPM)
    assert time.monotonic() - start >= 0.29  # first slot immediate, then 3 × 0.1 s


async def test_AC_8_classifier_passes_priority_to_genai(monkeypatch):
    seen: dict[str, object] = {}

    async def capture(**kwargs):
        seen.update(kwargs)
        return classifier.Classification.model_validate(kwargs["fake"]), "test-model"

    monkeypatch.setattr(get_settings(), "GENAI_MODE", "real")
    monkeypatch.setattr(genai, "generate_json", capture)
    transcript = [{"role": "resident", "text": "Water is coming in and I cannot walk"}]
    await classifier.classify(transcript, CaseStatus.NEEDS_EVACUATION, priority=True)

    assert seen["priority"] is True
