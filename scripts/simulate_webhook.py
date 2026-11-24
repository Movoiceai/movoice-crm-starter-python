"""python -m scripts.simulate_webhook [--lead L-101] [--event call.completed] [--status busy] [--url ...]

Sends your local server a call webhook signed exactly the way Movoice signs one, so the whole loop
works before you have a real key or a public address:

    X-Movoice-Timestamp: <unix seconds>
    X-Movoice-Signature: sha256=<hex HMAC-SHA256(MOVOICE_WEBHOOK_SECRET, "<timestamp>.<raw body>")>
    X-Movoice-Delivery:  <a new id per delivery>

It signs with MOVOICE_WEBHOOK_SECRET from .env, the same secret the server checks with.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Send a signed sample Movoice webhook to your local server.")
    parser.add_argument("--lead", default="L-101")
    parser.add_argument("--event", default="call.completed")
    parser.add_argument("--status", help="for call.failed: busy, no-answer or failed (default busy)")
    parser.add_argument("--summary", default="Wants Sat 11am visit")
    parser.add_argument("--url", default=f"http://localhost:{os.environ.get('PORT', '8000')}/movoice/webhook")
    args = parser.parse_args()

    secret = (os.environ.get("MOVOICE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        print("MOVOICE_WEBHOOK_SECRET is not set. Run `cp .env.example .env` first.", file=sys.stderr)
        return 1

    # Use the call id the "Call with AI" button stored, so the event matches the lead's latest call.
    leads_file = DATA / "leads.json" if (DATA / "leads.json").exists() else DATA / "leads.sample.json"
    lead = next((l for l in json.loads(leads_file.read_text("utf-8")) if l["id"] == args.lead), None)
    if lead is None:
        print(f"No lead {args.lead} in {leads_file.name}.", file=sys.stderr)
        return 1

    call_id = lead.get("callId") or f"test_call_simulated_{uuid.uuid4().hex[:8]}"
    now = time.time()
    event = {
        "event_id": f"evt_{uuid.uuid4().hex}",
        "event": args.event,
        "id": call_id,
        "context_data": {"leadId": lead["id"], "name": lead["name"]},
        "agent": {"id": os.environ.get("MOVOICE_AGENT_ID") or "agent_simulated"},
        "call_id": call_id,
        "agent_id": "engine_agent_simulated",
        "agent_name": "Your agent",
        "caller_phone": lead["phone"],
        "direction": "outbound",
        "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat().replace("+00:00", "Z"),
        "livemode": False,
    }
    if args.event == "call.completed":
        event.update(duration_seconds=74, summary=args.summary, transcript=[])
    if args.event == "call.failed":
        event.update(status=args.status or "busy", duration_seconds=0)

    body = json.dumps(event).encode("utf-8")
    timestamp = str(int(now))
    signature = hmac.new(secret.encode("utf-8"), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()

    try:
        res = httpx.post(
            args.url,
            content=body,
            headers={
                "content-type": "application/json",
                "x-movoice-timestamp": timestamp,
                "x-movoice-signature": f"sha256={signature}",
                "x-movoice-delivery": f"dlv_{uuid.uuid4()}",
                "user-agent": "movoice-crm-starter/simulate-webhook",
            },
            timeout=10,
        )
    except httpx.HTTPError as err:
        print(f"Could not reach {args.url}. Is `uvicorn app.main:app` running? ({err})", file=sys.stderr)
        return 1

    print(f"Sent {args.event} for {lead['id']} ({lead['name']}) to {args.url}")
    print(f"Server answered {res.status_code}: {res.text}")
    return 0 if res.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
