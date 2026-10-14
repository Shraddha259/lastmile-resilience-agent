"""Prompt templates (*.md) loaded by name."""

from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent


@lru_cache
def load_prompt(name: str) -> str:
    """Return the text of `agent/prompts/<name>`."""
    return (_DIR / name).read_text(encoding="utf-8")
