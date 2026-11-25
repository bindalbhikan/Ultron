"""Built-in tools "files": attach a file to the agent's reply, in whichever chat asked (Telegram or the app).

A file is named by its source:

    run:<run id>/<path>     a file a bot's run wrote (its output/ folder, as run_files lists it)
    adhoc:<id>/<file>       a result of a dynamic working (run_adhoc)

Sending a file to the chat that asked changes nothing outside, so it needs no approval. A GitHub artifact link is
never an answer: the artifacts are encrypted, so the owner could not open them.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..core import attachments
from ..core.llm import tool
from ..core.paths import output_root

ADHOC_ID = re.compile(r"[0-9a-f]{12}")


def adhoc_root() -> Path:
    return output_root() / "agent" / "adhoc"


def _inside(root: Path, rel: str) -> Path:
    rel = rel.strip().lstrip("/")
    path = (root / rel).resolve()
    if not rel or not path.is_relative_to(root.resolve()):
        raise ValueError(f"{rel!r} is not a file of that source")
    if not path.is_file():
        raise ValueError(f"no file {rel!r} there")
    return path


def resolve(source: str) -> Path:
    """The local path of a file source (see the module text); ValueError when it is not one."""
    kind, _, rest = source.strip().partition(":")
    head, _, rel = rest.partition("/")
    if kind == "run" and head.isdigit():
        from ..integrations import github
        root = github.output(int(head))
        if root is None:
            raise ValueError(f"run {head} kept no output")
        return _inside(root, rel)
    if kind == "adhoc" and ADHOC_ID.fullmatch(head):
        return _inside(adhoc_root() / head / "out", rel)
    raise ValueError(f"unknown source {source!r}: use run:<run id>/<path> or adhoc:<id>/<file>")


def for_app() -> bool:
    from . import controls
    return (controls.actor.get() or {}).get("source") == "job"


@tool
def send_file(source: str, caption: str = "") -> str:
    """Attach a file to your reply: the owner gets it in this same chat (a picture shows inline). Use it whenever
    the owner asks for an image, sheet or file a run made (find it with recent_runs and run_files) or one a dynamic
    working made (run_adhoc). Never answer with a GitHub artifact link instead: those are encrypted.

    Args:
        source: run:<run id>/<path as run_files lists it>, e.g. run:45631872650/vms/NOV-26.png; or adhoc:<id>/<file>.
        caption: one short line shown with the file.
    """
    try:
        path = resolve(source)
    except (ValueError, RuntimeError) as exc:
        return f"Error: {exc}"
    if source.startswith("adhoc:"):
        caption = ("Ad-hoc result, not a checked report. " + caption).strip()
    return attachments.attach(path, caption[:200], app=for_app())


TOOLS = [send_file]
