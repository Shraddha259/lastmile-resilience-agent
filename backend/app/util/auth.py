"""Demo passcode check for public write endpoints (PRD §11.1)."""

import hmac

from fastapi import Header

from app.config import get_settings
from app.util.errors import Unauthorized


async def require_passcode(x_demo_passcode: str | None = Header(default=None)) -> None:
    """FastAPI dependency: 401 unless `X-Demo-Passcode` matches DEMO_PASSCODE."""
    expected = get_settings().DEMO_PASSCODE.get_secret_value()
    if not x_demo_passcode or not hmac.compare_digest(x_demo_passcode, expected):
        raise Unauthorized("Missing or wrong demo passcode")
