"""Built-in tools "knowledge": the agent's lasting knowledge of the portals (docs/knowledge/ and
docs/PORTALS.md by default, [knowledge] paths in agent.toml): which API calls exist, what each is
for, what is read-only and what changes something. Read-only.

Knowledge is written by people and agents (and scripts/knowledge/learn_netcap.py from browser
captures); the private, changing notes (preferences, incidents) are the memory tools instead.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..core import config
from ..core.llm import tool

MAX_CHARS = 6000


def _files() -> list[Path]:
    cfg = config.get()
    out = []
    for rel in cfg.knowledge:
        p = cfg.root / rel
        if p.is_dir():
            out += sorted(p.rglob("*.md"))
        elif p.is_file():
            out.append(p)
    return out


def _name(p: Path) -> str:
    return p.relative_to(config.get().root).as_posix()


def _sections(p: Path) -> list[tuple[str, str]]:
    """(heading, text) of each section of a page (split at ## / ### headings)."""
    parts, head, buf = [], p.stem, []
    for line in p.read_text(encoding="utf-8").splitlines():
        if re.match(r"^#{2,3} ", line):
            if buf:
                parts.append((head, "\n".join(buf)))
            head, buf = line.lstrip("# ").strip(), [line]
        else:
            buf.append(line)
    if buf:
        parts.append((head, "\n".join(buf)))
    return parts


@tool
def knowledge_search(query: str) -> str:
    """Search the agent's knowledge of the portals (Myntra, AJIO, Flipkart, OMSGuru, ERP ...):
    API calls, what each is for, limits and lessons. Use it before saying something cannot be
    done, or to find which call gives some data (payments, notices, seller rating, prices).

    Args:
        query: words to look for, e.g. "myntra payment outstanding" or "announcements".
    """
    words = [w for w in re.findall(r"[\w-]+", query.lower()) if len(w) > 1]
    if not words:
        return "Error: give some words to look for"
    hits = []
    for p in _files():
        for head, text in _sections(p):
            low = text.lower()
            matched = sum(w in low for w in words)
            score = matched * 10 + sum(low.count(w) for w in words) + 3 * sum(w in head.lower() for w in words)
            if matched >= max(1, (len(words) + 1) // 2):
                hits.append((score, _name(p), head, text))
    if not hits:
        return f"Nothing in the knowledge about {query!r}. Pages: " + ", ".join(_name(p) for p in _files())
    hits.sort(key=lambda h: -h[0])
    out = [f"[{name} § {head}]\n{text.strip()}" for _, name, head, text in hits[:4]]
    text = "\n\n".join(out)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n... (cut; read the page for more)"


@tool
def knowledge_read(page: str, part: int = 1) -> str:
    """Read one knowledge page whole (in parts of about 6,000 characters).

    Args:
        page: the page's path or name as knowledge_search shows it, e.g. "docs/knowledge/myntra-partner.md" or "myntra-partner".
        part: which part, 1 = the start.
    """
    want = page.strip().lower().removesuffix(".md")
    found = next((p for p in _files() if _name(p).lower().removesuffix(".md") in (want, f"docs/knowledge/{want}")
                  or p.stem.lower() == want.rsplit("/", 1)[-1]), None)
    if not found:
        return f"No page {page!r}. Pages: " + ", ".join(_name(p) for p in _files())
    text = found.read_text(encoding="utf-8")
    chunks = [text[i:i + MAX_CHARS] for i in range(0, len(text), MAX_CHARS)] or [""]
    if not 1 <= part <= len(chunks):
        return f"{_name(found)} has {len(chunks)} part(s)"
    more = f"\n... (part {part} of {len(chunks)})" if len(chunks) > 1 else ""
    return chunks[part - 1] + more


TOOLS = [knowledge_search, knowledge_read]
