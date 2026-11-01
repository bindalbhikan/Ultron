"""Portal sale reports (the 2nd of every month): last month's sale reports of every portal, 1st to
last day, into Drive AGENT WORK/PORTAL REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/Sale Report <Mon-YY>/
(core/portal_reports.py). The return reports of the month follow on the 15th (the return
analysis), when the month's returns have come in.

  * Myntra MAIN / DBCC / FMCC: Seller_Orders_Report (report 4) for exactly the month; a job already
    on the portal for those dates is reused, else one is asked for (owner's rule, 1 Nov 2026).
  * AJIO: the Dropship order report of the month.
  * Flipkart: the report centre's "Sales Report" of the month.

A portal that fails is named on Telegram and the others are saved; a run again replaces the files.
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

log = logging.getLogger("bindal.portal_sales")

MYNTRA_ACCOUNTS = ("MAIN", "DBCC", "FMCC")


def report_month(value: str, today: date) -> date:
    """YYYY-MM, else last month."""
    if value:
        y, m = value.split("-")
        return date(int(y), int(m), 1)
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


def myntra_sale(account: str, first: date, last: date, dest: Path) -> list[Path]:
    from ..portals import myntra as mp
    from ..return_analysis.sources import myntra_portal
    portal = myntra_portal(account)
    job = portal.ensure(mp.REPORT_ID, first, last)
    name, data = portal.collect_or_regenerate(job, int(num("RETURNS_WAIT_MINUTES", 45)))
    mp.save_to_worker(env, portal.cookies(), account)
    path = dest / f"{account} {name}"
    path.write_bytes(data)
    return [path]


def ajio_sale(first: date, last: date, dest: Path) -> list[Path]:
    from ..portals.ajio import AjioClient
    user, pwd = env("AJIO_USERNAME"), env("AJIO_PASSWORD")
    if not user or not pwd:
        raise RuntimeError("AJIO_USERNAME / AJIO_PASSWORD not set")
    ajio = AjioClient(user, pwd)
    ajio.login()
    path = dest / f"DropShipOrderReports {first} to {last}.xlsx"
    path.write_bytes(ajio.order_report(first, last))
    return [path]


def flipkart_sale(first: date, last: date, dest: Path) -> list[Path]:
    from ..return_analysis.sources import flipkart_client
    fk = flipkart_client()
    name, data = fk.report("Sales Report", first, last, int(num("RETURNS_WAIT_MINUTES", 45)))
    path = dest / name
    path.write_bytes(data)
    return [path]


def run(args) -> int:
    month = report_month(args.month, date.today())
    first, last = month, month.replace(day=calendar.monthrange(month.year, month.month)[1])
    if last >= date.today():
        raise ValueError(f"{pr.label(month)} is not over yet: its sale reports come on the 2nd of the next month")
    log.info("Portal sale reports %s: %s..%s", pr.label(month), first, last)
    work = Path(tempfile.mkdtemp(prefix="portal_sales_"))
    tasks = {f"MYNTRA {a}": (myntra_sale, (a, first, last)) for a in MYNTRA_ACCOUNTS}
    tasks["AJIO"] = (ajio_sale, (first, last))
    tasks["FLIPKART"] = (flipkart_sale, (first, last))
    only = {p.strip().upper() for p in (args.portals or "").split(",") if p.strip()}
    tasks = {k: v for k, v in tasks.items() if not only or k.split()[0] in only}
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {}
        for name, (fn, a) in tasks.items():
            dest = work / name.replace(" ", "_")
            dest.mkdir(parents=True, exist_ok=True)
            futures[name] = pool.submit(fn, *a, dest)
    saved, failed = {}, {}
    for name, fut in futures.items():
        portal, _, account = name.partition(" ")
        try:
            files = fut.result()
            saved[name] = files if args.no_upload else pr.save(portal, month, "sale", files)
        except Exception as exc:  # noqa: BLE001 - one portal never stops the others
            log.exception("%s sale report failed", name)
            failed[name] = str(exc).splitlines()[0][:150] if str(exc) else type(exc).__name__
    lines = [f"🗂 <b>Portal sale reports {pr.label(month)}</b>",
             f"<i>{first:%d %b} to {last:%d %b %Y}, Drive AGENT WORK/PORTAL REPORTS</i>", ""]
    lines += [f"✅ {telegram.esc(n)}: {telegram.esc(', '.join(map(str, f)) if args.no_upload else str(len(f)) + ' file')}"
              for n, f in saved.items()]
    lines += [f"❌ {telegram.esc(n)}: {telegram.esc(why)}" for n, why in failed.items()]
    text = "\n".join(lines)
    print(text) if args.no_telegram else telegram.send(text)
    return 1 if failed and not saved else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py portal-sales", description=__doc__.splitlines()[0])
    p.add_argument("--month", default="", help="YYYY-MM (default: last month)")
    p.add_argument("--portals", default="", help="only these, e.g. MYNTRA,FLIPKART (default: all)")
    p.add_argument("--no-upload", action="store_true", help="download only, Drive not changed (test run)")
    return run_bot("Portal sale reports", p, run, argv)
