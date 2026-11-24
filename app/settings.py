"""Settings from .env, and the Movoice client. Server only: the secret key never reaches the page."""

from __future__ import annotations

import os

from movoice import Movoice


class MissingSettingError(Exception):
    pass


def require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise MissingSettingError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


def movoice_client() -> Movoice:
    """A FastAPI dependency, so tests can swap in a client whose network is faked."""
    return Movoice(
        require_env("MOVOICE_API_KEY"),
        base_url=(os.environ.get("MOVOICE_BASE_URL") or "").strip() or "https://app.movoice.ai",
    )
