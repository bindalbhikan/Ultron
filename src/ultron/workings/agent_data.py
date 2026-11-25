"""Bindal's data for the agent's dynamic workings (ultron.tools.adhoc): files saved in Drive AGENT WORK, read-only.

    drive:<folder>/<file>   a file under AGENT WORK, e.g. drive:BUSINESS FACTS/MYNTRA.parquet
    master                  the SKU master (AGENT WORK/MASTER SHEET/MasterSheet.xlsx, through core/master_sheet.py)

The agent lists the folders with drive_files. Nothing here writes to Drive.
"""
from __future__ import annotations

import json
from pathlib import Path

from ultron.core.llm import tool
from ultron.tools.adhoc import register_source

from .core import master_sheet

GOOGLE_NATIVE = "application/vnd.google-apps."


def _parts(path: str) -> list[str]:
    parts = [p.strip() for p in path.replace("\\", "/").split("/") if p.strip()]
    if any(p in (".", "..") for p in parts):
        raise ValueError(f"{path!r} is not a path under AGENT WORK")
    return parts


def fetch_drive(path: str, folder: Path) -> Path:
    from .core.drive import agent_folder
    parts = _parts(path)
    if not parts:
        raise ValueError("name a file: drive:<folder>/<file>")
    if [p.upper() for p in parts] == [master_sheet.FOLDER.upper(), master_sheet.FILE.upper()]:
        return fetch_master("", folder)
    where = agent_folder(*parts[:-1])
    if where is None:
        raise ValueError(f"no folder AGENT WORK/{'/'.join(parts[:-1])}")
    found = where.children().get(parts[-1])
    if found is None or found["mimeType"] == where.FOLDER:
        raise ValueError(f"no file {parts[-1]!r} in AGENT WORK/{'/'.join(parts[:-1])}")
    if found["mimeType"].startswith(GOOGLE_NATIVE):
        raise ValueError(f"{parts[-1]} is a Google Docs file; only real files (xlsx, csv, parquet, png) can be read")
    path_ = where.cached(parts[-1], folder, found)
    if path_ is None:
        raise ValueError(f"{parts[-1]} could not be downloaded")
    return path_


def fetch_master(_: str, folder: Path) -> Path:
    return master_sheet.download(folder)


register_source("drive", fetch_drive, "drive:<folder>/<file> under Drive AGENT WORK")
register_source("master", fetch_master, "master: the SKU MasterSheet.xlsx")


@tool
def drive_files(folder: str = "") -> str:
    """The files and folders in Drive AGENT WORK (or a folder under it), to find data for run_adhoc. Read-only.

    Args:
        folder: a path under AGENT WORK, e.g. "BUSINESS FACTS" or "MYNTRA/LISTING GROUPING"; "" for the top.
    """
    from .core.drive import agent_folder
    try:
        parts = _parts(folder)
    except ValueError as exc:
        return f"Error: {exc}"
    where = agent_folder(*parts)
    if where is None:
        return f"Error: no folder AGENT WORK/{folder}"
    rows = [{"name": f["name"], "folder": f["mimeType"] == where.FOLDER, "modified": f.get("modifiedTime", "")[:16],
             **({"google_file": True} if f["mimeType"].startswith(GOOGLE_NATIVE) else {})}
            for f in sorted(where.children().values(), key=lambda f: f["name"])]
    text = json.dumps(rows[:300], ensure_ascii=False)
    return text + (f"\n... {len(rows) - 300} more" if len(rows) > 300 else "")


TOOLS = [drive_files]
