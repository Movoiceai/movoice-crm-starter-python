"""The Movoice CRM starter: a lead list, a "Call with AI" button and the webhook that writes results back.

    GET  /                     the page (app/static/index.html)
    GET  /api/leads            the leads, for the page
    POST /api/leads/{id}/call  calls.create with context_data {leadId, name}; stores the call id
    POST /movoice/webhook      verify, skip repeats, write the outcome on the lead

Run: uvicorn app.main:app --reload
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import movoice
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import leads as store
from .outcome import change_for
from .settings import MissingSettingError, movoice_client, require_env

load_dotenv()

app = FastAPI(title="Movoice CRM starter")
PAGE = Path(__file__).parent / "static" / "index.html"


@app.exception_handler(MissingSettingError)
async def missing_setting(_request: Request, err: MissingSettingError) -> JSONResponse:
    return JSONResponse({"error": str(err)}, status_code=500)


def get_movoice() -> Iterator[movoice.Movoice]:
    """The Movoice client for one request. Tests replace this dependency."""
    with movoice_client() as client:
        yield client


@app.get("/", include_in_schema=False)
def page() -> FileResponse:
    return FileResponse(PAGE)


@app.get("/api/leads")
def leads() -> dict:
    return {"leads": store.list_leads()}


@app.post("/api/leads/{lead_id}/call")
def call_lead(lead_id: str, client: movoice.Movoice = Depends(get_movoice)) -> JSONResponse:
    """The "Call with AI" button. context_data fills {name} in the agent's prompt and comes back as
    ``context_data`` on every webhook for this call, which is how the webhook finds the lead again."""
    lead = store.get_lead(lead_id)
    if lead is None:
        return JSONResponse({"error": "No lead with that id."}, status_code=404)

    try:
        call = client.calls.create(
            agent_id=require_env("MOVOICE_AGENT_ID"),
            phone_number=lead["phone"],
            context_data={"leadId": lead["id"], "name": lead["name"]},
            # One key per button press: a timed-out request is retried with the same key and Movoice
            # answers with the first call instead of dialling twice.
            idempotency_key=f"call-{lead['id']}-{uuid.uuid4()}",
        )
    except movoice.MovoiceError as err:
        # e.g. INSUFFICIENT_BALANCE, FORBIDDEN, INVALID_REQUEST. The message never contains your key.
        return JSONResponse({"error": err.message, "code": err.code}, status_code=502)

    updated = store.update_lead(
        lead["id"],
        lambda current: {
            "status": "calling",
            "callId": call["id"],
            "callAttempts": int(current.get("callAttempts") or 0) + 1,
            "lastResult": None,
        },
    )
    return JSONResponse({"lead": updated, "callId": call["id"], "livemode": call.get("livemode") is not False})


@app.post("/movoice/webhook")
async def movoice_webhook(request: Request) -> JSONResponse:
    """Movoice tells you how a call went. Register this address in
    Movoice › Settings › Developer › Webhooks (see the README)."""
    secret = (os.environ.get("MOVOICE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        return JSONResponse({"error": "MOVOICE_WEBHOOK_SECRET is not set."}, status_code=500)

    raw_body = await request.body()  # the exact bytes: parse only after verifying
    try:
        event = movoice.webhooks.verify(raw_body, request.headers, secret)
    except movoice.WebhookVerificationError as err:
        return JSONResponse({"error": str(err)}, status_code=400)

    delivery_id = request.headers.get("x-movoice-delivery") or event.get("event_id")
    if delivery_id and not store.remember_delivery(delivery_id):
        return JSONResponse({"ok": True, "duplicate": True})

    try:
        context = event.get("context_data") or {}
        lead_id = context.get("leadId") if isinstance(context, dict) else None
        all_leads = store.list_leads()
        target = next((l for l in all_leads if lead_id is not None and l["id"] == lead_id), None) or next(
            (l for l in all_leads if event.get("id") and l.get("callId") == event.get("id")), None
        )
        lead = store.update_lead(target["id"], lambda current: change_for(current, event)) if target else None
    except Exception:
        if delivery_id:
            store.forget_delivery(delivery_id)  # let Movoice's retry try again
        raise

    # No matching lead (a call placed from somewhere else): answer 200 so Movoice does not retry it.
    return JSONResponse({"ok": True, "leadId": lead and lead["id"], "status": lead and lead["status"]})
