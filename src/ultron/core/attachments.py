"""Files the agent attaches to its reply, delivered with the answer by whoever sends it: Telegram (a photo or a
document in the same chat) or the private app chat (stored with the answer, downloaded in the app).

Tools call attach(); the sender calls take() once the reply text is ready. One reply carries at most MAX_FILES.
The box lives in a context variable, so two answers never share files.
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass
from pathlib import Path

MAX_FILES = 5
APP_MAX_BYTES = 1_400_000           # one app chat file (base64 in a D1 row, at most 2 MB)
TELEGRAM_MAX_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class Attachment:
    path: Path
    caption: str = ""


_box: contextvars.ContextVar[list[Attachment] | None] = contextvars.ContextVar("attachments", default=None)


def start() -> None:
    """A new, empty box for the reply being written."""
    _box.set([])


def limit(app: bool) -> int:
    return APP_MAX_BYTES if app else TELEGRAM_MAX_BYTES


def attach(path: Path, caption: str = "", app: bool = False) -> str:
    """Queue a file for the reply; the text the tool gives back to the model."""
    box = _box.get()
    if box is None:
        box = []
        _box.set(box)
    path = Path(path)
    if not path.is_file():
        return f"Error: {path.name} does not exist"
    if any(a.path == path for a in box):
        return f"{path.name} is already attached"
    if len(box) >= MAX_FILES:
        return f"Error: a reply carries at most {MAX_FILES} files"
    size = path.stat().st_size
    if size > limit(app):
        where = "the app" if app else "Telegram"
        return (f"Error: {path.name} is {size:,} bytes, over {where}'s limit of {limit(app):,}; "
                "send a smaller file (fewer rows, one sheet, a summary)")
    box.append(Attachment(path, caption))
    return f"Attached {path.name} ({size:,} bytes); it goes with your reply."


def take() -> list[Attachment]:
    """The files queued for this reply, emptying the box."""
    box = _box.get() or []
    _box.set([])
    return box
