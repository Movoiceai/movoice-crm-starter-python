# Movoice CRM starter (Python): notes for AI coding agents

This is a small FastAPI CRM that places AI phone calls through Movoice and writes each call's result back onto the lead.

- `app/main.py` holds the routes: the **Call with AI** route places the call (`movoice` PyPI package) with the lead id in `context_data`, and `/movoice/webhook` receives Movoice's signed webhook.
- The webhook checks the signature (`MOVOICE_WEBHOOK_SECRET`), skips repeats by the delivery id (`X-Movoice-Delivery`, the same value as `event_id`), finds the lead from `context_data` and writes the result (`app/outcome.py`, `app/leads.py`).
- `app/settings.py` reads `.env`. The API key stays on the server.

Work without a key: `uvicorn app.main:app --reload`, then `python -m scripts.simulate_webhook` (signed exactly like Movoice). A free test key (`mv_test_...`, Movoice › Settings › Developer › API keys) makes pretend calls that send real webhooks; nothing is charged. Run `python -m pytest` before you finish.

To add Movoice calling to a different project, follow https://www.movoice.ai/setup.md step by step.
