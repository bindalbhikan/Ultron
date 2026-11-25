"""Built-in tools "adhoc": dynamic workings. When no report or tool gives what the owner asked for, the agent
writes a short Python (Polars) script, runs it on copies of saved data in the locked sandbox (core/sandbox.py)
and sends the result to the same chat (send_file). Works the same from Telegram and the app.

The script can change nothing: no network, no secrets, no portal, no Drive; it reads /data and writes /out.
Its results are labelled ad-hoc: they are not checked reports, so they never go into the reports, the
dashboard or Drive. A working that is wanted again is made permanent with the codechange action (a PR).

Data sources (comma or line separated):

    run:<run id>/<path>     a file a bot's run wrote
    adhoc:<id>/<file>       a result of an earlier dynamic working
    <prefix>:<name>         a seller's own source, registered with register_source() (Bindal: drive:, master)
"""
from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Callable

from ..core import sandbox
from ..core.llm import tool
from .files import adhoc_root, resolve

log = logging.getLogger("ultron")
DATA_MAX_BYTES = 400 * 1024 * 1024
MAX_SOURCES = 10

# prefix -> (fetch(name, folder) -> local path, one line for the model)
SOURCES: dict[str, tuple[Callable[[str, Path], Path], str]] = {}


def register_source(prefix: str, fetch: Callable[[str, Path], Path], about: str) -> None:
    """Let run_adhoc read `<prefix>:<name>`: fetch copies that file into the folder and returns its path."""
    SOURCES[prefix] = (fetch, about)


def _fetch(source: str, folder: Path) -> Path:
    prefix, _, name = source.partition(":")
    if prefix in ("run", "adhoc"):
        return resolve(source)
    if prefix in SOURCES and name.strip():
        return SOURCES[prefix][0](name.strip(), folder)
    known = ", ".join(["run:<run id>/<path>", "adhoc:<id>/<file>"] + [f"{p}: ({a})" for p, (_, a) in SOURCES.items()])
    raise ValueError(f"unknown data source {source!r}; use {known}")


def _gather(data: str, into: Path) -> list[str]:
    sources = [s.strip() for s in re.split(r"[,\n]", data) if s.strip()]
    if len(sources) > MAX_SOURCES:
        raise ValueError(f"at most {MAX_SOURCES} data sources")
    names, total = [], 0
    fetched = into.parent / "fetched"
    for i, source in enumerate(sources):
        path = _fetch(source, fetched / str(i))
        total += path.stat().st_size
        if total > DATA_MAX_BYTES:
            raise ValueError(f"the data is over {DATA_MAX_BYTES // 2**20} MB; use fewer or smaller files")
        name = path.name if path.name not in names else f"{i}_{path.name}"
        shutil.copyfile(path, into / name)
        names.append(name)
    return names


@tool
def run_adhoc(script: str, data: str = "", purpose: str = "") -> str:
    """Do a working no report or tool covers: run a Python script you write on copies of saved data, then send its
    result with send_file. The script runs locked: no network, no secrets, no portal or Drive access; it reads the
    files under /data (read-only) and writes results to /out (the working folder). Libraries: polars (tables;
    pl.read_excel reads xlsx through calamine, pl.read_parquet, pl.read_csv), xlsxwriter (xlsx, with native Excel
    charts), Pillow, the standard library. No pandas, no openpyxl, no matplotlib. Print a short summary (and
    df.schema when you do not know the columns yet); a failed script shows its error, fix it and run again.
    Results are ad-hoc, not checked reports: say so to the owner. Never invent data the files do not hold.

    Args:
        script: the whole Python script.
        data: the data sources, comma separated: run:<run id>/<path>, adhoc:<id>/<file>, or a seller source
            such as drive:<folder>/<file> under AGENT WORK (drive_files lists them) or master (the SKU master).
        purpose: one line: what the working is for (kept in the log).
    """
    reason = sandbox.unavailable()
    if reason:
        return f"Dynamic workings cannot run here: {reason}."
    run_id = uuid.uuid4().hex[:12]
    work = adhoc_root() / run_id
    data_dir = work / "data"
    data_dir.mkdir(parents=True)
    try:
        names = _gather(data, data_dir)
    except Exception as exc:  # noqa: BLE001 - the model fixes its sources
        shutil.rmtree(work, ignore_errors=True)
        return f"Error in data: {exc}"
    log.info("Dynamic working %s (%s) on %s", run_id, purpose[:200], names)
    try:
        result = sandbox.run(script, data_dir, work / "run")
    except RuntimeError as exc:
        return f"Dynamic workings cannot run here: {exc}."
    out = work / "out"
    shutil.move(str(work / "run" / "out"), out)
    files = [f"adhoc:{run_id}/{p.relative_to(out).as_posix()}  {p.stat().st_size:,} bytes"
             for p in sorted(out.rglob("*")) if p.is_file()]
    state = "timed out" if result.timed_out else ("finished" if result.code == 0 else f"failed (exit {result.code})")
    return (f"Script {state}. /data had: {', '.join(names) or 'nothing'}.\n"
            f"Results:\n{chr(10).join(files) if files else 'none'}\n"
            f"Output:\n{result.output or '(nothing printed)'}"
            + ("\nSend a result with send_file(source)." if files and result.code == 0 else ""))


TOOLS = [run_adhoc]
