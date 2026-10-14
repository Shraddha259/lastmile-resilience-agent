"""Time helpers, including simulation time scaling (PRD §4)."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def scaled(seconds: float, scale: float) -> float:
    """Compress a wait by the sim time scale, e.g. 120 s at scale 10 -> 12 s."""
    return seconds / max(scale, 0.001)
