from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

SECRET = "whsec_test_secret_for_the_starter"
SAMPLE = Path(__file__).resolve().parent.parent / "data" / "leads.sample.json"


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh copy of the 5 sample leads, used by the store through LEADS_DIR."""
    shutil.copyfile(SAMPLE, tmp_path / "leads.sample.json")
    shutil.copyfile(SAMPLE, tmp_path / "leads.json")
    monkeypatch.setenv("LEADS_DIR", str(tmp_path))
    monkeypatch.setenv("MOVOICE_WEBHOOK_SECRET", SECRET)
    return tmp_path


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    from app.main import app

    return TestClient(app)


def read_lead(data_dir: Path, lead_id: str) -> dict[str, Any]:
    return next(l for l in json.loads((data_dir / "leads.json").read_text()) if l["id"] == lead_id)


def set_calling(data_dir: Path, call_id: str = "test_call_abc", lead_id: str = "L-101") -> None:
    """Put the lead in the state the call route leaves it in: calling, with the call id stored."""
    leads = json.loads((data_dir / "leads.json").read_text())
    for lead in leads:
        if lead["id"] == lead_id:
            lead.update(status="calling", callId=call_id)
    (data_dir / "leads.json").write_text(json.dumps(leads))


def call_event(**fields: Any) -> dict[str, Any]:
    event = {
        "event_id": f"evt_{uuid.uuid4().hex}",
        "event": "call.completed",
        "id": "test_call_abc",
        "context_data": {"leadId": "L-101", "name": "Rahul Sharma"},
        "agent": {"id": "agent_1"},
        "call_id": "test_call_abc",
        "agent_id": "engine_1",
        "agent_name": "Your agent",
        "caller_phone": "+15555550111",
        "direction": "outbound",
        "duration_seconds": 74,
        "summary": "Wants Sat 11am visit",
        "timestamp": "sent-now",
        "livemode": False,
    }
    event.update(fields)
    return {k: v for k, v in event.items() if v is not None}


def signed(
    event: dict[str, Any],
    *,
    secret: str = SECRET,
    timestamp: Optional[int] = None,
    delivery: Optional[str] = None,
    tamper: bool = False,
) -> dict[str, Any]:
    """Keyword arguments for client.post(): a body and headers signed the way Movoice signs them."""
    body = json.dumps(event).encode()
    ts = str(timestamp if timestamp is not None else int(time.time()))
    sig = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {
        "content": body.replace(b"Wants", b"Hates") if tamper else body,
        "headers": {
            "content-type": "application/json",
            "x-movoice-timestamp": ts,
            "x-movoice-signature": f"sha256={sig}",
            "x-movoice-delivery": delivery or f"dlv_{uuid.uuid4()}",
        },
    }
