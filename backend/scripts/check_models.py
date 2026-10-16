"""List the Gemini models your key can call, and check the configured ones exist.

Usage (key from backend/.env or the environment; it is never printed):
    cd backend && uv run python scripts/check_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google import genai  # noqa: E402

from app.config import get_settings  # noqa: E402


def main() -> int:
    s = get_settings()
    if not s.GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set (backend/.env or environment).")
        return 1
    client = genai.Client(api_key=s.GEMINI_API_KEY.get_secret_value())
    names = sorted(m.name.removeprefix("models/") for m in client.models.list())
    print(f"{len(names)} models available to this key")
    ok = True
    for var in ("GEMINI_AGENT_MODEL", "GEMINI_FALLBACK_MODEL", "GEMINI_LIVE_MODEL"):
        model = getattr(s, var)
        found = model in names
        ok &= found
        print(f"  {'OK     ' if found else 'MISSING'} {var}={model}")
    if not ok:
        print("Candidates:", ", ".join(n for n in names if "flash" in n or "live" in n))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
