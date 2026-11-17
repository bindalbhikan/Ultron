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
from datetime import date, datetime
from pathlib import Path

from .drive import API, DriveFolder, agent_folder

log = logging.getLogger("bindal.portal_reports")

ROOT = "PORTAL REPORTS"
KINDS = {"sale": "ORDER REPORT", "return": "RETURN REPORT", "payment": "PAYMENT REPORT",
         "sales": "SALES REPORT",   # SALES REPORT: Flipkart's tax Sales Report (every sale / return / cancel event, invoice value)
         "omsguru": "OMSGURU REPORT",   # OMSGURU REPORT: OMSGuru's order lines of the portal's channels (status of each line)
         "monthly": "MONTHLY REPORT"}   # MONTHLY REPORT: the owner's monthly file (order lines + settlement), months the portal no longer gives


def label(month: date) -> str:
    return f"{month:%b-%y}"          # Oct-26 (the folder)


def file_name(portal: str, month: date, kind: str, account: str = "", ext: str = ".xlsx",
              partial: bool = False) -> str:
    parts = [portal.upper(), account.upper(), KINDS[kind], label(month).upper()] + (["PARTIAL"] if partial else [])
    return " ".join(p for p in parts if p) + ext


def month_folder(portal: str, month: date, create: bool = False) -> DriveFolder | None:
    """PORTAL REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/ on Drive."""
    folder = agent_folder()
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


def save_partial(portal: str, month: date, kind: str, file: Path | None, account: str = "") -> str:
    """Save file as the month's <kind> report marked PARTIAL (a month not over: the returns of its 1st to
    14th, kept by the 15th's return analysis) unless the month already has its whole report: that one stays."""
    if file is None:
        return ""
    folder = month_folder(portal, month)
    whole = file_name(portal, month, kind, account, "")
    if folder and any(n.startswith(whole) and " PARTIAL" not in n for n in folder.children()):
        log.info("PORTAL REPORTS/%s %s: the whole %s report is there, the partial one not saved",
                 portal.upper(), label(month), kind)
        return ""
    return save(portal, month, kind, file, account, partial=True)


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
    import polars as pl

    from .tables import read_excel_text
    from .xlsx import write_sheets
    # read as pandas read them (openpyxl: AJIO's texts keep their outer spaces); Polars from here
    frames = [df for f in files if (df := read_excel_text(f, sheet or 0, engine="openpyxl")).height]
    if not frames:
        return None
    df = pl.concat(frames, how="diagonal_relaxed")
    cols = [c for c in date_cols if c in df.columns]
    if not cols:
        raise ValueError(f"none of the date columns {date_cols} in {[f.name for f in files]}")
    raw = pl.coalesce([pl.col(c) for c in cols])                  # the first filled one decides
    day = parse(raw) if parse else raw.str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False).cast(pl.Datetime("us"))
    first = datetime(month.year, month.month, 1)
    nxt = datetime(month.year + month.month // 12, month.month % 12 + 1, 1)
    df = df.filter((day >= first) & (day < nxt))
    if key:
        df = df.unique([k for k in key if k in df.columns], keep="last", maintain_order=True)
    if not df.height:
        return None
    write_sheets(out, {sheet or "Sheet1": (df.columns, df.rows())}, bold_header=True)
    return out, df.height
