import json
import time

import httpx
import movoice
import pytest

from app.main import app, get_movoice

from .conftest import read_lead


@pytest.fixture
def movoice_api(monkeypatch):
    """The real movoice client, with its network replaced: records each request, answers like the API."""
    monkeypatch.setenv("MOVOICE_AGENT_ID", "agent_123")
    sent: list[httpx.Request] = []
    reply = {
        "status": 200,
        "json": {
            "success": True,
            "data": {
                "id": "test_call_xyz",
                "agentId": "agent_123",
                "phoneNumber": "+15555550111",
                "status": "initiated",
                "startedAt": int(time.time() * 1000),
                "contextData": {"leadId": "L-101", "name": "Rahul Sharma"},
                "livemode": False,
            },
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(reply["status"], json=reply["json"])

    fake = movoice.Movoice(
        "mv_test_unit_tests_only",
        base_url="https://testing.movoice.ai",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    app.dependency_overrides[get_movoice] = lambda: fake
    yield sent, reply
    app.dependency_overrides.clear()


def test_calls_the_lead_with_context_data_lead_id_and_stores_the_call_id(client, data_dir, movoice_api):
    sent, _ = movoice_api
    res = client.post("/api/leads/L-101/call")
    assert res.status_code == 200

    assert len(sent) == 1
    request = sent[0]
    assert request.method == "POST"
    assert str(request.url) == "https://testing.movoice.ai/api/v1/calls"
    assert request.headers["authorization"] == "Bearer mv_test_unit_tests_only"
    assert request.headers["idempotency-key"].startswith("call-L-101-")
    assert json.loads(request.content) == {
        "agentId": "agent_123",
        "phoneNumber": "+15555550111",
        "contextData": {"leadId": "L-101", "name": "Rahul Sharma"},
    }

    lead = read_lead(data_dir, "L-101")
    assert (lead["status"], lead["callId"], lead["callAttempts"]) == ("calling", "test_call_xyz", 1)


def test_unknown_lead_is_404_and_calls_nobody(client, data_dir, movoice_api):
    sent, _ = movoice_api
    assert client.post("/api/leads/L-999/call").status_code == 404
    assert sent == []


def test_passes_movoice_refusal_back_and_leaves_the_lead(client, data_dir, movoice_api):
    _, reply = movoice_api
    reply["status"] = 402
    reply["json"] = {"success": False, "error": {"code": "INSUFFICIENT_BALANCE", "message": "Your balance is empty."}}
    res = client.post("/api/leads/L-101/call")
    assert res.status_code == 502
    assert res.json()["code"] == "INSUFFICIENT_BALANCE"
    lead = read_lead(data_dir, "L-101")
    assert (lead["status"], lead["callId"]) == ("new", None)


def test_says_which_setting_is_missing(client, data_dir, monkeypatch):
    monkeypatch.delenv("MOVOICE_API_KEY", raising=False)
    res = client.post("/api/leads/L-101/call")
    assert res.status_code == 500
    assert "MOVOICE_API_KEY" in res.json()["error"]
