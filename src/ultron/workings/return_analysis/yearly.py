"""Yearly return analysis: January to December of one year in one workbook per portal, plus the
Myntra combined and all-portal ones (same sheets as the monthly reports; Monthly Summary and
Category Performance show the months side by side).

Every monthly run keeps each portal's built rows (template columns + STATE) on Drive as
RETURN ANALYSIS/Yearly/<YYYY>/<PORTAL> <MON-YY>.csv and rebuilds the year's reports into
RETURN ANALYSIS/Output/<YYYY>/<PORTAL> SALE RETURN ANALYSIS <YYYY>.xlsx.

backfill() reuses archived portal exports and the canonical business builders for every closed
month, without requesting new portal jobs. Yearly rendering also revalidates older saved months
against those builders instead of retaining legacy return flags.
"""
from __future__ import annotations

import calendar
import logging
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from ..core.config import env
from ..core.drive import DriveFolder
from . import sources
from .engine import DATA_COLUMNS, SCHEMA, build_period
from ..core import clients

log = logging.getLogger(__name__)

# A month Myntra refuses is asked for again after the cooldown, up to this many times
YEARLY_TRIES = 3

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PORTALS = ["MYNTRA MAIN", "MYNTRA DBCC", "MYNTRA FMCC", "AJIO", "FLIPKART"]


def tag(month: date) -> str:
    return f"{month:%b-%y}".upper()


def last_day(month: date) -> date:
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def next_month(month: date) -> date:
    return last_day(month) + timedelta(days=1)


# ------------------------------------------------------------------ monthly data on Drive

def save_month_data(root: DriveFolder, results: list[dict], work: Path) -> list[str]:
    """Each portal's rows of a built month into Yearly/<YYYY>/ on Drive; portals saved."""
    saved = []
    for r in results:
        if r.get("df") is None:
            continue
        month = datetime.strptime(r["month"], "%b-%y").date()
        folder = root.subfolder("Yearly", create=True).subfolder(f"{month.year}", create=True)
        path = work / "yearly_data" / f"{r['portal']} {r['month']}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        r["df"].select(DATA_COLUMNS).write_csv(path)
        folder.put(path, "text/csv")
        saved.append(r["portal"])
    return saved


def blank_month_data(root: DriveFolder, portal: str, month: date, work: Path) -> None:
    """Empty a portal's saved month on Drive (header only), so the yearly report leaves it out.
    (The bot cannot delete a file you own; an empty file reads as no rows.)"""
    folder = root.subfolder("Yearly")
    folder = folder.subfolder(f"{month.year}") if folder else None
    name = f"{portal} {tag(month)}.csv"
    if not folder or name not in folder.children():
        return
    path = work / "yearly_blank" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(schema=SCHEMA).select(DATA_COLUMNS).write_csv(path)
    folder.put(path, "text/csv")
    log.info("Emptied %s on Drive (data not available)", name)


def rebuild_year(root: DriveFolder, year: int, supporting: Path, work: Path, upload: bool = True,
                 *, context=None, reports_by_portal=None) -> list[dict]:
    """Revalidate saved months against canonical lines before rendering the year.

    Legacy monthly CSVs identify which months to include; their old return classifications
    are never copied into the year's totals.
    """
    from .reconciled import load_context, load_reports, template_rows, template_source
    folder = root.subfolder("Yearly")
    folder = folder.subfolder(f"{year}") if folder else None
    if not folder:
        log.info("No monthly data for %s yet", year)
        return []
    months = {}
    names = folder.children()
    for portal in PORTALS:
        months[portal] = sorted({datetime.strptime(n[len(portal) + 1:-4], "%b-%y").date()
                                 for n in names if n.startswith(portal + " ") and n.endswith(".csv")})
    latest = max((m for values in months.values() for m in values), default=None)
    if latest is None:
        return []
    context = context if context is not None else load_context(supporting)
    reports, gaps = (load_reports(latest, context[0], work / "canonical") if reports_by_portal is None
                     else (reports_by_portal, []))
    frames, notes = {}, [f"{p} left out: {why}" for p, why in gaps]
    sources = {portal: template_source(rep) for portal, rep in reports.items()}
    for portal, values in months.items():
        source, _, account = portal.partition(" ")
        rep = reports.get(source)
        if rep is None:
            if values:
                notes.append(f"{portal} left out: canonical source unavailable")
            continue
        parts = []
        for month in values:
            try:
                parts.append(template_rows(rep, month, account, context[3], source=sources[source]))
            except ValueError as exc:
                notes.append(f"{portal} {tag(month)} left out: {exc}")
        if parts:
            frames[portal] = pl.concat(parts, how="diagonal_relaxed")
    if not frames:
        return []
    out = work / "yearly_out"
    results = build_period(frames, f"{year}", str(supporting), str(out))
    if upload:
        target = root.subfolder("Output", create=True).subfolder(f"{year}", create=True)
        for r in results:
            target.put(Path(r["report"]), XLSX)
    for r in results:
        r["months"] = sorted({m for df in frames.values() for m in df["MONTH"].drop_nulls().unique().to_list()})
        r["frames"] = frames          # the dashboard's details come from the same rows
        r["notes"] = notes
    return results


# ------------------------------------------------------------------ backfill

def months_to_fill(year: int, today: date) -> list[date]:
    """Months of the year whose returns window (to the next month's 14th) is already over."""
    out, m = [], date(year, 1, 1)
    while m.year == year and next_month(m).replace(day=14) < today:
        out.append(m)
        m = next_month(m)
    return out


def _myntra_account(account: str, months: list[date], dest: Path, notes: list[str]) -> None:
    """Every month's orders report and every calendar month's returns report of one account into
    dest/<MON-YY>/. Orders and returns are asked together; the same report again only after
    the cooldown. A refused or failed job leaves that month without the file (noted)."""
    from ..portals import myntra as mp
    portal = sources.myntra_portal(account)
    last = months[-1]
    orders = [(mp.REPORT_ID, m, last_day(m), m) for m in months]
    # returns by calendar month (they give the reasons; the return itself is on the orders report),
    # the month after the last one only up to its 14th
    returns = [(mp.RETURNS_REPORT_ID, m, last_day(m), m) for m in months]
    returns.append((mp.RETURNS_REPORT_ID, next_month(last), next_month(last).replace(day=14), next_month(last)))
    jobs = []
    queues = [list(orders), list(returns)]
    tries: dict[tuple, int] = {}
    while any(queues):
        asked = False
        for queue in queues:
            if not queue:
                continue
            report_id, start, end, month = queue[0]
            job = mp.exact_job(portal.jobs(100), report_id, start, end)
            if not job:
                # Every request (or refusal) is followed by the cooldown before this report is
                # asked for again. A refused month stays first in its queue and is asked for
                # again after the cooldown - moving on lost May MAIN / Jun DBCC (18 Oct backfill).
                asked = True
                try:
                    job = portal.schedule(start, end, report_id, cooldown_wait=False)
                except Exception as exc:  # noqa: BLE001 - that month only
                    key = (report_id, start)
                    tries[key] = tries.get(key, 0) + 1
                    log.warning("Myntra %s report %s %s refused (try %d): %s", account, report_id, start, tries[key], exc)
                    if tries[key] < YEARLY_TRIES:
                        continue
                    notes.append(f"Myntra {account} report {report_id} {start:%b %Y}: {str(exc)[:80]}")
                    queue.pop(0)
                    continue
            jobs.append((job, month))
            queue.pop(0)
        if asked and any(queues):
            log.info("%s: waiting for the report cooldown", account)
            time.sleep(sources.COOLDOWN_SECONDS)
    for job, month in jobs:
        try:
            name, data = portal.collect_or_regenerate(job, wait_minutes=60)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Myntra {account} job {job.get('id')} ({month:%b %Y}): {str(exc)[:80]}")
            continue
        folder = dest / tag(month)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
    mp.save_to_worker(env, portal.cookies(), account)


def _ajio(months: list[date], dest: Path, notes: list[str]) -> None:
    ajio = clients.ajio()
    for m in months:
        folder = dest / tag(m)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"DropShipOrderReports {m} to {last_day(m)}.xlsx").write_bytes(ajio.order_report(m, last_day(m)))
            for start, end, blob in ajio.rtv_reports(m, next_month(m).replace(day=14), days=30):
                (folder / f"DropShipRtvReports {start} to {end}.xlsx").write_bytes(blob)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Ajio {m:%b %Y}: {str(exc)[:80]}")
            shutil.rmtree(folder, ignore_errors=True)


def _flipkart(months: list[date], dest: Path, notes: list[str]) -> set[date]:
    """Every month's Sales Report and Returns report into dest/<MON-YY>/. Flipkart keeps returns
    for about four months only: a month whose Returns report is empty or starts late is asked for
    once more, and if it is still incomplete the month is left out (Flipkart missing from it in
    the yearly report rather than shown with no returns). The months left out."""
    fk = sources.flipkart_client()
    wanted = [(m, "Sales Report", m, last_day(m)) for m in months] + \
             [(m, "Returns", m, next_month(m).replace(day=14)) for m in months]
    for _, name, a, b in wanted:      # all asked first, Flipkart makes them side by side
        try:
            fk.request_report(name, a, b)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Flipkart {name} {a:%b %Y}: {str(exc)[:80]}")
    left_out: set[date] = set()
    for m, name, a, b in wanted:
        try:
            file_name, data = fk.report(name, a, b, wait_minutes=60)
            if name == "Returns" and not sources.returns_complete(data, a)[0]:
                rid = fk.request_report(name, a, b, fresh=True)       # a new report, once
                file_name, data = fk._report(name, a, b, rid, 60, 30)
                ok, why = sources.returns_complete(data, a)
                if not ok:
                    left_out.add(m)
                    notes.append(f"Flipkart {m:%b %Y} left out: {why} (Flipkart keeps returns ~4 months)")
                    continue
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Flipkart {name} {a:%b %Y}: {str(exc)[:80]}")
            if name == "Returns":
                left_out.add(m)
            continue
        folder = dest / tag(m)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / file_name).write_bytes(data)
    for m in left_out:                 # no returns for the month: its sales alone would be wrong
        shutil.rmtree(dest / tag(m), ignore_errors=True)
    return left_out


def _month_input(raw: Path, month: date, inputs: Path) -> None:
    """One month's engine Input/ tree from the fetched files."""
    from ..portals import myntra as mp
    for account in mp.ACCOUNTS:
        files = list((raw / "Myntra" / account / tag(month)).glob("*Seller_Orders_Report*.csv"))
        if not files:
            continue
        folder = inputs / "Myntra" / account
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(files[0], folder)
        for m in (month, next_month(month)):          # reasons: this month's and next month's returns
            for f in (raw / "Myntra" / account / tag(m)).glob("*Seller_Returns_Report*.csv"):
                shutil.copy2(f, folder)
    for portal in ("Ajio", "Flipkart"):
        src = raw / portal / tag(month)
        if src.is_dir() and any(src.iterdir()):
            shutil.copytree(src, inputs / portal, dirs_exist_ok=True)


def backfill(root: DriveFolder, year: int, supporting: Path, work: Path, today: date,
             notes: list[str], portals: set[str] | None = None) -> tuple[list[date], list[dict]]:
    """Rebuild closed months from saved portal reports using the canonical business lines.

    No new portal jobs are requested. Sources unavailable in the archive are named and excluded.
    """
    from .reconciled import build_month, load_context, load_reports
    months = months_to_fill(year, today)
    if not months:
        raise RuntimeError(f"no month of {year} has its returns window over yet")
    log.info("Backfill %s: %s", year, [tag(m) for m in months])
    portals = {p.upper() for p in portals} if portals else {"MYNTRA", "AJIO", "FLIPKART"}
    allowed = {name for name in PORTALS if name.split()[0] in portals}
    if not allowed:
        raise RuntimeError(f"no known portal in {sorted(portals)} (MYNTRA, AJIO, FLIPKART)")
    context = load_context(supporting)
    reports, failures = load_reports(months[-1], context[0], work / "canonical", allowed=allowed)
    notes.extend(f"{portal} left out: {why}" for portal, why in failures)
    filled = []
    for m in months:
        results, skipped = build_month(m, supporting, work / "months" / tag(m) / "out", work / "canonical",
                                        allowed=allowed, context=context, reports_by_portal=reports)
        for portal, reason in skipped:
            notes.append(f"{tag(m)} {portal} left out: {reason[:80]}")
        if results:
            save_month_data(root, [r for r in results if r.get("df") is not None and r["month"] == tag(m)], work)
            filled.append(m)
    # Revalidate other portals too when rendering an existing year's combined workbook.
    results = rebuild_year(root, year, supporting, work, context=context)
    return filled, results
