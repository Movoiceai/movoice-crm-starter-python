"""Turn a Movoice call webhook into what the CRM shows on the lead.

    call.started                           -> "in call"
    call.completed                         -> "called" · answered (or · voicemail)
    call.failed with status busy/no-answer -> "not reached" · busy / no answer
    call.failed otherwise                  -> "failed"
    call.missed                            -> "not reached" · missed
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .leads import Lead, now_iso


def outcome_of(event: Mapping[str, Any]) -> Optional[tuple[str, str]]:
    """(status, outcome) for an event, or None for an event this starter does not use."""
    name = event.get("event")
    if name == "call.started":
        return "in call", "in call"
    if name == "call.completed":
        return "called", "voicemail" if event.get("answered_by") == "voicemail" else "answered"
    if name == "call.failed":
        if event.get("status") == "busy":
            return "not reached", "busy"
        if event.get("status") == "no-answer":
            return "not reached", "no answer"
        return "failed", "failed"
    if name == "call.missed":
        return "not reached", "missed"
    return None


def change_for(lead: Lead, event: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """The fields to write on the lead for this event, or None to leave the lead as it is."""
    result = outcome_of(event)
    if result is None:
        return None
    call_id = event.get("id")

    # A late event for an older call must not overwrite the newest call's result.
    if call_id and lead.get("callId") and call_id != lead["callId"]:
        return None

    # call.started can arrive after call.completed (deliveries are not ordered): keep the final result.
    if event.get("event") == "call.started" and lead.get("status") != "calling":
        return None

    status, outcome = result
    duration = event.get("duration_seconds")
    fields: dict[str, Any] = {
        "status": status,
        "lastResult": {
            "event": event.get("event"),
            "outcome": outcome,
            "summary": event.get("summary"),
            "durationSeconds": duration if isinstance(duration, (int, float)) else None,
            "at": now_iso(),
        },
    }
    if call_id and not lead.get("callId"):
        fields["callId"] = call_id
    return fields
