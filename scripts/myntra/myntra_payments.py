"""Download the Myntra payments (every payout and its line-level breakup) of each account for a date
range by hand, with the bot's saved sessions. The same process as the Myntra SPF bot's daily run:
src/ultron/workings/myntra_spf/payments.py (the QUIRY payment export tool's method).

    python scripts/myntra/myntra_payments.py 2026-08-01 2026-10-30 "<out folder>" [MAIN DBCC FMCC]

Writes <out folder>/myntra-payments-TOTAL-<from>_to_<to>-<ACCOUNT>.csv. Read-only: no report is
requested.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from ultron.workings.myntra_spf.payments import account_payments  # noqa: E402
from ultron.workings.portals import myntra as mp  # noqa: E402
from ultron.workings.return_analysis.sources import env, myntra_portal  # noqa: E402

if __name__ == "__main__":
    start, end, out = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]), Path(sys.argv[3])
    for acc in sys.argv[4:] or list(mp.ACCOUNTS):
        try:
            portal = myntra_portal(acc)
            got = account_payments(portal, start, end, out / f"myntra-payments-TOTAL-{start}_to_{end}-{acc}.csv")
            mp.save_to_worker(env, portal.cookies(), acc)
            print(f"== {acc}: {got['payouts']} payouts, {got['rows']} rows; without line rows: "
                  f"{got['without_lines']} (Rs {got['missing_amount']:,})")
        except mp.SessionExpired as exc:
            print(f"== {acc}: session expired ({exc}) - log in again (scripts/myntra/README.md)")
