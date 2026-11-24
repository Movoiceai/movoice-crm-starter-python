"""The lead store: one JSON file, data/leads.json.

It is created from data/leads.sample.json the first time it is read, so your own changes never show
up in git. Swap this file for your real CRM or database: the routes only use the functions below.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

Lead = dict[str, Any]

#: How many webhook delivery ids to remember for de-duplication.
MAX_REMEMBERED_DELIVERIES = 1000

# One write at a time: every read-modify-write below holds this lock.
_lock = threading.RLock()


def data_dir() -> Path:
    """Where the files live. Tests point LEADS_DIR at a temporary folder."""
    return Path(os.environ.get("LEADS_DIR") or Path(__file__).resolve().parent.parent / "data")


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return fallback


def _write_json(path: Path, value: Any) -> None:
    """Write a temporary file first, then rename, so a crash never leaves half a file."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", "utf-8")
    os.replace(tmp, path)


def _load() -> list[Lead]:
    leads = _read_json(data_dir() / "leads.json", None)
    if leads is not None:
        return leads
    sample = _read_json(data_dir() / "leads.sample.json", [])
    _write_json(data_dir() / "leads.json", sample)
    return sample


def list_leads() -> list[Lead]:
    with _lock:
        return _load()


def get_lead(lead_id: str) -> Optional[Lead]:
    return next((lead for lead in list_leads() if lead["id"] == lead_id), None)


def update_lead(lead_id: str, change: Callable[[Lead], Optional[dict[str, Any]]]) -> Optional[Lead]:
    """Change one lead. ``change`` returns the new fields, or None to leave it as it is.

    Returns the lead after the change, or None when there is no lead with that id.
    """
    with _lock:
        leads = _load()
        for i, lead in enumerate(leads):
            if lead["id"] != lead_id:
                continue
            fields = change(lead)
            if not fields:
                return lead
            leads[i] = {**lead, **fields, "updatedAt": now_iso()}
            _write_json(data_dir() / "leads.json", leads)
            return leads[i]
        return None


def remember_delivery(delivery_id: str) -> bool:
    """Remember a webhook delivery id. False when it was already seen, so the caller skips a repeat:
    Movoice retries a delivery until it gets a 2xx, and a retry carries the same id."""
    with _lock:
        path = data_dir() / "deliveries.json"
        seen: list[str] = _read_json(path, [])
        if delivery_id in seen:
            return False
        seen.append(delivery_id)
        _write_json(path, seen[-MAX_REMEMBERED_DELIVERIES:])
        return True


def forget_delivery(delivery_id: str) -> None:
    """Forget a delivery id again, when handling it failed and Movoice should be able to retry it."""
    with _lock:
        path = data_dir() / "deliveries.json"
        _write_json(path, [d for d in _read_json(path, []) if d != delivery_id])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
