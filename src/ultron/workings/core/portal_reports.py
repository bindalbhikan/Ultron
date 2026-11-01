"""The portals' monthly reports, kept on Drive for every later working:

    AGENT WORK/PORTAL REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/<PORTAL> [<ACCOUNT>] <KIND> REPORT <MON-YY>[ PARTIAL].<ext>

e.g. AJIO/2026/Oct-26/AJIO ORDER REPORT OCT-26.xlsx, MYNTRA/2026/Oct-26/MYNTRA MAIN RETURN REPORT
OCT-26.csv. No sub folders: the name says what a file is (ORDER / RETURN / PAYMENT REPORT, owner's
rule 1 Nov 2026). Every file holds one calendar month, 1st to last day; PARTIAL = days are missing
(its source had gaps). Saved by portal-reports on the 2nd (order + payment reports) and the return
analysis on the 10th / 15th (return reports); read by the business reporting, so a report is
downloaded once. A file of the same name is replaced (a run again).
"""
from __future__ import annotations

import logging
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

from .config import env
from .drive import API, DriveFolder

log = logging.getLogger("bindal.portal_reports")

AGENT_WORK = "1uO-aOha_QKkI3f19EA7sweYPgkjMukZI"   # Drive BINDAL EXPORTS/AGENT WORK
ROOT = "PORTAL REPORTS"
KINDS = {"sale": "ORDER REPORT", "return": "RETURN REPORT", "payment": "PAYMENT REPORT",
         "sales": "SALES REPORT"}   # SALES REPORT: Flipkart's tax Sales Report (every sale / return / cancel event, invoice value)


def label(month: date) -> str:
    return f"{month:%b-%y}"          # Oct-26 (the folder)


def file_name(portal: str, month: date, kind: str, account: str = "", ext: str = ".xlsx",
              partial: bool = False) -> str:
    parts = [portal.upper(), account.upper(), KINDS[kind], label(month).upper()] + (["PARTIAL"] if partial else [])
    return " ".join(p for p in parts if p) + ext


def month_folder(portal: str, month: date, create: bool = False) -> DriveFolder | None:
    """PORTAL REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/ on Drive."""
    folder = DriveFolder(env("AGENT_WORK_FOLDER_ID", AGENT_WORK))
    for name in (ROOT, portal.upper(), f"{month:%Y}", label(month)):
        folder = folder.subfolder(name, create=create)
        if folder is None:
            return None
    return folder


def _trash(folder: DriveFolder, file_id: str, name: str) -> None:
    r = folder.http.patch(f"{API}/{file_id}", params={"supportsAllDrives": "true"}, json={"trashed": True}, timeout=60)
    folder._check(r, f"trash of {name}")
    log.info("PORTAL REPORTS: %s moved to the trash", name)


def save(portal: str, month: date, kind: str, file: Path | None, account: str = "",
         keep_existing: bool = False, partial: bool = False) -> str:
    """Upload file as the month's <kind> report (of the account); the name saved, "" when nothing
    was. keep_existing: kept as it is when the month already has that report. The other version
    (PARTIAL or not) of the same report goes to the Drive trash."""
    if file is None:
        return ""
    name = file_name(portal, month, kind, account, file.suffix.lower() or ".xlsx", partial)
    folder = month_folder(portal, month, create=True)
    base = file_name(portal, month, kind, account, "")
    have = {n: m for n, m in folder.children().items() if n.startswith(base)}
    if keep_existing and have:
        log.info("PORTAL REPORTS/%s %s: %s already there, kept", portal.upper(), label(month), next(iter(have)))
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        src = file if file.name == name else Path(shutil.copy2(file, Path(tmp) / name))
        folder.put(src, "application/octet-stream")
    for n, meta in have.items():
        if n != name:
            _trash(folder, meta["id"], n)
    log.info("PORTAL REPORTS/%s/%s: %s", portal.upper(), label(month), name)
    return name


def load(portal: str, month: date, kind: str, dest: Path, account: str = "") -> list[Path]:
    """The month's <kind> report files (every account's when account is empty) into dest."""
    folder = month_folder(portal, month)
    if not folder:
        return []
    pat = re.compile(rf"^{re.escape(portal.upper())} (\w+ )?{KINDS[kind]} {label(month).upper()}( PARTIAL)?\.")
    out = []
    for n in folder.children():
        m = pat.match(n)
        if m and (not account or (m.group(1) or "").strip() == account.upper()):
            p = folder.download(n, dest / n)
            if p:
                out.append(p)
    return out


def month_slice(files: list[Path], month: date, date_cols: list[str], out: Path, sheet: str | None = None,
                parse=None, key: list[str] | None = None) -> tuple[Path, int] | None:
    """The rows of the calendar month (1st to last day) of report files that cover more than that
    month (a returns window of the 1st to the next 14th, 30-day downloads), in one xlsx at out:
    the first filled column of date_cols decides a row's day; rows of the same key are kept once,
    the later file winning. None when the files hold no row of the month."""
    import pandas as pd
    frames = []
    for f in files:
        df = pd.read_excel(f, sheet_name=sheet or 0, dtype=str)
        if not df.empty:
            frames.append(df)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    raw = None
    for c in date_cols:
        if c in df.columns:
            raw = df[c] if raw is None else raw.fillna(df[c])
    if raw is None:
        raise ValueError(f"none of the date columns {date_cols} in {[f.name for f in files]}")
    day = parse(raw) if parse else pd.to_datetime(raw.str[:10], errors="coerce")
    first = pd.Timestamp(month.replace(day=1))
    df = df[(day >= first) & (day < first + pd.offsets.MonthBegin(1))]
    if key:
        df = df.drop_duplicates([k for k in key if k in df.columns], keep="last")
    if df.empty:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out) as xw:
        df.to_excel(xw, sheet_name=sheet or "Sheet1", index=False)
    return out, len(df)
