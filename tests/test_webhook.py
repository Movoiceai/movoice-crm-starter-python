import time

import pytest

from .conftest import call_event, read_lead, set_calling, signed


def test_accepts_a_signed_call_completed_and_writes_the_outcome(client, data_dir):
    set_calling(data_dir)
    res = client.post("/movoice/webhook", **signed(call_event()))
    assert res.status_code == 200
    lead = read_lead(data_dir, "L-101")
    assert lead["status"] == "called"
    assert lead["lastResult"]["event"] == "call.completed"
    assert lead["lastResult"]["outcome"] == "answered"
    assert lead["lastResult"]["summary"] == "Wants Sat 11am visit"
    assert lead["lastResult"]["durationSeconds"] == 74


# Every row is a delivery that must be refused with 400 and change nothing.
REFUSED = [
    ("a signature made with another secret", {"secret": "whsec_someone_else"}),
    ("a body changed after signing", {"tamper": True}),
    ("a timestamp 10 minutes old (a replay)", {"timestamp": lambda: int(time.time()) - 600}),
    ("a timestamp 10 minutes in the future", {"timestamp": lambda: int(time.time()) + 600}),
]


@pytest.mark.parametrize("name,opts", REFUSED, ids=[r[0] for r in REFUSED])
def test_refuses(client, data_dir, name, opts):
    set_calling(data_dir)
    before = read_lead(data_dir, "L-101")
    opts = {k: (v() if callable(v) else v) for k, v in opts.items()}
    res = client.post("/movoice/webhook", **signed(call_event(), **opts))
    assert res.status_code == 400
    assert read_lead(data_dir, "L-101") == before


def test_refuses_a_delivery_with_no_signature_headers(client, data_dir):
    set_calling(data_dir)
    res = client.post("/movoice/webhook", json=call_event())
    assert res.status_code == 400
    assert read_lead(data_dir, "L-101")["status"] == "calling"


def test_handles_a_repeated_delivery_only_once(client, data_dir):
    set_calling(data_dir)
    first = client.post("/movoice/webhook", **signed(call_event(), delivery="dlv_same"))
    assert first.json()["status"] == "called"
    after_first = read_lead(data_dir, "L-101")

    # Same delivery id, different (validly signed) content: it must be skipped, not applied.
    repeat = client.post(
        "/movoice/webhook",
        **signed(call_event(event="call.failed", status="busy", summary=None), delivery="dlv_same"),
    )
    assert repeat.status_code == 200
    assert repeat.json()["duplicate"] is True
    assert read_lead(data_dir, "L-101") == after_first


def test_finds_the_lead_by_the_stored_call_id_without_context_data(client, data_dir):
    set_calling(data_dir, "test_call_only_id")
    event = call_event(id="test_call_only_id")
    del event["context_data"]
    client.post("/movoice/webhook", **signed(event))
    assert read_lead(data_dir, "L-101")["status"] == "called"


# What each call ending shows on the lead.
ENDINGS = [
    ("answered", {}, "called", "answered"),
    ("voicemail", {"answered_by": "voicemail"}, "called", "voicemail"),
    ("busy", {"event": "call.failed", "status": "busy"}, "not reached", "busy"),
    ("no answer", {"event": "call.failed", "status": "no-answer"}, "not reached", "no answer"),
    ("failed", {"event": "call.failed", "status": "failed"}, "failed", "failed"),
]


@pytest.mark.parametrize("name,fields,status,outcome", ENDINGS, ids=[e[0] for e in ENDINGS])
def test_shows_each_ending(client, data_dir, name, fields, status, outcome):
    set_calling(data_dir)
    client.post("/movoice/webhook", **signed(call_event(**fields)))
    lead = read_lead(data_dir, "L-101")
    assert (lead["status"], lead["lastResult"]["outcome"]) == (status, outcome)


def test_keeps_the_final_result_when_call_started_arrives_late(client, data_dir):
    set_calling(data_dir)
    client.post("/movoice/webhook", **signed(call_event()))
    client.post("/movoice/webhook", **signed(call_event(event="call.started", summary=None)))
    assert read_lead(data_dir, "L-101")["status"] == "called"


def test_ignores_a_late_event_from_an_older_call(client, data_dir):
    set_calling(data_dir, "test_call_newest")
    client.post("/movoice/webhook", **signed(call_event(id="test_call_older", event="call.failed", status="busy")))
    assert read_lead(data_dir, "L-101")["status"] == "calling"
