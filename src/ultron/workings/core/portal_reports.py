"""The portals' monthly sale and return reports, kept on Drive for every later working:

    AGENT WORK/PORTAL REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/Sale Report <Mon-YY>/
                                                     /Return Report <Mon-YY>/

(e.g. AJIO/2026/Oct-26/Sale Report Oct-26/). The return analysis saves what it downloads on the 15th
(Myntra orders + returns of every account, AJIO orders + RTV, Flipkart Sales Report + Returns), and
the business reporting reads them from here: a report is downloaded once. A Myntra file is named
after its account ("MAIN <file>"); a file already there is replaced (a run again the same month).
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import date
from pathlib import Path

from .config import env
from .drive import DriveFolder

log = logging.getLogger("bindal.portal_reports")

AGENT_WORK = "1uO-aOha_QKkI3f19EA7sweYPgkjMukZI"   # Drive BINDAL EXPORTS/AGENT WORK
ROOT = "PORTAL REPORTS"
KINDS = {"sale": "Sale Report", "return": "Return Report"}


def label(month: date) -> str:
    return f"{month:%b-%y}"          # Oct-26


def month_folder(portal: str, month: date, kind: str, create: bool = False) -> DriveFolder | None:
    """PORTAL REPORTS/<PORTAL>/<YYYY>/<Mon-YY>/<Sale|Return> Report <Mon-YY>/ on Drive."""
    folder = DriveFolder(env("AGENT_WORK_FOLDER_ID", AGENT_WORK))
    for name in (ROOT, portal.upper(), f"{month:%Y}", label(month), f"{KINDS[kind]} {label(month)}"):
        folder = folder.subfolder(name, create=create)
        if folder is None:
            return None
    return folder


def save(portal: str, month: date, kind: str, files: list[Path], prefix: str = "") -> list[str]:
    """Upload files into the month's folder (names prefixed, e.g. the Myntra account); names saved."""
    if not files:
        return []
    folder = month_folder(portal, month, kind, create=True)
    saved = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            name = f"{prefix} {f.name}" if prefix and not f.name.startswith(prefix + " ") else f.name
            src = f if name == f.name else Path(shutil.copy2(f, Path(tmp) / name))
            folder.put(src, "application/octet-stream")
            saved.append(name)
    log.info("PORTAL REPORTS/%s %s %s: %d file(s)", portal.upper(), label(month), KINDS[kind], len(saved))
    return saved


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


def load(portal: str, month: date, kind: str, dest: Path) -> list[Path]:
    """Every file of the month's folder into dest (empty when nothing was saved for that month)."""
    folder = month_folder(portal, month, kind)
    return folder.download_all(dest) if folder else []
