"""Shared test setup. Settings are pinned here so tests never touch a real project or model."""

import os

os.environ.update(
    {
        "GCP_PROJECT_ID": "demo-lastmile",
        "FIRESTORE_EMULATOR_HOST": os.environ.get("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080"),
        "GENAI_MODE": "fake",
        "DEMO_PASSCODE": "test-passcode",
        "SIM_TIME_SCALE": "100",
        "LIVE_RING_TIMEOUT_S": "0.3",
        "FORCE_FALLBACK": "true",
        "AUTO_APPROVE_DISPATCH": "true",
        "RATE_LIMIT_PER_MIN": "1000",
        "LOG_LEVEL": "WARNING",
    }
)

import asyncio  # noqa: E402
import contextlib  # noqa: E402
import json  # noqa: E402
import socket  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

SEED = Path(__file__).resolve().parents[2] / "seed"


def _emulator_up() -> bool:
    host, port = os.environ["FIRESTORE_EMULATOR_HOST"].split(":")
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def _wipe(url: str) -> None:
    urllib.request.urlopen(urllib.request.Request(url, method="DELETE")).close()


def load_seed(name: str):
    return json.loads((SEED / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def residents() -> list[dict]:
    return load_seed("residents.json")


@pytest.fixture(scope="session")
def scenario_template() -> dict:
    return load_seed("scenario_flood_demo.json")


@pytest.fixture(scope="session")
def shelters_seed() -> list[dict]:
    return load_seed("shelters.json")


@pytest.fixture(scope="session")
def volunteers_seed() -> list[dict]:
    return load_seed("volunteers.json")


@pytest.fixture
async def fresh_db():
    """Wipe the emulator and load the seed. Skips if the emulator isn't running."""
    if not _emulator_up():
        pytest.skip("Firestore emulator not running (make emulators)")
    from app.services import db, worker

    # Let background jobs from the previous test finish: the emulator refuses to wipe
    # (409 Conflict) while one of them holds a transaction.
    for inc in list(worker._tasks):
        worker.cancel_incident(inc)
    with contextlib.suppress(TimeoutError):
        await worker.drain(limit_s=5)
    host = os.environ["FIRESTORE_EMULATOR_HOST"]
    url = f"http://{host}/emulator/v1/projects/demo-lastmile/databases/(default)/documents"
    for attempt in range(10):
        try:
            await asyncio.to_thread(_wipe, url)
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 409 or attempt == 9:
                raise
            await asyncio.sleep(0.3)
    worker.reset_state()
    db.STATS.clear()
    items = []
    client = db.get_db()
    items.append(
        (
            client.collection("scenarios").document("flood_demo"),
            load_seed("scenario_flood_demo.json"),
        )
    )
    for r in load_seed("residents.json"):
        items.append((db.resident_ref(r["resident_id"]), r))
    for s in load_seed("shelters.json"):
        items.append((db.shelter_ref(s["shelter_id"]), s))
    for v in load_seed("volunteers.json"):
        items.append((db.volunteer_ref(v["volunteer_id"]), v))
    for rid, d in load_seed("dialogues.json").items():
        items.append((client.collection("dialogues").document(rid), d))
    await db.batch_write(items)
    db.STATS.clear()
    yield client
    for inc in list(worker._tasks):
        worker.cancel_incident(inc)
    # Running jobs (e.g. the dispatch queued when a call ends) are not cancelled; let them
    # finish so the next test's emulator wipe doesn't hit open transactions (HTTP 409).
    for inc in list(worker._tasks):
        await worker.drain(inc, limit_s=10)
