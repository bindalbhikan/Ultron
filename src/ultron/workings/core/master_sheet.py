"""The SKU master, one file for every working (owner, 24 Nov 2026): Drive AGENT WORK/MASTER SHEET/MasterSheet.xlsx.

Sheets: MasterData (one row per channel listing OMSGuru has, rebuilt every night at 1 AM by the master-sheet
working), REMOVED LISTINGS (the listings OMSGuru no longer has, kept so old orders still map), and the owner's own
Master Sku / Fabric Code / Launch Date & Size Count. Read it only through read() / download() here.

The owner renamed two columns (24 Nov 2026): FINAL SKU -> MASTER SKU, FINAL MY SKU -> MASTER STYLE CODE. read()
gives the old names too, so a reader written for them keeps working.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

FOLDER = "MASTER SHEET"
FILE = "MasterSheet.xlsx"
SHEET = "MasterData"
REMOVED = "REMOVED LISTINGS"
OLD_SHEET = "Master"                       # the layout before 24 Nov 2026
RENAMED = {"MASTER SKU": "FINAL SKU", "MASTER STYLE CODE": "FINAL MY SKU"}   # new name -> the old one


def download(dest: Path) -> Path:
    """MasterSheet.xlsx from AGENT WORK/MASTER SHEET into dest (a copy already there with the same content is reused)."""
    from .drive import agent_folder
    folder = agent_folder(FOLDER)
    path = folder.cached(FILE, Path(dest)) if folder else None
    if path is None:
        raise RuntimeError(f"{FILE} not found in Drive AGENT WORK/{FOLDER}")
    return path


def read(path: Path, removed: bool = True) -> "pl.DataFrame":
    """MasterData (then REMOVED LISTINGS when removed=True) as text columns, with the old column names FINAL SKU /
    FINAL MY SKU added. A file in the old layout (sheet Master) is read as it is."""
    import polars as pl
    from python_calamine import CalamineWorkbook

    from .tables import read_excel_text
    names = CalamineWorkbook.from_path(str(path)).sheet_names
    if SHEET not in names:
        return read_excel_text(path, OLD_SHEET)
    frames = [read_excel_text(path, SHEET)]
    if removed and REMOVED in names:
        frames.append(read_excel_text(path, REMOVED))
    df = pl.concat([f for f in frames if f.width], how="diagonal")
    return df.with_columns(pl.col(new).alias(old) for new, old in RENAMED.items() if new in df.columns and old not in df.columns)


def load(dest: Path, removed: bool = True) -> "pl.DataFrame":
    """download() then read()."""
    return read(download(dest), removed)
