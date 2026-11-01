"""Submitting the pending colour groups on the Myntra partner portal, and keeping the record of it.

  submit(day)   every upload file of TEMPLATES/<day>/ACC-<seller id>/ (the pending groups of that day's
                run) is uploaded on its account (Catalog > Style Grouping: upload token, the file to the
                CMS blob store, style-grouping/bulk-upload/submit). A group already submitted (the same
                account, Unique ID, brand and article on that day) is not sent again.
  The record:   Drive AGENT WORK/MYNTRA/LISTING GROUPING/GROUPING SUBMISSIONS.xlsx, one row per upload,
                kept for good: SUBMITTED ON, TIME, ACCOUNT, SELLER ID, UNIQUE ID, BRAND, ARTICLE TYPE, FILE,
                STYLES, STYLE IDS, JOB ID, JOB STATUS, TOTAL / PROCESSED / ERRED RECORDS, BY
  apply(master) MYNTRA GROUPING MASTER.xlsx gets a SUBMISSIONS sheet (the record, newest first) and, on the
                account sheets, SUBMITTED ON and JOB ID for the styles each upload carried.
Job statuses are read again from the portal on every run (WAITING, APPROVAL_PENDING, COMPLETED,
PARTIAL_COMPLETE, FAILED).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger("bindal.myntra_grouping")

RECORD = "GROUPING SUBMISSIONS.xlsx"
COLS = ["SUBMITTED ON", "TIME", "ACCOUNT", "SELLER ID", "UNIQUE ID", "BRAND", "ARTICLE TYPE", "FILE", "STYLES",
        "STYLE IDS", "JOB ID", "JOB STATUS", "TOTAL RECORDS", "PROCESSED RECORDS", "ERRED RECORDS", "BY"]
ACCOUNT_OF = {"19170": "MAIN", "32207": "DBCC", "35426": "FMCC"}


def read_record(path: Path | None) -> pd.DataFrame:
    if path and path.exists():
        df = pd.read_excel(path, sheet_name="SUBMISSIONS", dtype=str)
        return df.reindex(columns=COLS)
    return pd.DataFrame(columns=COLS)


def template_rows(path: Path) -> tuple[str, list[str]]:
    """(unique id, style ids) of one upload file."""
    df = pd.read_excel(path, dtype=str)
    uid = str(df.iloc[0, 0]).strip() if len(df) else ""
    return uid, [str(x).replace(".0", "").strip() for x in df.iloc[:, 2].dropna()]


def submit(day: str, folder: Path, record: pd.DataFrame, accounts: set[str] | None = None,
           pause: float = 1.0) -> tuple[pd.DataFrame, list[str]]:
    """Upload every file of folder/ACC-<seller id>/ for that day; the record with the new rows and
    the problems (one line each)."""
    from ..portals import myntra as mp
    from ..return_analysis.sources import env, myntra_portal
    rows, problems = [], []
    done = {(r["SELLER ID"], r["UNIQUE ID"], r["FILE"]) for _, r in record.iterrows() if r["SUBMITTED ON"] == day}
    for acc_dir in sorted(p for p in folder.iterdir() if p.is_dir() and p.name.startswith("ACC-")):
        seller = acc_dir.name[4:]
        account = ACCOUNT_OF.get(seller, seller)
        if accounts and account not in accounts:
            continue
        files = sorted(acc_dir.glob("*.xlsx"))
        if not files:
            continue
        try:
            portal = myntra_portal(account)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{account}: no session ({exc})")
            continue
        for f in files:
            uid, styles = template_rows(f)
            m = re.match(r"^(\d+)_(.+)_(.+)\.xlsx$", f.name)
            brand, article = (m.group(2), m.group(3)) if m else ("", "")
            if (seller, uid, f.name) in done:
                continue
            try:
                job = portal.style_grouping_submit(f.name, f.read_bytes())
                status = "SUBMITTED"
            except Exception as exc:  # noqa: BLE001 - one group never stops the others
                job, status = "", f"NOT SUBMITTED: {str(exc).splitlines()[0][:120]}"
                problems.append(f"{account} {f.name}: {status}")
            rows.append({"SUBMITTED ON": day, "TIME": f"{datetime.now():%H:%M}", "ACCOUNT": account, "SELLER ID": seller,
                         "UNIQUE ID": uid, "BRAND": brand, "ARTICLE TYPE": article, "FILE": f.name, "STYLES": len(styles),
                         "STYLE IDS": ", ".join(styles), "JOB ID": str(job), "JOB STATUS": status, "BY": "Ultron"})
            time.sleep(pause)
        mp.save_to_worker(env, portal.cookies(), account)
    return pd.concat([record, pd.DataFrame(rows, columns=COLS)], ignore_index=True), problems


def refresh_status(record: pd.DataFrame) -> pd.DataFrame:
    """JOB STATUS and the record counts of every job, read again from the portal."""
    from ..return_analysis.sources import myntra_portal
    if not len(record):
        return record
    record = record.copy()
    for account in sorted(set(record["ACCOUNT"].dropna())):
        try:
            jobs = {str(j["id"]): j for j in myntra_portal(account).style_grouping_jobs(200)}
        except Exception as exc:  # noqa: BLE001
            log.warning("Grouping jobs of %s not read: %s", account, exc)
            continue
        for i, r in record[record["ACCOUNT"] == account].iterrows():
            j = jobs.get(str(r["JOB ID"]))
            if j:
                record.loc[i, ["JOB STATUS", "TOTAL RECORDS", "PROCESSED RECORDS", "ERRED RECORDS"]] = [
                    j.get("status"), str(j.get("totalRecords") or 0), str(j.get("processedRecords") or 0),
                    str(j.get("erredRecords") or 0)]
    return record


def write_record(record: pd.DataFrame, path: Path) -> Path:
    from .engine import format_workbook
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        record.sort_values(["SUBMITTED ON", "TIME"], ascending=False).to_excel(xw, sheet_name="SUBMISSIONS", index=False)
        format_workbook(xw.book)
    return path


def apply(master: Path, record: pd.DataFrame) -> None:
    """SUBMITTED ON and JOB ID on the account sheets (the newest upload of each style), and the
    SUBMISSIONS sheet, in MYNTRA GROUPING MASTER.xlsx."""
    from openpyxl import load_workbook
    from .engine import format_workbook
    if not len(record):
        return
    latest = {}
    for _, r in record.sort_values(["SUBMITTED ON", "TIME"]).iterrows():
        if not str(r["JOB ID"]).strip() or str(r["JOB ID"]) == "nan":
            continue
        for sid in str(r["STYLE IDS"]).split(", "):
            latest[(str(r["SELLER ID"]), str(r["UNIQUE ID"]), sid)] = (r["SUBMITTED ON"], r["JOB ID"], r["JOB STATUS"])
    wb = load_workbook(master)
    for ws in wb.worksheets:
        if not ws.title.startswith("ACC-"):
            continue
        seller = ws.title[4:]
        head = [c.value for c in ws[1]]
        if "JOB ID" in head:
            continue
        col = len(head) + 1
        for j, h in enumerate(["SUBMITTED ON", "JOB ID", "JOB STATUS"]):
            ws.cell(1, col + j, h)
        iu, isid = head.index("Unique ID"), head.index("Style ID")
        for row in ws.iter_rows(min_row=2):
            uid = str(row[iu].value or "").strip().zfill(3)
            sid = str(row[isid].value or "").replace(".0", "").strip()
            hit = latest.get((seller, uid, sid))
            if hit:
                for j, v in enumerate(hit):
                    ws.cell(row[0].row, col + j, v)
    if "SUBMISSIONS" in wb.sheetnames:
        del wb["SUBMISSIONS"]
    ws = wb.create_sheet("SUBMISSIONS")
    rec = record.sort_values(["SUBMITTED ON", "TIME"], ascending=False)
    ws.append(COLS)
    for r in rec.itertuples(index=False):
        ws.append(["" if pd.isna(v) else v for v in r])
    format_workbook(wb)
    wb.save(master)
