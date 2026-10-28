"""Myntra order and return history: Seller_Orders_Report (4) and Seller_Returns_Report (12) of MAIN,
DBCC and FMCC, one report per calendar month (--from .. --to, default Apr-25 .. Sep-26), into Drive
AGENT WORK/MYNTRA ORDER RETURN REPORTS <FROM> TO <TO>/:

  ORDERS/<ACCOUNT>/<ACCOUNT> ORDERS APR-25.csv     RETURNS/<ACCOUNT>/<ACCOUNT> RETURNS APR-25.csv
  MYNTRA ORDERS ALL ACCOUNTS APR-25 TO SEP-26.csv  MYNTRA RETURNS ALL ACCOUNTS APR-25 TO SEP-26.csv
  (every month of the 3 accounts, ACCOUNT and MONTH columns first; zipped when too big for the
  Drive relay)

A report already on the portal for exactly that month is used; else one is asked for. The portal
takes the same report of an account once in 16 minutes (a refusal reads "Internal server error"):
the six account x report lines run side by side, each asks for its next month 16 minutes after the
last and downloads its reports as they are ready. A month refused 3 times (older than the portal
keeps) is reported and skipped. Months already in the Drive folder are not asked for again, so a
run cut short (6 h limit) is simply run again.
"""
from __future__ import annotations

import argparse
import io
import logging
import tempfile
import threading
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ..core import telegram
from ..core.app import run_bot
from ..core.config import env, num

log = logging.getLogger("bindal.myntra_history")

AGENT_WORK = "1uO-aOha_QKkI3f19EA7sweYPgkjMukZI"   # Drive BINDAL EXPORTS/AGENT WORK
ACCOUNTS = ["MAIN", "DBCC", "FMCC"]
CSV = "text/csv"
GAP = 16 * 60            # seconds between two requests of the same report of an account
TRIES = 2           # a refusal after the 16-minute gap is not the cooldown: twice = not kept
RELAY_MAX = 30_000_000   # bytes: a bigger merged CSV goes up zipped


def months(first: date, last: date) -> list[tuple[date, date]]:
    out, m = [], first.replace(day=1)
    while m <= last:
        nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((m, nxt - timedelta(days=1)))
        m = nxt
    return out


def tag(d: date) -> str:
    return f"{d:%b-%y}".upper()


class Line(threading.Thread):
    """One account's one report: asks for its months one by one (16 minutes apart), downloads each
    as it is ready, saves it in the Drive folder."""

    def __init__(self, account: str, label: str, rid: int, wanted, folder, work: Path, results: dict):
        super().__init__(name=f"{account}-{label}")
        self.account, self.label, self.rid, self.wanted = account, label, rid, wanted
        self.folder, self.work, self.results = folder, work, results
        self.pending: list[tuple[date, dict]] = []
        self.next_ok = 0.0

    def run(self):
        from ..portals import myntra as mp
        from ..return_analysis.sources import myntra_portal
        try:
            self.portal = myntra_portal(self.account)
            jobs, ask = self.portal.jobs(200), []
            for start, end in self.wanted:      # reports already on the portal first, for every month
                job = mp.exact_job(jobs, self.rid, start, end)
                if job and not any(f in str(job.get("status", "")).upper() for f in mp.FAILED):
                    log.info("%s %s: job %s already on the portal", self.name, tag(start), job.get("id"))
                    self.pending.append((start, job))
                else:
                    ask.append((start, end))
            # newest month first: a month the portal no longer keeps is refused, and so is every
            # older one, so the line stops there instead of spending 16 minutes a try on each
            # (28 Oct 2026: Apr-25 and May-25 refused, Jul-25 given)
            ask.sort(reverse=True)
            for n, (start, end) in enumerate(ask):
                got = False
                for attempt in range(1, TRIES + 1):
                    self.serve_until(self.next_ok)
                    try:
                        self.pending.append((start, self.portal.schedule(start, end, self.rid, cooldown_wait=0)))
                        self.next_ok = time.time() + GAP
                        got = True
                        break
                    except Exception as exc:  # noqa: BLE001
                        if isinstance(exc, mp.SessionExpired):
                            raise
                        self.next_ok = time.time() + GAP
                        log.warning("%s %s refused (try %d of %d): %s", self.name, tag(start), attempt, TRIES,
                                    str(exc)[:120])
                if not got:
                    older = [tag(s) for s, _ in ask[n:]]
                    log.warning("%s: %s refused %d times, not asking for older months (%s)", self.name,
                                tag(start), TRIES, ", ".join(older))
                    self.results["failed"] += [(self.account, self.label, m, "not given by the portal (too old?)")
                                               for m in older]
                    break
            self.serve_until(time.time() + num("MYNTRA_HISTORY_WAIT_MINUTES", 90) * 60, all_done=True)
            for start, job in self.pending:
                self.results["failed"].append((self.account, self.label, tag(start), f"job {job.get('id')} not ready"))
            mp.save_to_worker(env, self.portal.cookies(), self.account)
        except Exception as exc:  # noqa: BLE001 - the other lines go on
            log.exception("%s stopped", self.name)
            self.results["failed"].append((self.account, self.label, "-", f"stopped: {str(exc)[:150]}"))

    def serve_until(self, until: float, all_done: bool = False):
        """Download the pending reports that are ready until `until` (or until none is left)."""
        from ..portals import myntra as mp
        while True:
            if self.pending:
                jobs = {j.get("id"): j for j in self.portal.jobs(200)}
                for item in list(self.pending):
                    start, job = item
                    job = jobs.get(job.get("id"), job)
                    status = str(job.get("status") or "").upper()
                    if status == "COMPLETED" and job.get("successFile"):
                        self.pending.remove(item)
                        self.save(start, self.portal.download(job)[1])
                    elif any(f in status for f in mp.FAILED):
                        self.pending.remove(item)
                        self.results["failed"].append((self.account, self.label, tag(start), f"job {status}"))
            if (all_done and not self.pending) or time.time() >= until:
                return
            time.sleep(min(60, max(1, until - time.time())))

    def save(self, start: date, data: bytes):
        name = f"{self.account} {self.label} {tag(start)}.csv"
        path = self.work / self.label / self.account / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        rows = len(pd.read_csv(io.BytesIO(data), low_memory=False))
        with LOCK:
            self.folder.subfolder(self.label, create=True).subfolder(self.account, create=True).put(path, CSV)
        log.info("%s %s: %d rows saved", self.name, tag(start), rows)
        self.results["saved"].append((self.account, self.label, tag(start), rows))


LOCK = threading.Lock()


def merge(folder, work: Path, label: str, wanted, first: date, last: date) -> tuple[str, int] | None:
    """Every month of the 3 accounts (this run's and earlier runs' files, from Drive) in one file."""
    frames = []
    sub = folder.subfolder(label)
    for account in ACCOUNTS:
        acc = sub.subfolder(account) if sub else None
        for start, _ in wanted:
            name = f"{account} {label} {tag(start)}.csv"
            path = work / label / account / name
            if not path.exists() and acc:
                acc.download(name, path)
            if path.exists():
                df = pd.read_csv(path, dtype=str, low_memory=False)
                df.insert(0, "MONTH", tag(start))
                df.insert(0, "ACCOUNT", account)
                frames.append(df)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    out = work / f"MYNTRA {label} ALL ACCOUNTS {tag(first)} TO {tag(last)}.csv"
    df.to_csv(out, index=False)
    if out.stat().st_size > RELAY_MAX:
        z = out.with_suffix(".zip")
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
            f.write(out, out.name)
        out = z
    folder.put(out, "application/zip" if out.suffix == ".zip" else CSV)
    log.info("Merged %s: %d rows, %d files -> %s", label, len(df), len(frames), out.name)
    return out.name, len(df)


def run(args) -> int:
    """--step prepare: the Drive folders (before parallel fetches, so no folder is made twice);
    fetch: get the months (--accounts / --reports), Telegram only when some failed; merge: the
    merged files + the Telegram summary; all: the three in one go."""
    from ..core.drive import DriveFolder
    from ..portals import myntra as mp
    first, last = date.fromisoformat(args.from_month + "-01"), date.fromisoformat(args.to_month + "-01")
    wanted = months(first, last)
    accounts, labels = args.accounts.split(","), args.reports.split(",")
    rids = {"ORDERS": mp.REPORT_ID, "RETURNS": mp.RETURNS_REPORT_ID}
    root = DriveFolder(env("AGENT_WORK_FOLDER_ID", AGENT_WORK))
    name = f"MYNTRA ORDER RETURN REPORTS {tag(first)} TO {tag(last)}"
    folder = root.subfolder(name, create=args.step in ("prepare", "all"))
    if folder is None:
        raise RuntimeError(f"No AGENT WORK/{name} folder on Drive: run --step prepare first")
    if args.step in ("prepare", "all"):
        for label in labels:
            sub = folder.subfolder(label, create=True)
            for account in accounts:
                sub.subfolder(account, create=True)
        if args.step == "prepare":
            print(f"{name}: folders ready")
            return 0
    work = Path(tempfile.mkdtemp(prefix="myntra_history_"))
    results = {"saved": [], "failed": []}
    if args.step in ("fetch", "all"):
        lines = []
        for account in accounts:
            for label in labels:
                acc = folder.subfolder(label).subfolder(account)
                have = set(acc.children())
                todo = [(s, e) for s, e in wanted if f"{account} {label} {tag(s)}.csv" not in have]
                log.info("%s %s: %d of %d months to get", account, label, len(todo), len(wanted))
                if todo:
                    lines.append(Line(account, label, rids[label], todo, folder, work, results))
        for t in lines:
            t.start()
            time.sleep(3)
        for t in lines:
            t.join()
        print(f"saved {len(results['saved'])}, failed {len(results['failed'])}")
        if args.step == "fetch":
            if results["failed"] and not args.no_telegram:
                telegram.send(f"⚠️ <b>Myntra history · {'/'.join(accounts)} {'/'.join(labels)}</b>: "
                              f"{len(results['saved'])} months saved, not got:\n"
                              + "\n".join(f"  {a} {lb} {mo}: {telegram.esc(why)}"
                                          for a, lb, mo, why in results["failed"][:30]))
            return 0

    merged = {label: merge(folder, work, label, wanted, first, last) for label in labels}
    missing = []
    for label in labels:
        for account in accounts:
            acc = folder.subfolder(label).subfolder(account)
            have = set(acc.children()) if acc else set()
            missing += [f"{account} {label} {tag(s)}" for s, _ in wanted if f"{account} {label} {tag(s)}.csv" not in have]
    total = len(wanted) * len(accounts) * len(labels)
    msg = [f"📥 <b>Myntra order + return reports · {tag(first)} to {tag(last)}</b>",
           f"{total - len(missing)} of {total} monthly files on Drive"]
    for label, m in merged.items():
        if m:
            msg.append(f"• {label}: {m[1]:,} rows in {telegram.esc(m[0])}")
    if missing:
        msg.append(f"⚠️ Missing ({len(missing)}): " + ", ".join(missing[:40]))
    msg.append(f"📁 Drive: AGENT WORK/{name}")
    text = "\n".join(msg)
    if args.no_telegram:
        print(text)
    else:
        telegram.send(text)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from", dest="from_month", default="2025-04", help="first month, YYYY-MM (default 2025-04)")
    p.add_argument("--to", dest="to_month", default="2026-09", help="last month, YYYY-MM (default 2026-09)")
    p.add_argument("--accounts", default=",".join(ACCOUNTS), help="comma separated (default MAIN,DBCC,FMCC)")
    p.add_argument("--reports", default="ORDERS,RETURNS", help="ORDERS, RETURNS or both (default both)")
    p.add_argument("--step", choices=["all", "prepare", "fetch", "merge"], default="all",
                   help="prepare the Drive folders / fetch the months / merge them (default all)")
    return run_bot("Myntra order + return history", p, run, argv)


if __name__ == "__main__":
    raise SystemExit(main())
