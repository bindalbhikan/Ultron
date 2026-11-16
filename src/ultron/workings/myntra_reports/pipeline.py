"""Myntra daily reports (9:30 AM, the one time of day the bots ask Myntra for their daily reports):
of each account (MAIN / DBCC / FMCC) Seller_Orders_Report, Seller_Returns_Report and
Return_Delivery_Report for the 30 days up to yesterday (the very jobs the SPF master reads at 10 AM),
and Seller_Listings_Report and Seller_Inventory_Report, snapshots of today.

Only made on the portal (owner, 16 Nov 2026): no report file is saved anywhere; the other workings
(SPF master, morning, sale, portal sale, courier scorecard, grouping) use these jobs and never ask for
the same report again. The one thing kept is AGENT WORK/MYNTRA/MYNTRA DAILY RETURN DELIVERY REPORT.xlsx:
from the 30-day return delivery and orders jobs (read in memory) every day of the 30 days is written
again per account (DATE, PORTAL, CUSTOMER RETURN, RTO, CANCELLED, TOTAL; PPMP warehouses only), so a day
missed or wrong before is put right by the next run. Days after the last day Myntra's data holds for the
account are left blank (never 0), named on Telegram and filled by a later run (Myntra's report held no
PPMP delivery after 7 Nov 2026 for days). The five are different reports,
so they are asked for together (the 15-minute cooldown is per report); a job already on the portal
for the same dates (or a snapshot of today) is reused. Each job is waited for until it is done;
one refused or killed ("Internal server error while scheduling", INTERRUPTED) is asked for again in a
second round, and so is every dated report when the orders job holds yesterday only in part (its
data time is read in memory, nothing kept). Telegram: the return delivery of yesterday, per account
each report made, or why not.
--backfill-from (by hand): the old return delivery workbook's rows from jobs on the portal.
"""
from __future__ import annotations

import argparse
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ..core import telegram
from ..core.app import run_bot
from ..core.config import csv_list, env, num
from ..core.config import agent_work_id

log = logging.getLogger("bindal.myntra_reports")

ACCOUNTS = ["MAIN", "DBCC", "FMCC"]
AREA = "MYNTRA"   # the agent's folder is kept by portal: AGENT WORK/MYNTRA (since 29 Oct 2026)
WORKBOOK = "MYNTRA DAILY RETURN DELIVERY REPORT.xlsx"
PORTALS = {"MAIN": "MYNTRA MAIN", "DBCC": "MYNTRA DBCC", "FMCC": "MYNTRA FMCC"}
DELIVERY_COLUMNS = ["CUSTOMER RETURN", "RTO", "CANCELLED", "TOTAL"]
# our own warehouses (PPMP orders): MAIN 46148 and 24504, DBCC 50829, FMCC 56765. The delivery report
# also has FBM / SJIT returns to Myntra's warehouses (28, 36, 81 ...): not counted in the workbook.
PPMP_WAREHOUSES = {"46148", "24504", "50829", "56765"}
# label -> report id
REPORTS = {"Orders": 4, "Returns": 12, "Return Delivery": 84, "Listings": 14, "Inventory": 16}
SNAPSHOT = {"Listings", "Inventory"}
ORDER_DAYS = 30
# returns and return deliveries are asked for the 30 days up to yesterday: the very job the SPF master
# (10 AM) reads, so no working asks Myntra for the same report again
RANGE_DAYS = {"Orders": ORDER_DAYS, "Returns": 30, "Return Delivery": 30}


def _job(portal, label: str, rid: int, day: date, fresh: bool = False) -> dict:
    """A job of the report for the RANGE_DAYS up to yesterday (Listings / Inventory: a snapshot asked
    for today), reused when the portal already has one."""
    from ..portals import myntra as mp
    if label not in SNAPSHOT:
        days = int(num("MYNTRA_SPF_RETURN_DAYS", 30)) if label != "Orders" else RANGE_DAYS[label]
        return portal.ensure(rid, day - timedelta(days=min(days, 30) - 1), day, fresh=fresh)
    today = date.today()
    for j in portal.jobs(100):
        status = str(j.get("status") or "").upper()
        created = mp._ts(j.get("createdOn"))
        if not fresh and j.get("reportId") == rid and created == today and not any(f in status for f in mp.FAILED):
            log.info("Report %s of today already on the portal (job %s, %s)", rid, j.get("id"), status)
            return j
    return portal.schedule(None, None, rid)


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """The column, whatever its case in the CSV; empty when the report has no such column."""
    for c in df.columns:
        if str(c).strip().lower() == name:
            return df[c].astype(str).str.strip()
    return pd.Series(dtype=str, index=df.index)


def ppmp_only(delivery: pd.DataFrame) -> pd.DataFrame:
    """The rows delivered to our own (PPMP) warehouses; FBM / SJIT returns go to Myntra's warehouses."""
    ours = set(csv_list("MYNTRA_PPMP_WAREHOUSES")) or PPMP_WAREHOUSES
    return delivery[_col(delivery, "warehouse_id").str.replace(r"\.0$", "", regex=True).isin(ours)]


def delivery_split(delivery: pd.DataFrame, orders: pd.DataFrame | None) -> dict[str, int]:
    """CUSTOMER RETURN / RTO / CANCELLED / TOTAL of a Return_Delivery_Report, PPMP warehouses only.
    RTO_or_Cancel rows are cancelled when the order's status in the orders report is F, else RTO."""
    delivery = ppmp_only(delivery)
    kind = _col(delivery, "type")
    status = pd.Series(dtype=str)
    if orders is not None and len(orders):
        status = pd.Series(_col(orders, "order status").values,
                           index=_col(orders, "order release id").str.replace(r"\.0$", "", regex=True).values
                           ).groupby(level=0).first()
    rto_or_cancel = kind == "RTO_or_Cancel"
    cancelled = int((rto_or_cancel & (_col(delivery, "order_id").str.replace(r"\.0$", "", regex=True)
                                      .map(status) == "F")).sum())
    return {"CUSTOMER RETURN": int((kind == "Return").sum()), "RTO": int(rto_or_cancel.sum()) - cancelled,
            "CANCELLED": cancelled, "TOTAL": len(delivery)}


def make_account(account: str, day: date, wait_minutes: int) -> tuple[dict[str, str], list[str], dict[str, dict]]:
    """The account's five reports made on the portal and waited for (nothing saved): ({label: what was
    made}, notes for reports not made, {label: its done job})."""
    import time
    from ..portals import myntra as mp
    from ..return_analysis.sources import myntra_portal
    portal = myntra_portal(account)
    made: dict[str, str] = {}
    done: dict[str, dict] = {}
    errors: dict[str, str] = {}
    stale: set[str] = set()     # reports whose job held wrong / short data: asked for anew
    for attempt in range(1, int(num("MYNTRA_REPORT_ROUNDS", 2)) + 1):
        pending = [label for label in REPORTS if label not in made]
        if not pending:
            break
        if attempt > 1:
            log.warning("%s: %s not made, asking again (round %d)", account, ", ".join(pending), attempt)
        jobs = {}
        for label in pending:
            try:
                jobs[label] = _job(portal, label, REPORTS[label], day, fresh=label in stale)
            except Exception as exc:  # noqa: BLE001 - the other reports still come
                if isinstance(exc, mp.SessionExpired):
                    raise
                log.warning("%s %s not asked for: %s", account, label, exc)
                errors[label] = str(exc)
        deadline = time.time() + wait_minutes * 60
        for label, job in jobs.items():
            if attempt == 1 and label != "Orders" and label in stale:
                errors[label] = "asked for anew with the orders report (its data was short)"
                continue
            try:
                job = portal._wait(job, deadline, 30)
                if label == "Orders":
                    # the data time is read in memory only: a job short of yesterday is no use to anyone
                    _, data = portal.download(job)
                    through = mp.data_through(mp.data_stamp(data.decode("utf-8-sig", "replace")))
                    if not through or through < day:
                        stale |= set(RANGE_DAYS)
                        for other in RANGE_DAYS:
                            made.pop(other, None)
                        raise RuntimeError(f"orders job {job.get('id')} holds data only up to {through}, a new report is asked for")
                rng = mp.job_range(job, REPORTS[label])
                made[label] = f"job {job.get('id')}" + (f" ({rng[0]:%d %b} to {rng[1]:%d %b})" if rng else " (today)")
                done[label] = job
                errors.pop(label, None)
            except Exception as exc:  # noqa: BLE001
                if isinstance(exc, mp.SessionExpired):
                    raise
                log.warning("%s %s not made: %s", account, label, exc)
                errors[label] = str(exc)
    mp.save_to_worker(env, portal.cookies(), account)
    return made, [f"{account} {label}: {e[:100]}" for label, e in errors.items()], done


def delivery_day(delivery: pd.DataFrame) -> pd.Series:
    """The day each return reached us (deliver_to_seller_date, else gatepass_lastmodified)."""
    when = pd.to_datetime(_col(delivery, "deliver_to_seller_date"), errors="coerce")
    return when.fillna(pd.to_datetime(_col(delivery, "gatepass_lastmodified"), errors="coerce")).dt.date


def window_rows(delivery: pd.DataFrame, orders: pd.DataFrame | None, first: date, last: date
                ) -> tuple[dict[date, dict], list[date], date | None]:
    """({day: split} for the days first..last Myntra's data holds, [days after it: left blank],
    the last day with a PPMP delivery). A day before that last one with no delivery is a real 0."""
    from ..portals import myntra as mp
    delivery = delivery.assign(_day=delivery_day(delivery))
    ours = ppmp_only(delivery)
    through = ours["_day"].dropna().max() if len(ours) else None
    through = None if pd.isna(through) else through
    rows, blank = {}, []
    for d in sorted(mp._days(first, last)):
        if through and d <= through:
            rows[d] = delivery_split(delivery[delivery["_day"] == d], orders)
        else:
            blank.append(d)
    return rows, blank, through


def account_rows(account: str, done: dict[str, dict]) -> tuple[dict[date, dict], list[date], date | None]:
    """window_rows of the account's 30-day return delivery job (and orders job), read in memory."""
    from ..portals import myntra as mp
    from ..return_analysis.sources import myntra_portal
    portal = myntra_portal(account)
    job = done["Return Delivery"]
    delivery = pd.read_csv(io.BytesIO(portal.download(job)[1]), dtype=str, low_memory=False)
    orders = None
    if "Orders" in done:
        orders = pd.read_csv(io.BytesIO(portal.download(done["Orders"])[1]), dtype=str, low_memory=False)
    first, last = mp.job_range(job, REPORTS["Return Delivery"])
    return window_rows(delivery, orders, first, last)


def update_workbook(root, rows: list[tuple[date, str, dict]], work: Path,
                    drop: set[tuple[date, str]] = frozenset()) -> str:
    """rows (day, account, split) into AGENT WORK/MYNTRA/MYNTRA DAILY RETURN DELIVERY REPORT.xlsx (DATA sheet;
    rows of the same day and portal replaced, DASHBOARD built when missing). Returns its link."""
    from ..core.drive import DriveFile
    from . import workbook
    found = root.children().get(WORKBOOK)
    if not found:
        raise RuntimeError(f"{WORKBOOK} not found in AGENT WORK/MYNTRA on Drive")
    drive = DriveFile(found["id"], root.http)
    path = drive.download(work / WORKBOOK, need_edit=True)
    # only DATA's rows change: the dashboard's own formatting and charts (edited in Excel) stay as they are
    workbook.update_file(path, [(d, PORTALS.get(a, a), s) for d, a, s in rows], [PORTALS.get(a, a) for a in ACCOUNTS], drop)
    drive.upload(path)
    return drive.url


def backfill(args) -> int:
    """The workbook's rows for --backfill-from .. --backfill-to (default the day before yesterday), from report jobs already on
    the portal (the 9:30 AM run keeps a 30-day Return_Delivery_Report and 60 days of orders):
    each delivery counted on its deliver_to_seller_date. A missing range is asked for (one job per
    report, waited for)."""
    import tempfile
    from ..core.drive import DriveFolder
    from ..portals import myntra as mp
    from ..return_analysis.sources import myntra_portal
    start = date.fromisoformat(args.backfill_from)
    end = date.fromisoformat(args.backfill_to) if args.backfill_to else date.today() - timedelta(days=2)
    rows, drop = [], set()
    for account in csv_list("MYNTRA_REPORT_ACCOUNTS") or ACCOUNTS:
        portal = myntra_portal(account)
        jobs = portal.jobs(200)

        def frames(rid: int, first: date, last: date) -> list[pd.DataFrame]:
            """Completed jobs of the report that together cover first..last (newest first), else one new job."""
            out, need = [], set(mp._days(first, last))
            for j in sorted(jobs, key=lambda j: j.get("createdOn") or 0, reverse=True):
                rng = mp.job_range(j, rid)
                if not rng or not need & mp._days(*rng) or str(j.get("status")).upper() != "COMPLETED":
                    continue
                try:
                    out.append(pd.read_csv(io.BytesIO(portal.download(j)[1]), low_memory=False))
                    need -= mp._days(*rng)
                except Exception as exc:  # noqa: BLE001 - asked for again below
                    log.warning("%s job %s not downloaded: %s", account, j.get("id"), exc)
                if not need:
                    return out
            if need:
                job = portal.schedule(min(need), max(need), rid)
                out.append(pd.read_csv(io.BytesIO(portal.collect(job, 40)[1]), low_memory=False))
            return out
        delivery = pd.concat(frames(84, start, end), ignore_index=True)
        orders = pd.concat(frames(mp.REPORT_ID, start - timedelta(days=60), end), ignore_index=True)
        mp.save_to_worker(env, portal.cookies(), account)
        got, blank, through = window_rows(delivery.drop_duplicates(), orders, start, end)
        rows += [(d, account, s) for d, s in got.items()]
        drop |= {(d, PORTALS.get(account, account)) for d in blank}
        log.info("%s: %d days written, %d left blank (data up to %s)", account, len(got), len(blank), through)
    root = DriveFolder(agent_work_id()).subfolder(AREA, create=True)
    link = update_workbook(root, rows, Path(tempfile.mkdtemp(prefix="myntra_rd_")), drop)
    total = sum(s["TOTAL"] for _, _, s in rows)
    print(f"{WORKBOOK}: {len(rows)} rows for {start}..{end}, {total} return deliveries. {link}")
    return 0


def run(args) -> int:
    if args.backfill_from:
        return backfill(args)
    day = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    accounts = csv_list("MYNTRA_REPORT_ACCOUNTS") or ACCOUNTS
    wait = num("MYNTRA_REPORT_WAIT_MINUTES", 40)
    results: dict[str, dict] = {}
    jobs: dict[str, dict] = {}
    notes: list[str] = []
    with ThreadPoolExecutor(len(accounts)) as pool:
        futures = {a: pool.submit(make_account, a, day, wait) for a in accounts}
        for a, f in futures.items():
            try:
                results[a], more, jobs[a] = f.result()
                notes += more
            except Exception as exc:  # noqa: BLE001 - the other accounts still go out
                log.exception("%s reports failed", a)
                results[a] = {}
                notes.append(f"{a}: {str(exc)[:150]}")
    if not any(results.values()):
        raise RuntimeError("no Myntra report made: " + "; ".join(notes))

    # the return delivery workbook: every day of the 30 days again, blank where Myntra has no data yet
    rows, drop, waiting, failed = [], set(), [], False
    for a in accounts:
        if "Return Delivery" not in jobs.get(a, {}):
            notes.append(f"{a}: no return delivery report, its workbook rows not written")
            failed = True
            continue
        try:
            got, blank, through = account_rows(a, jobs[a])
        except Exception as exc:  # noqa: BLE001 - the other accounts still go in
            log.exception("%s return delivery not read", a)
            notes.append(f"{a} return delivery not read: {str(exc)[:100]}")
            failed = True
            continue
        rows += [(d, a, s) for d, s in got.items()]
        drop |= {(d, PORTALS.get(a, a)) for d in blank}
        if blank:
            waiting.append(f"{a}: Myntra's data holds PPMP return deliveries only up to "
                           f"{f'{through:%d %b}' if through else 'none in 30 days'}; "
                           f"{blank[0]:%d %b} to {blank[-1]:%d %b} left blank, filled by a later run")
    book = ""
    if rows or drop:
        import tempfile
        from ..core.drive import DriveFolder
        try:
            root = DriveFolder(agent_work_id()).subfolder(AREA, create=True)
            book = update_workbook(root, rows, Path(tempfile.mkdtemp(prefix="myntra_rd_")), drop)
        except Exception as exc:  # noqa: BLE001 - the message still goes out
            log.exception("%s not updated", WORKBOOK)
            notes.append(f"{WORKBOOK} not updated: {str(exc)[:150]}")
            failed = True

    out = [f"📊 <b>Myntra daily reports · {day:%d %b %Y}</b>", "<i>made on the partner portal; no report file saved</i>"]
    yday = [s for d, _, s in rows if d == day]
    if yday:
        total = {k: sum(s[k] for s in yday) for k in DELIVERY_COLUMNS}
        out += ["", f"📦 <b>Return delivery {day:%d %b}: {total['TOTAL']}</b>"
                    + (f" ({len(yday)} of {len(accounts)} accounts)" if len(yday) < len(accounts) else ""),
                f"Customer return {total['CUSTOMER RETURN']} · RTO {total['RTO']} · Cancelled {total['CANCELLED']}"]
    for a in accounts:
        out += ["", f"<b>{telegram.esc(a)}</b>"]
        out += [f"✅ {telegram.esc(label)}: {telegram.esc(s)}" for label, s in results[a].items()]
        if not results[a]:
            out.append("• no report")
    if book:
        out += ["", f'📗 <a href="{book}">{WORKBOOK}</a> ({len(rows)} rows written for the 30 days)']
    if waiting or notes:
        out += [""] + ["⏳ " + telegram.esc(w) for w in waiting] + ["⚠️ " + telegram.esc(n) for n in notes]
    msg = "\n".join(out)
    print(msg) if args.no_telegram else telegram.send(msg)
    # Myntra's own data being late is named, not a failure: the next runs fill those days
    return 1 if notes or failed else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py myntra-reports",
                                description="Myntra daily reports made on the portal (orders, returns, return delivery, listings, inventory)")
    p.add_argument("--date", help="report day YYYY-MM-DD (default yesterday)")
    p.add_argument("--backfill-from", help="YYYY-MM-DD: only fill the return delivery workbook from that day"
                   " to the day before yesterday")
    p.add_argument("--backfill-to", help="YYYY-MM-DD: the last day --backfill-from fills (default the day before yesterday)")
    p.add_argument("--no-telegram", action="store_true", help="print the summary instead of sending it")
    return run_bot("Myntra daily reports", p, run, argv)
