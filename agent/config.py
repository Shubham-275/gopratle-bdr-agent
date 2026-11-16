"""Tiny config layer: read env vars at call time (so tests/demo can override them)."""
import os

from dotenv import load_dotenv

load_dotenv()


def get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def get_int(name: str, default: int) -> int:
    try:
        return int(get(name, str(default)))
    except ValueError:
        return default
