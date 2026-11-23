"""Built-in tools "runs": the bots' GitHub Actions runs. Read-only: nothing here starts, changes or sends anything.

Each returns text for the model, kept short (MAX_CHARS): a log is searched or tailed, a sheet
summarised, never sent whole.
"""
from __future__ import annotations

from collections import Counter

import json
import re
from pathlib import Path

from ..integrations import github
from ..core.llm import tool

MAX_CHARS = 8000          # every step sends the whole conversation again: keep results small


def _cut(text: str) -> str:
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + f"\n... ({len(text) - MAX_CHARS} more characters cut)"


def _cut_start(head: str, body: str) -> str:
    """head and the end of body: the last lines of a log are the ones that say why it ended."""
    if len(body) <= MAX_CHARS:
        return f"{head}\n{body}"
    return f"{head}\n({len(body) - MAX_CHARS} earlier characters cut) ...\n{body[-MAX_CHARS:]}"


def _out(run_id: int) -> Path:
    path = github.output(run_id)
    if path is None:
        raise ValueError(f"run {run_id} kept no encrypted output (cancelled before upload, or an old run)")
    return path


@tool
def recent_runs(workflow_file: str, count: int = 10) -> str:
    """Recent runs of one bot workflow, newest first: id, conclusion, event, start, minutes, commit.
    Use it to compare a run with the ones before it (usual duration, how often it fails).
    "started" is UTC; tell the owner "started_local" (their time) and count "today" by it. Count every run
    of the day: a bot that runs every 2 hours fails on several of them.

    Args:
        workflow_file: workflow file name, e.g. "ajio-tat.yml", "myntra-spf.yml", "inv-push.yml".
        count: how many runs (max 30).
    """
    return json.dumps(github.runs(workflow_file, min(max(count, 1), 30)), default=str)


@tool
def run_log(run_id: int, grep: str = "", tail: int = 120) -> str:
    """The bot's own log of a run (output/run.log, decrypted). With grep: only the lines matching
    that regular expression (case-insensitive), with a line before and after; else the last lines.

    Args:
        run_id: the GitHub Actions run id.
        grep: optional regex, e.g. "ERROR|WARNING|Traceback" or "Master after merge".
        tail: lines from the end when grep is empty (max 400).
    """
    log = _out(run_id) / "run.log"
    if not log.is_file():
        return "this run has no run.log"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    if grep:
        rx = re.compile(grep, re.I)
        keep = sorted({j for i, ln in enumerate(lines) if rx.search(ln) for j in (i - 1, i, i + 1)
                       if 0 <= j < len(lines)})
        body = "\n".join(lines[j] for j in keep) or f"no line matches {grep!r}"
        return _cut_start(f"{len(lines)} lines in the log, {len(keep)} shown", body)
    n = min(max(tail, 1), 400)
    return _cut(f"{len(lines)} lines in the log, last {min(n, len(lines))}:\n" + "\n".join(lines[-n:]))


@tool
def run_files(run_id: int) -> str:
    """The files the run wrote (its output/ folder): path and size. xlsx files can be read with
    sheet_summary.

    Args:
        run_id: the GitHub Actions run id.
    """
    root = _out(run_id)
    files = [f"{p.relative_to(root).as_posix()}  {p.stat().st_size:,} bytes"
             for p in sorted(root.rglob("*")) if p.is_file() and p.name != "desktop.ini"]
    return _cut("\n".join(files) or "no files")



def _short(v) -> str:
    s = "" if v is None else str(v)
    return s if len(s) <= 40 else s[:37] + "..."


def _label(v) -> str:
    return "(blank)" if v is None or v == "" else str(v)


def _month(v) -> str:
    """YYYY-MM of a date cell or a date text (ISO or "16 Nov 2026"); "NaT" when none (as before)."""
    from datetime import date, datetime
    if isinstance(v, (datetime, date)):
        return f"{v:%Y-%m}"
    s = str(v or "").strip()
    for text in dict.fromkeys((s, s[:19], s[:10])):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y", "%d-%b-%Y", "%d/%m/%Y"):
            try:
                return f"{datetime.strptime(text, fmt):%Y-%m}"
            except ValueError:
                continue
    return "NaT"


def _crosstab(rows: list[str], cols: list[str]) -> str:
    """Rows x columns counts with an All row and column (as pandas' crosstab with margins)."""
    keys_r, keys_c = sorted(set(rows)), sorted(set(cols))
    n = Counter(zip(rows, cols))
    lines = ["  ".join(["month"] + keys_c + ["All"])]
    for r in keys_r:
        cells = [n[(r, c)] for c in keys_c]
        lines.append("  ".join([r] + [str(x) for x in cells] + [str(sum(cells))]))
    totals = [sum(n[(r, c)] for r in keys_r) for c in keys_c]
    lines.append("  ".join(["All"] + [str(x) for x in totals] + [str(sum(totals))]))
    return "\n".join(lines)


@tool
def sheet_summary(run_id: int, path: str, sheet: str = "", group_by: str = "", month_of: str = "") -> str:
    """Summary of one sheet of an xlsx the run wrote: its sheets, row count, every column with how
    many values are filled, the first rows. Optional counts: group_by = a column to count values
    of (top 25); month_of = a date column to count rows per month, crossed with group_by if given.

    Args:
        run_id: the GitHub Actions run id.
        path: the file's path as run_files shows it.
        sheet: sheet name; empty = the first sheet.
        group_by: optional column to count, e.g. "TAT Result" or "Pickup Status".
        month_of: optional date column, e.g. "Order Time".
    """
    f = (_out(run_id) / path).resolve()
    if not f.is_file() or _out(run_id).resolve() not in f.parents:
        return f"no file {path!r} in run {run_id}"
    try:
        from openpyxl import load_workbook
    except ImportError:
        return "openpyxl is not installed here (pip install 'ultron[full]'): xlsx files cannot be read"
    wb = load_workbook(f, read_only=True, data_only=True)
    names = wb.sheetnames
    name = sheet or names[0]
    if name not in names:
        return f"no sheet {name!r}; sheets: {names}"
    from openpyxl.worksheet._read_only import ReadOnlyWorksheet
    ws = wb[name]
    if not isinstance(ws, ReadOnlyWorksheet):
        return f"sheet {name!r} is a chart, not rows; sheets: {names}"
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    head = [str(h) if h is not None else f"Unnamed: {i}" for i, h in enumerate(rows[0])] if rows else []
    body = [r + [None] * (len(head) - len(r)) for r in rows[1:]]
    col = {h: i for i, h in enumerate(head)}

    def filled(v) -> bool:
        return v is not None and not (isinstance(v, str) and v == "")
    parts = [f"sheets: {names}", f"sheet {name!r}: {len(body)} rows, {len(head)} columns",
             "filled per column: " + ", ".join(f"{h}={sum(filled(r[i]) for r in body)}" for h, i in col.items()),
             "first rows:\n" + "\n".join(" | ".join(_short(r[i]) for i in range(len(head))) for r in [head] + body[:5])]
    if month_of and month_of in col:
        months = [_month(r[col[month_of]]) for r in body]
        if group_by and group_by in col:
            groups = [_label(r[col[group_by]]) for r in body]
            parts.append(f"rows per month of {month_of} x {group_by}:\n" + _crosstab(months, groups))
        else:
            counts = Counter(m for m in months)
            parts.append(f"rows per month of {month_of}:\n" + "\n".join(f"{m}  {n}" for m, n in sorted(counts.items())))
    elif group_by and group_by in col:
        counts = Counter(_label(r[col[group_by]]) for r in body)
        parts.append(f"{group_by} counts:\n" + "\n".join(f"{k}  {n}" for k, n in counts.most_common(25)))
    for c in (group_by, month_of):
        if c and c not in col:
            parts.append(f"(no column {c!r})")
    return _cut("\n\n".join(parts))


TOOLS = [recent_runs, run_log, run_files, sheet_summary]
