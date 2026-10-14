"""ID helpers (PRD §4, §9.1)."""

import secrets
import string
from datetime import UTC, datetime

_ALPHABET = string.ascii_lowercase + string.digits


def _rand(n: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


def incident_id(now: datetime | None = None) -> str:
    """Return `inc_<yyyymmddhhmmss>_<4 chars>`."""
    now = now or datetime.now(UTC)
    return f"inc_{now:%Y%m%d%H%M%S}_{_rand(4)}"


def task_id() -> str:
    """Return `tk_<6 chars>`."""
    return f"tk_{_rand(6)}"


def checkin_id(resident_id: str, attempt: int) -> str:
    """Return `ck_<rid>_<attempt>`."""
    return f"ck_{resident_id}_{attempt}"


def voice_token() -> str:
    """Return a one-time voice session token `vs_...`."""
    return f"vs_{secrets.token_urlsafe(24)}"
