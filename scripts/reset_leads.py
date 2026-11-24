"""python -m scripts.reset_leads: put data/leads.json back to the 5 sample leads and forget seen deliveries."""

import shutil
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

shutil.copyfile(DATA / "leads.sample.json", DATA / "leads.json")
(DATA / "deliveries.json").unlink(missing_ok=True)
print("data/leads.json is back to the 5 sample leads.")
