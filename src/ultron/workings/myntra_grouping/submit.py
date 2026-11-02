"""Submitting the pending colour groups on the Myntra partner portal, and keeping the record of it.

  sync_jobs     every style-grouping job on the portal goes into the record (also those uploaded by
                hand: BY = Portal, their style ids read from the job's input file), and the status and
                counts of every job are read again (WAITING, APPROVAL_PENDING, COMPLETED,
                PARTIAL_COMPLETE, FAILED). Myntra approves an upload before it goes live.
  submit        the upload files of TEMPLATES/<day>/ACC-<seller id>/ are uploaded on their account
                (only with --submit, the owner's call). A group holding a style of a job still
                waiting on the portal is skipped, so nothing is sent twice.
  The record    Drive AGENT WORK/MYNTRA/LISTING GROUPING/GROUPING SUBMISSIONS.xlsx, one row per upload,
                kept for good, newest first.
  apply         the report (MYNTRA GROUPING MASTER.xlsx) gets a SUBMISSIONS sheet and, on the account
                sheets, SUBMITTED ON, JOB ID and JOB STATUS of each style's newest upload.
"""
from __future__ import annotations

import io
import logging
import re
import time
from datetime import datetime, timedelta
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
            jobs = portal.style_grouping_jobs(200)
            mp.save_to_worker(env, portal.cookies(), account)
        except Exception as exc:  # noqa: BLE001 - one account never stops the others
            problems.append(f"{account}: grouping jobs not read ({str(exc).splitlines()[0][:100]})")
            continue
        known = set(record["JOB ID"].astype(str))
        for j in jobs:
            jid = str(j.get("id"))
            counts = [str(j.get("status") or ""), str(j.get("totalRecords") or 0), str(j.get("processedRecords") or 0),
                      str(j.get("erredRecords") or 0)]
            if jid in known:
                record.loc[record["JOB ID"].astype(str) == jid,
                           ["JOB STATUS", "TOTAL RECORDS", "PROCESSED RECORDS", "ERRED RECORDS"]] = counts
                continue
            uid, styles = _job_styles(j)
            day, at = _when(j.get("createdAt"))
            new.append({"SUBMITTED ON": day, "TIME": at, "ACCOUNT": account, "SELLER ID": SELLER_OF[account],
                        "UNIQUE ID": uid, "BRAND": "", "ARTICLE TYPE": "", "FILE": "", "STYLES": str(len(styles)),
                        "STYLE IDS": ", ".join(styles), "JOB ID": jid, "JOB STATUS": counts[0], "TOTAL RECORDS": counts[1],
                        "PROCESSED RECORDS": counts[2], "ERRED RECORDS": counts[3], "BY": "Portal"})
    if new:
        record = pd.concat([record, pd.DataFrame(new, columns=COLS)], ignore_index=True)
    return record, problems


def failure_reasons(record: pd.DataFrame) -> pd.DataFrame:
    """PORTAL REMARK of the bot's failed jobs: the reason in the job's result report."""
    import zipfile
    from ..return_analysis.sources import myntra_portal
    record, portals = record.copy(), {}
    todo = record[(record["BY"] == "Ultron") & (record["JOB STATUS"].isin(["FAILED", "PARTIAL_COMPLETE"]))
                  & (record["PORTAL REMARK"].isna() | (record["PORTAL REMARK"].astype(str) == ""))]
    for i, r in todo.iterrows():
        try:
            portal = portals.setdefault(r["ACCOUNT"], myntra_portal(r["ACCOUNT"]))
            z = zipfile.ZipFile(io.BytesIO(requests.get(portal.style_grouping_report(int(r["JOB ID"])), timeout=60).content))
            df = pd.read_csv(z.open(z.namelist()[0]), dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            bad = df[df["Remarks"].astype(str).str.strip().str.upper() != "SUCCESS"]["Remarks"].dropna().unique()
            record.loc[i, "PORTAL REMARK"] = " | ".join(str(x).strip() for x in bad)[:300]
        except Exception as exc:  # noqa: BLE001 - the reason is only a help
            log.info("Report of job %s not read: %s", r["JOB ID"], str(exc)[:100])
    return record


def failed_uploads(record: pd.DataFrame) -> set[tuple[str, frozenset]]:
    """(seller id, the style set) of uploads Myntra failed: the same upload would fail again."""
    bad = record[record["JOB STATUS"].astype(str) == "FAILED"]
    return {(str(r["SELLER ID"]), frozenset(str(r["STYLE IDS"]).split(", "))) for _, r in bad.iterrows()}


def waiting_styles(record: pd.DataFrame) -> set[tuple[str, str]]:
    """(seller id, style id) of every job not finished yet."""
    out = set()
    for _, r in record.iterrows():
        status = str(r["JOB STATUS"])
        if status in FINISHED or status.startswith("NOT SUBMITTED") or status == "nan":
            continue
        out |= {(str(r["SELLER ID"]), s) for s in str(r["STYLE IDS"]).split(", ") if s}
    return out


def submit(folder: Path, record: pd.DataFrame, limit: int = 0, pause: float = 0.005) -> tuple[pd.DataFrame, list[str], int, int]:
    """Upload the files of folder/ACC-<seller id>/; (record, problems, submitted, skipped).
    limit: at most that many groups in all (a test)."""
    from ..portals import myntra as mp
    from ..return_analysis.sources import env, myntra_portal
    rows, problems, skipped = [], [], 0
    waiting, failed = waiting_styles(record), failed_uploads(record)
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
            if any((seller, s) in waiting for s in styles) or (seller, frozenset(styles)) in failed:
                skipped += 1
                log.info("%s %s: waiting on the portal, or the same upload failed before: skipped", account, f.name)
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
    return record.sort_values(["SUBMITTED ON", "TIME"], ascending=False, na_position="last")


def write_record(record: pd.DataFrame, path: Path) -> Path:
    from .engine import format_workbook
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        _newest_first(record).to_excel(xw, sheet_name="SUBMISSIONS", index=False)
        format_workbook(xw.book)
    return path


def apply(report: Path, record: pd.DataFrame) -> None:
    """SUBMITTED ON, JOB ID and JOB STATUS of each style's newest upload on the account sheets, and the
    SUBMISSIONS sheet."""
    from openpyxl import load_workbook
    from .engine import format_workbook
    latest: dict[tuple[str, str], tuple] = {}
    for _, r in _newest_first(record).iloc[::-1].iterrows():
        if str(r["JOB ID"]) in ("", "nan"):
            continue
        for sid in str(r["STYLE IDS"]).split(", "):
            latest[(str(r["SELLER ID"]), sid)] = (r["SUBMITTED ON"], r["JOB ID"], r["JOB STATUS"])
    wb = load_workbook(report)
    for ws in wb.worksheets:
        if not ws.title.startswith("ACC-"):
            continue
        seller = ws.title[4:]
        head = [c.value for c in ws[1]]
        col = len(head) + 1
        for j, h in enumerate(["SUBMITTED ON", "JOB ID", "JOB STATUS"]):
            ws.cell(1, col + j, h)
        isid = head.index("Style ID")
        for row in ws.iter_rows(min_row=2, max_col=len(head)):
            sid = str(row[isid].value or "").replace(".0", "").strip()
            for j, v in enumerate(latest.get((seller, sid), ())):
                ws.cell(row[0].row, col + j, v)
    ws = wb.create_sheet("SUBMISSIONS")
    ws.append(COLS)
    for r in _newest_first(record).itertuples(index=False):
        ws.append(["" if pd.isna(v) else v for v in r])
    format_workbook(wb)
    wb.save(report)
