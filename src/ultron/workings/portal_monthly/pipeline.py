"""Portal reports (the 2nd of every month): last month's order and payment reports of every portal,
1st to last day, into Drive AGENT WORK/PORTAL REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/ as
"<PORTAL> [<ACCOUNT>] ORDER REPORT <MON-YY>" / "... PAYMENT REPORT <MON-YY>" (core/portal_reports.py).
The month's return reports follow on the 10th (and the fresh second try on the 15th) from the
return analysis, when the month's returns have come in.

  * Myntra MAIN / DBCC / FMCC: Seller_Orders_Report (report 4) for exactly the month (a job already
    on the portal for those dates is reused, else one is asked for: owner's rule, 1 Nov 2026), and
    the payments of the month (every payout and its line rows, myntra_spf/payments.py).
  * AJIO: the Dropship order report of the month, and the SRM statement of accounts (the AJIO
    ledger: G4 payments, reversals) of the month.
  * Flipkart: the report centre's "Orders" report (Fulfilment Reports) and "Settled Transactions"
    (Payment Reports) of the month.

A part that fails is named on Telegram and the others are saved; a run again replaces the files.
"""
from __future__ import annotations

import argparse
import calendar
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from ..core import portal_reports as pr
from ..core import telegram
from ..core.app import run_bot
from ..core.config import env, num

log = logging.getLogger("bindal.portal_reports")

MYNTRA_ACCOUNTS = ("MAIN", "DBCC", "FMCC")


def report_month(value: str, today: date) -> date:
    """YYYY-MM, else last month."""
    if value:
        y, m = value.split("-")
        return date(int(y), int(m), 1)
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


def myntra_orders(account: str, first: date, last: date, dest: Path) -> Path:
    from ..portals import myntra as mp
    from ..return_analysis.sources import myntra_portal
    portal = myntra_portal(account)
    job = portal.ensure(mp.REPORT_ID, first, last)
    name, data = portal.collect_or_regenerate(job, int(num("RETURNS_WAIT_MINUTES", 45)))
    mp.save_to_worker(env, portal.cookies(), account)
    path = dest / f"{account}_orders{Path(name).suffix or '.csv'}"
    path.write_bytes(data)
    return path


def myntra_payments(account: str, first: date, last: date, dest: Path) -> Path:
    from ..myntra_spf.payments import account_payments
    from ..portals import myntra as mp
    from ..return_analysis.sources import myntra_portal
    portal = myntra_portal(account)
    path = dest / f"{account}_payments.csv"
    got = account_payments(portal, first, last, path)
    mp.save_to_worker(env, portal.cookies(), account)
    log.info("Myntra %s payments %s..%s: %s", account, first, last, got)
    return path


def ajio_orders(first: date, last: date, dest: Path) -> Path:
    from ..portals.ajio import AjioClient
    user, pwd = env("AJIO_USERNAME"), env("AJIO_PASSWORD")
    if not user or not pwd:
        raise RuntimeError("AJIO_USERNAME / AJIO_PASSWORD not set")
    ajio = AjioClient(user, pwd)
    ajio.login()
    path = dest / "ajio_orders.xlsx"
    path.write_bytes(ajio.order_report(first, last))
    return path


def ajio_payments(first: date, last: date, dest: Path) -> Path:
    from ..ajio_spf.inputs import write_xlsx
    from ..portals.srm import PAYMENT_COLUMNS, Srm, payment_rows
    if not env("SRM_USERNAME") or not env("SRM_PASSWORD"):
        raise RuntimeError("SRM_USERNAME / SRM_PASSWORD not set")
    srm = Srm(env("SRM_USERNAME"), env("SRM_PASSWORD"))
    srm.login()
    rows = payment_rows(srm.statement(first, last))
    if not rows:
        raise RuntimeError(f"SRM statement {first}..{last} has no lines")
    path = dest / "ajio_payments.xlsx"
    write_xlsx(path, {"Sheet1": (list(PAYMENT_COLUMNS), rows)})
    return path


def flipkart_report(report: str, first: date, last: date, dest: Path) -> Path:
    """A report centre report for exactly the month: "Orders" (Fulfilment Reports, the order
    report the owner downloads by hand) or "Settled Transactions" (Payment Reports: every
    transaction settled in the range - orders, SPF, TDS, storage, recall)."""
    from ..return_analysis.sources import flipkart_client
    fk = flipkart_client()
    name, data = fk.report(report, first, last, int(num("RETURNS_WAIT_MINUTES", 45)))
    path = dest / f"flipkart_{report.lower().replace(' ', '_')}{Path(name).suffix or '.xlsx'}"
    path.write_bytes(data)
    return path


def run(args) -> int:
    month = report_month(args.month, date.today())
    first, last = month, month.replace(day=calendar.monthrange(month.year, month.month)[1])
    if last >= date.today():
        raise ValueError(f"{pr.label(month)} is not over yet: its reports come on the 2nd of the next month")
    log.info("Portal reports %s: %s..%s", pr.label(month), first, last)
    # (portal, account, kind) -> (function, arguments)
    tasks = {}
    for a in MYNTRA_ACCOUNTS:
        tasks[("MYNTRA", a, "sale")] = (myntra_orders, (a, first, last))
        tasks[("MYNTRA", a, "payment")] = (myntra_payments, (a, first, last))
    tasks[("AJIO", "", "sale")] = (ajio_orders, (first, last))
    tasks[("AJIO", "", "payment")] = (ajio_payments, (first, last))
    tasks[("FLIPKART", "", "sale")] = (flipkart_report, ("Orders", first, last))
    tasks[("FLIPKART", "", "payment")] = (flipkart_report, ("Settled Transactions", first, last))
    only = {p.strip().upper() for p in (args.portals or "").split(",") if p.strip()}
    tasks = {k: v for k, v in tasks.items() if not only or k[0] in only}
    work = Path(tempfile.mkdtemp(prefix="portal_reports_"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {}
        for key, (fn, a) in tasks.items():
            dest = work / "_".join(p for p in key if p)
            dest.mkdir(parents=True, exist_ok=True)
            futures[key] = pool.submit(fn, *a, dest)
    saved, failed = [], []
    for (portal, account, kind), fut in futures.items():
        what = f"{portal} {account} {pr.KINDS[kind]}".replace("  ", " ")
        try:
            path = fut.result()
            name = path.name if args.no_upload else pr.save(portal, month, kind, path, account)
            saved.append(name or what)
        except Exception as exc:  # noqa: BLE001 - one part never stops the others
            log.exception("%s failed", what)
            failed.append((what, (str(exc).splitlines() or [type(exc).__name__])[0][:150]))
    lines = [f"🗂 <b>Portal reports {pr.label(month)}</b>",
             f"<i>{first:%d %b} to {last:%d %b %Y}, Drive AGENT WORK/PORTAL REPORTS</i>", ""]
    lines += [f"✅ {telegram.esc(n)}" for n in saved]
    lines += [f"❌ {telegram.esc(n)}: {telegram.esc(why)}" for n, why in failed]
    if args.no_upload:
        lines.append("<i>test run: Drive not changed</i>")
    text = "\n".join(lines)
    print(text) if args.no_telegram else telegram.send(text)
    return 1 if failed and not saved else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py portal-reports", description=__doc__.splitlines()[0])
    p.add_argument("--month", default="", help="YYYY-MM (default: last month)")
    p.add_argument("--portals", default="", help="only these, e.g. MYNTRA,AJIO (default: all)")
    p.add_argument("--no-upload", action="store_true", help="download only, Drive not changed (test run)")
    return run_bot("Portal reports", p, run, argv)
