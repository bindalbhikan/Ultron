#!/usr/bin/env python
"""Keep the agent docs in step with the code:  python scripts/docs/sync_docs.py [--check]

Rewrites the generated blocks (between <!-- AUTO:<name> --> and <!-- /AUTO:<name> -->) of
docs/CONTEXT.md and AGENTS.md from the code itself:
  workings   every bot of run.py (BOTS + its docstring), its workflow (name), when it runs (TASKS of
             the work schedule, else the **When** line of its docs/bots page) and its page
  gaps       what is missing: a bot without a docs/bots page, a workflow no bot or doc names,
             a bot workflow the watcher (agent-watch.yml) does not watch
and keeps CLAUDE.md importing AGENTS.md. The "Last synced" line changes only when a block did.

Run by: the "Docs sync" workflow on every push to main (commits the result), and by every agent
before it commits (AGENTS.md). --check exits 1 when a file
would change (nothing written).
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
IST = timezone(timedelta(hours=5, minutes=30))

# bots whose workflow is not <bot>.yml, or that run on an event rather than a schedule
WORKFLOW = {"work-schedule": "agent-watch.yml"}
NOT_WATCHED = {"agent-watch.yml", "agent-chat.yml", "ci-fix.yml", "android-app.yml", "docs-sync.yml",
               "tests.yml", "myntra-history.yml", "sms-catchup.yml"}


def bots() -> tuple[dict[str, str], dict[str, str]]:
    """(bot -> module, bot -> one-line description) from run.py, read without importing it."""
    tree = ast.parse((ROOT / "run.py").read_text(encoding="utf-8"))
    table: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "BOTS" for t in node.targets):
            table = ast.literal_eval(node.value)
    about = {}
    for line in (ast.get_docstring(tree) or "").splitlines():
        m = re.match(r"\s+([a-z][a-z0-9-]+)\s+(.+?)\s+python run\.py", line)
        if m:
            about[m.group(1)] = m.group(2).strip()
    return table, about


def workflow_names() -> dict[str, str]:
    out = {}
    for p in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        m = re.search(r"^name:\s*(.+)$", p.read_text(encoding="utf-8"), re.M)
        out[p.name] = m.group(1).strip().strip('"') if m else p.stem
    return out


def schedule() -> dict[str, list[str]]:
    """workflow -> ["9:00 AM DAILY", ...] from the work schedule's TASKS (the worker's SCHEDULE)."""
    try:
        from ultron.workings.work_schedule.pipeline import TASKS
    except Exception as exc:  # noqa: BLE001 - the table then uses the docs' When lines
        print(f"note: work schedule not read ({exc}); using the docs' When lines", file=sys.stderr)
        return {}
    out: dict[str, list[str]] = {}
    for t in sorted(TASKS, key=lambda t: t.slots[0]):
        entry = f"{t.time} {t.every.lower()}"
        if entry not in out.setdefault(t.workflow, []):
            out[t.workflow].append(entry)
    return out


def when_line(page: Path) -> str:
    if not page.is_file():
        return ""
    text = page.read_text(encoding="utf-8")
    m = re.search(r"^\*\*When\*\*:\s*(.+?)(?:\n\s*\n|\n\*\*|$)", text, re.M | re.S)
    if not m:
        return ""
    line = " ".join(m.group(1).split())
    line = re.split(r"(?<=[.;])\s|\s\(", line)[0].rstrip(".;,")
    return line[:90]


def title(page: Path) -> str:
    if not page.is_file():
        return ""
    first = page.read_text(encoding="utf-8").splitlines()[0]
    return re.sub(r"^#\s*|\s+[—-]\s+`.*$", "", first).strip()


def esc(text: str) -> str:
    return text.replace("|", "\\|")


def workings_block() -> tuple[str, list[str]]:
    table, about = bots()
    names, when = workflow_names(), schedule()
    watched = (ROOT / ".github" / "workflows" / "agent-watch.yml").read_text(encoding="utf-8")
    rows, gaps = [], []
    for bot in sorted(table):
        wf = WORKFLOW.get(bot, f"{bot}.yml")
        page = ROOT / "docs" / "bots" / f"{bot}.md"
        if wf not in names:
            wf = ""
        runs = "; ".join(when.get(wf, [])) if wf != "agent-watch.yml" else ""
        runs = runs or when_line(page) or "by hand"
        what = about.get(bot) or title(page) or bot
        rows.append(f"| {bot} | `python run.py {bot}` | {esc(what)} | "
                    f"{('`' + wf + '` ' + esc(names[wf])) if wf else '—'} | {esc(runs)} | "
                    f"{('`docs/bots/' + bot + '.md`') if page.is_file() else '**missing**'} |")
        if not page.is_file():
            gaps.append(f"`{bot}` has no page `docs/bots/{bot}.md`")
        if wf and wf not in NOT_WATCHED and names[wf] not in watched and bot != "work-schedule":
            gaps.append(f"`{wf}` ({names[wf]}) is not watched: add its name to `agent-watch.yml`")
    used = {WORKFLOW.get(b, f"{b}.yml") for b in table}
    for wf, name in names.items():
        if wf not in used and wf not in NOT_WATCHED:
            gaps.append(f"`{wf}` ({name}) belongs to no bot of `run.py`")
    head = ("| Bot | Run | What it does | Workflow | When (IST) | Page |\n"
            "|---|---|---|---|---|---|")
    return head + "\n" + "\n".join(rows), gaps


def gaps_block(gaps: list[str]) -> str:
    return "\n".join(f"- {g}" for g in gaps) if gaps else "- none: every bot has its page and its workflow is watched"


def replace_block(text: str, name: str, body: str) -> str:
    start, end = f"<!-- AUTO:{name} -->", f"<!-- /AUTO:{name} -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    new = f"{start}\n{body}\n{end}"
    if not pattern.search(text):
        raise SystemExit(f"block {start} missing: add the start and end markers first")
    return pattern.sub(lambda _m: new, text)


def synced(text: str, today: str) -> str:
    return re.sub(r"(<!-- AUTO:synced -->).*?(<!-- /AUTO:synced -->)",
                  lambda m: f"{m.group(1)}Last synced with the code: {today}.{m.group(2)}", text, flags=re.S)


def build() -> dict[Path, str]:
    table, gaps = workings_block()
    today = datetime.now(IST).strftime("%Y-%m-%d")
    out = {}
    for rel, blocks in (("docs/CONTEXT.md", {"workings": table, "gaps": gaps_block(gaps)}),
                        ("AGENTS.md", {"gaps": gaps_block(gaps)})):
        p = ROOT / rel
        old = p.read_text(encoding="utf-8")
        new = old
        for name, body in blocks.items():
            new = replace_block(new, name, body)
        if new != old:
            new = synced(new, today)
        out[p] = new
    claude = ROOT / "CLAUDE.md"
    text = claude.read_text(encoding="utf-8") if claude.is_file() else ""
    if "@AGENTS.md" not in text:
        text = "# Claude Code\n\n@AGENTS.md\n\n" + text
    out[claude] = text
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--check", action="store_true", help="exit 1 when a file would change; write nothing")
    p.add_argument("--quiet", action="store_true", help="print only what changed")
    args = p.parse_args(argv)
    changed = []
    for path, new in build().items():
        old = path.read_text(encoding="utf-8") if path.is_file() else None
        if new != old:
            changed.append(path.relative_to(ROOT).as_posix())
            if not args.check:
                path.write_text(new, encoding="utf-8", newline="\n")
    if changed:
        print(("would change: " if args.check else "updated: ") + ", ".join(changed))
    elif not args.quiet:
        print("docs in step with the code")
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
