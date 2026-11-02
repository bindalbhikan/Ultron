"""Submitting the pending colour groups on the Myntra partner portal, and keeping the record of it.

  sync_jobs     every style-grouping job on the portal goes into the record (also those uploaded by
                hand: BY = Portal, their style ids read from the job's input file), and the status and
                counts of every job are read again (WAITING, APPROVAL_PENDING, COMPLETED,
                IN_PROGRESS, PARTIAL_COMPLETE, FAILED, REJECTED). Myntra approves an upload before it goes
                live.
  group state   the newest job of a group decides, never an older one: a failed upload followed by a
                completed one is approved. The live check on myntra.com has the last word: a group with
                nothing pending is DONE, whatever its old jobs say.
  submit        the upload files of TEMPLATES/<day>/ACC-<seller id>/ are uploaded on their account
                (only with --submit, the owner's call). skip_reason says what is not sent.
  The record    Drive AGENT WORK/MYNTRA/LISTING GROUPING/GROUPING SUBMISSIONS.xlsx, one row per upload,
                kept for good, newest first.
  apply         the report (MYNTRA GROUPING MASTER.xlsx) gets a SUBMISSIONS sheet and, on the account
                sheets, the group's newest job, its SUBMIT STATE, TRIES (every upload of the group) and
                the portal's reason. It can run again on a finished report (--status).
"""
from __future__ import annotations

import io
import logging
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger("bindal.myntra_grouping")

RECORD = "GROUPING SUBMISSIONS.xlsx"
COLS = ["SUBMITTED ON", "TIME", "ACCOUNT", "SELLER ID", "UNIQUE ID", "BRAND", "ARTICLE TYPE", "FILE", "STYLES",
        "STYLE IDS", "JOB ID", "JOB STATUS", "TOTAL RECORDS", "PROCESSED RECORDS", "ERRED RECORDS", "BY", "PORTAL REMARK"]
SELLER_OF = {"MAIN": "19170", "DBCC": "32207", "FMCC": "35426"}
ACCOUNT_OF = {v: k for k, v in SELLER_OF.items()}
FINISHED = {"COMPLETED", "PARTIAL_COMPLETE", "FAILED", "REJECTED"}
# An approved job can take days to show on myntra.com (2 Nov 2026: 35 of 143 jobs approved that day were
# fully there hours later), so it is not sent again for this long; a failed upload is free to try again after it.
WAIT_DAYS = 7
GROUP_COLS = ["SUBMITTED ON", "JOB ID", "JOB STATUS", "SUBMIT STATE", "TRIES", "PORTAL REMARK"]
DONE, FRESH, WAITING, APPROVED, CHECK = "DONE", "FRESH", "WAITING ON MYNTRA", "APPROVED, SITE NOT UPDATED", "APPROVED, NOT ON SITE: CHECK"
PARTIAL, FAILED, REJECTED = "PARTIAL", "FAILED", "REJECTED"


def read_record(path: Path | None) -> pd.DataFrame:
    if path and path.exists():
        return pd.read_excel(path, sheet_name="SUBMISSIONS", dtype=str).reindex(columns=COLS)
    return pd.DataFrame(columns=COLS, dtype=object)


def template_rows(path: Path) -> tuple[str, list[str]]:
    """(unique id, style ids) of one upload file."""
    df = pd.read_excel(path, dtype=str)
    uid = str(df.iloc[0, 0]).strip() if len(df) else ""
    return uid, [str(x).replace(".0", "").strip() for x in df.iloc[:, 2].dropna()]


def _when(value) -> tuple[str, str]:
    """(date, time) in IST of a job's createdAt (the portal answers UTC, ISO text or epoch ms)."""
    try:
        t = pd.to_datetime(value, unit="ms") if str(value).isdigit() else pd.to_datetime(value)
        t = t.tz_convert(None) if t.tzinfo else t
        t = t + timedelta(hours=5, minutes=30)
        return f"{t:%Y-%m-%d}", f"{t:%H:%M}"
    except (ValueError, TypeError):
        return str(value)[:10], ""


def _job_styles(job: dict) -> tuple[str, list[str]]:
    """(unique id, style ids) from a job's input file; empty when it cannot be read."""
    url = (job.get("metaData") or {}).get("signedInputFilePath")
    if not url:
        return "", []
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        df = pd.read_excel(io.BytesIO(r.content), dtype=str)
        return str(df.iloc[0, 0]).strip(), [str(x).replace(".0", "").strip() for x in df.iloc[:, 2].dropna()]
    except Exception as exc:  # noqa: BLE001 - the job is still recorded
        log.info("Input file of job %s not read: %s", job.get("id"), str(exc)[:100])
        return "", []


def sync_jobs(record: pd.DataFrame, accounts: list[str] | None = None) -> tuple[pd.DataFrame, list[str]]:
    """The portal's jobs into the record, every status read again; problems, one line each."""
    from ..portals import myntra as mp
    from ..return_analysis.sources import env, myntra_portal
    record, problems, new = record.copy(), [], []
    for account in accounts or list(SELLER_OF):
        try:
            portal = myntra_portal(account)
            jobs, page = [], 1
            while True:         # every page: a job past the first would keep its old status for good
                got = portal.style_grouping_jobs(200, page)
                jobs += got
                if len(got) < 200:
                    break
                page += 1
            mp.save_to_worker(env, portal.cookies(), account)
        except Exception as exc:  # noqa: BLE001 - one account never stops the others
            problems.append(f"{account}: grouping jobs not read ({str(exc).splitlines()[0][:100]})")
            continue
        known = set(record["JOB ID"].astype(str))
        for j in jobs:
            jid = str(j.get("id"))
            counts = [str(j.get("status") or ""), str(j.get("totalRecords") or 0), str(j.get("processedRecords") or 0),
                      str(j.get("erredRecords") or 0)]
            day, at = _when(j.get("createdAt"))
            if jid in known:     # the portal's own time: the clock of the run that uploaded can be UTC
                record.loc[record["JOB ID"].astype(str) == jid,
                           ["SUBMITTED ON", "TIME", "JOB STATUS", "TOTAL RECORDS", "PROCESSED RECORDS", "ERRED RECORDS"]] = [day, at, *counts]
                continue
            uid, styles = _job_styles(j)
            new.append({"SUBMITTED ON": day, "TIME": at, "ACCOUNT": account, "SELLER ID": SELLER_OF[account],
                        "UNIQUE ID": uid, "BRAND": "", "ARTICLE TYPE": "", "FILE": "", "STYLES": str(len(styles)),
                        "STYLE IDS": ", ".join(styles), "JOB ID": jid, "JOB STATUS": counts[0], "TOTAL RECORDS": counts[1],
                        "PROCESSED RECORDS": counts[2], "ERRED RECORDS": counts[3], "BY": "Portal"})
    if new:
        record = pd.concat([record, pd.DataFrame(new, columns=COLS)], ignore_index=True)
    return record, problems


def failure_reasons(record: pd.DataFrame) -> pd.DataFrame:
    """PORTAL REMARK of every job Myntra did not fully take, uploaded by the bot or by hand: the reason in
    the job's result report (Remarks; rejectReason on a job the approver rejected)."""
    import zipfile
    from ..return_analysis.sources import myntra_portal
    record, portals = record.copy(), {}
    todo = record[record["JOB STATUS"].isin(["FAILED", "PARTIAL_COMPLETE", "REJECTED"])
                  & record["JOB ID"].astype(str).str.fullmatch(r"\d+")
                  & (record["PORTAL REMARK"].isna() | (record["PORTAL REMARK"].astype(str) == ""))]
    for i, r in todo.iterrows():
        try:
            if r["ACCOUNT"] not in portals:
                portals[r["ACCOUNT"]] = myntra_portal(r["ACCOUNT"])
            link = portals[r["ACCOUNT"]].style_grouping_report(int(r["JOB ID"]))
            z = zipfile.ZipFile(io.BytesIO(requests.get(link, timeout=60).content))
            df = pd.read_csv(z.open(z.namelist()[0]), dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            said = df[next(c for c in ("rejectReason", "Remarks") if c in df)].dropna().astype(str).str.strip()
            bad = said[(said != "") & (said.str.upper() != "SUCCESS")].unique()
            record.loc[i, "PORTAL REMARK"] = " | ".join(bad)[:300] or "no reason in the report"
        except Exception as exc:  # noqa: BLE001 - the reason is only a help
            log.info("Report of job %s not read: %s", r["JOB ID"], str(exc)[:100])
    return record


def jobs_of(record: pd.DataFrame) -> list[dict]:
    """Every job the portal took, oldest first (by job id: the portal numbers them in order)."""
    out = []
    for _, r in record.iterrows():
        jid = str(r["JOB ID"]).replace(".0", "")
        if not jid.isdigit():
            continue
        remark = r["PORTAL REMARK"]
        out.append({"id": int(jid), "seller": str(r["SELLER ID"]), "day": str(r["SUBMITTED ON"])[:10], "status": str(r["JOB STATUS"]),
                    "styles": {s for s in str(r["STYLE IDS"]).split(", ") if s and s != "nan"},
                    "remark": "" if pd.isna(remark) else str(remark)})
    return sorted(out, key=lambda j: j["id"])


def _recent(job: dict, today: date) -> bool:
    try:
        return (today - date.fromisoformat(job["day"])).days <= WAIT_DAYS
    except ValueError:
        return False


def skip_reason(seller: str, styles: list[str], jobs: list[dict], today: date) -> str:
    """Why this upload is not sent now ("" = send it). Only the newest attempt of the same styles counts:
    a failed upload that later went through blocks nothing."""
    have, mine = set(styles), [j for j in jobs if j["seller"] == seller]
    if any(j["status"] not in FINISHED and have & j["styles"] for j in mine):
        return "waiting on Myntra"
    same = [j for j in mine if j["styles"] == have]
    if same and same[-1]["status"] == "REJECTED":
        return "rejected, change the styles first"
    if same and same[-1]["status"] in ("FAILED", "PARTIAL_COMPLETE") and _recent(same[-1], today):
        return f"failed in the last {WAIT_DAYS} days"
    approved = set().union(*[j["styles"] for j in mine if j["status"] == "COMPLETED" and _recent(j, today)], set())
    if have <= approved:
        return "approved, site not updated yet"
    return ""


def group_state(jobs_newest_first: list[dict], pending: bool, today: date) -> str:
    """A group's state: the live check first, then its newest job."""
    if not pending:
        return DONE
    if not jobs_newest_first:
        return FRESH
    job = jobs_newest_first[0]
    if job["status"] == "COMPLETED":
        return APPROVED if _recent(job, today) else CHECK
    return {"PARTIAL_COMPLETE": PARTIAL, "FAILED": FAILED, "REJECTED": REJECTED}.get(job["status"], WAITING)


def changed_jobs(old: pd.DataFrame, new: pd.DataFrame) -> Counter:
    """New status -> jobs that are new or got that status since the old record."""
    was = dict(zip(old["JOB ID"].astype(str), old["JOB STATUS"].astype(str)))
    return Counter(str(s) for j, s in zip(new["JOB ID"].astype(str), new["JOB STATUS"].astype(str))
                   if j.isdigit() and was.get(j) != str(s))


def submit(folder: Path, record: pd.DataFrame, limit: int = 0, pause: float = 0.005) -> tuple[pd.DataFrame, list[str], int, Counter]:
    """Upload the files of folder/ACC-<seller id>/; (record, problems, submitted, reason -> skipped).
    limit: at most that many groups in all (a test)."""
    from ..portals import myntra as mp
    from ..return_analysis.sources import env, myntra_portal
    rows, problems, skipped = [], [], Counter()
    jobs, today = jobs_of(record), date.today()
    for acc_dir in sorted(p for p in folder.iterdir() if p.is_dir() and p.name.startswith("ACC-")):
        seller = acc_dir.name[4:]
        account = ACCOUNT_OF.get(seller, seller)
        try:
            portal = myntra_portal(account)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{account}: no session ({str(exc)[:100]})")
            continue
        for f in sorted(acc_dir.glob("*.xlsx")):
            if limit and len(rows) >= limit:
                break
            uid, styles = template_rows(f)
            why = skip_reason(seller, styles, jobs, today)
            if why:
                skipped[why] += 1
                log.info("%s %s: %s: skipped", account, f.name, why)
                continue
            m = re.match(r"^(\d+)_(.+)_([^_]+)\.xlsx$", f.name)
            brand, article = (m.group(2), m.group(3)) if m else ("", "")
            try:
                job, status = str(portal.style_grouping_submit(f.name, f.read_bytes())), "SUBMITTED"
            except Exception as exc:  # noqa: BLE001 - one group never stops the others
                job, status = "", f"NOT SUBMITTED: {str(exc).splitlines()[0][:120]}"
                problems.append(f"{account} {f.name}: {status}")
            rows.append({"SUBMITTED ON": f"{datetime.now():%Y-%m-%d}", "TIME": f"{datetime.now():%H:%M}", "ACCOUNT": account,
                         "SELLER ID": seller, "UNIQUE ID": uid, "BRAND": brand, "ARTICLE TYPE": article, "FILE": f.name,
                         "STYLES": str(len(styles)), "STYLE IDS": ", ".join(styles), "JOB ID": job, "JOB STATUS": status,
                         "BY": "Ultron"})
            time.sleep(pause)
        mp.save_to_worker(env, portal.cookies(), account)
    if rows:
        record = pd.concat([record, pd.DataFrame(rows, columns=COLS)], ignore_index=True)
    return record, problems, sum(1 for r in rows if r["JOB ID"]), skipped


def _newest_first(record: pd.DataFrame) -> pd.DataFrame:
    return (record.assign(_job=pd.to_numeric(record["JOB ID"], errors="coerce"))
            .sort_values(["SUBMITTED ON", "_job"], ascending=False, na_position="last").drop(columns="_job"))


def write_record(record: pd.DataFrame, path: Path) -> Path:
    from .engine import format_workbook
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        _newest_first(record).to_excel(xw, sheet_name="SUBMISSIONS", index=False)
        format_workbook(xw.book)
    return path


def apply(report: Path, record: pd.DataFrame, today: date | None = None) -> dict[str, Counter]:
    """On the account sheets each group's newest job, SUBMIT STATE, TRIES and the portal's reason, and the
    SUBMISSIONS sheet. Safe to run on a report that has them already. Returns seller -> pending groups per state."""
    from openpyxl import load_workbook
    from .engine import PENDING_REMARKS, REMARK_EXTRA, format_workbook
    today, states = today or date.today(), {}
    jobs = jobs_of(record)
    wb = load_workbook(report)
    for ws in wb.worksheets:
        if not ws.title.startswith("ACC-"):
            continue
        seller = ws.title[4:]
        head = [c.value for c in ws[1]]
        at = {}
        for name in GROUP_COLS:
            if name not in head:
                head.append(name)
                ws.cell(1, len(head), name)
            at[name] = head.index(name) + 1
        iuid, isid, irem = head.index("Unique ID") + 1, head.index("Style ID") + 1, head.index("GROUPING REMARK") + 1
        groups: dict[str, dict] = {}
        for r in range(2, ws.max_row + 1):
            g = groups.setdefault(str(ws.cell(r, iuid).value), {"rows": [], "styles": set(), "pending": False})
            g["rows"].append(r)
            remark = ws.cell(r, irem).value
            g["pending"] |= remark in PENDING_REMARKS
            if remark != REMARK_EXTRA:      # a style to take out belongs to another group
                g["styles"].add(str(ws.cell(r, isid).value or "").replace(".0", "").strip())
        tally = Counter()
        for g in groups.values():
            mine = [j for j in reversed(jobs) if j["seller"] == seller and j["styles"] & g["styles"]]
            state = group_state(mine, g["pending"], today)
            if g["pending"]:
                tally[state] += 1
            tries = " | ".join(f"{j['day']} {j['status']}" for j in mine[:4]) + (f" | {len(mine) - 4} older" if len(mine) > 4 else "")
            new = mine[0] if mine else {}
            values = {"SUBMITTED ON": new.get("day", ""), "JOB ID": new.get("id", ""), "JOB STATUS": new.get("status", ""),
                      "SUBMIT STATE": state, "TRIES": tries, "PORTAL REMARK": new.get("remark", "")}
            for r in g["rows"]:
                for name, v in values.items():
                    ws.cell(r, at[name], v)
        states[seller] = tally
    if "SUBMISSIONS" in wb.sheetnames:
        del wb["SUBMISSIONS"]
    ws = wb.create_sheet("SUBMISSIONS")
    ws.append(COLS)
    for r in _newest_first(record).itertuples(index=False):
        ws.append(["" if pd.isna(v) else v for v in r])
    format_workbook(wb)
    wb.save(report)
    return states


def state_line(tally: Counter) -> str:
    """The pending groups of one account, per state, for Telegram."""
    return " · ".join(f"{s} {tally[s]}" for s in (FRESH, WAITING, APPROVED, CHECK, PARTIAL, FAILED, REJECTED) if tally[s]) or "none pending"
