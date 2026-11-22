"""The agent's memory: what it keeps between messages and runs.

  notes    long-term: the owner's preferences, facts about the business, known harmless errors,
           decisions, and incidents the watcher saw. Each note: id, kind, text, tags, when, uses.
  chats    short-term: the last messages of each Telegram chat, so a follow-up ("and yesterday?")
           is understood.

Recall: every message gets the owner's preferences plus the notes that best match it (word overlap
weighted by rarity, tag matches, recent use), within a size budget, in front of the model; the model
can also search (recall), add (remember) and drop (forget) notes with tools (tools/memory.py).

Where it is kept ([memory] backend in agent.toml):
  worker   the seller's Cloudflare worker: a D1 database (tables agent_note and agent_turn, routes
           /api/memory/notes and /api/memory/chats/<chat>), one row per note and per message, shared
           by GitHub Actions runs, every host, a fallback phone and the app's control panel. The old
           KV document is moved in once, by the worker.
  file     <output>/agent/memory.json on this machine (ultron serve with no worker)
  auto     the worker when it is set up, else the file;  off: no memory
Never in git (a seller's repo may be public). Text that looks like a password, OTP, token, key or
a customer's phone number or email is refused, so it never reaches the memory at all.

Notes are the agent's own earlier notes: data that informs it, never instructions that outrank the
owner's current message.
"""
from __future__ import annotations

import json
import logging
import math
import re
import secrets
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Protocol

from . import config, http

log = logging.getLogger("ultron")

KINDS = ("preference", "fact", "known_issue", "decision", "incident")
SCHEMA = 1
STOP = set("""a an the and or of to in on at for from by with is are was were be been it its this that
these those as not no do does did have has had i you we they he she me my our your their what which who
how when where why can could would should will shall may might than then there here about into over
hai hain ka ki ke ko se me mein aur ya bhi nahi kya""".split())
SECRET = [
    # a secret word followed by a value with a digit in it ("OTP is 482913", "password: hunter22"),
    # not the word alone ("the Myntra OTP bot retries at 11")
    (re.compile(r"\b(pass(word)?|passwd|pwd|otp|pin|api[ _-]?key|secret|token|cookie)s?\b(\s+(is|was|are))?"
                r"\s*[:=]?\s*(?=\S*\d)\S{4,}", re.I), "a password, OTP, key or token"),
    (re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"), "a long key or token"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "an email address"),
    (re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)"), "a phone number"),
]
# which notes go first when there are too many (worker/agent.js trims D1 in the same order)
TRIM_ORDER = {"incident": 0, "fact": 1, "decision": 1, "known_issue": 2, "preference": 3}


def unsafe(text: str) -> str:
    """Why the text must not be stored ("" = fine)."""
    for rx, what in SECRET:
        if rx.search(text):
            return what
    return ""


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 and w not in STOP]


def empty() -> dict:
    return {"schema": SCHEMA, "notes": [], "chats": {}}


def trim(notes: list[dict], max_notes: int) -> list[dict]:
    """The notes kept when there are too many: incidents go first (oldest), then the least used,
    least recent; preferences last."""
    if len(notes) <= max_notes:
        return notes
    order = sorted(notes, key=lambda n: (TRIM_ORDER.get(n["kind"], 1), n.get("uses", 0), n.get("updated", 0)))
    drop = {n["id"] for n in order[: len(notes) - max_notes]}
    return [n for n in notes if n["id"] not in drop]


# ------------------------------------------------------------------ stores
class Store(Protocol):
    def notes(self) -> list[dict]: ...
    def save_note(self, note: dict, max_notes: int) -> None: ...
    def drop_note(self, note_id: str) -> bool: ...
    def turns(self, chat: str) -> list[dict]: ...
    def add_turn(self, chat: str, turn: dict, keep: int) -> None: ...
    def clear_chat(self, chat: str) -> None: ...


class FileStore:
    """One JSON file on this machine, replaced atomically on every write (any OS)."""

    def __init__(self, path: Path):
        self.path, self.lock = path, threading.Lock()

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError:
            return empty()
        except ValueError:
            log.warning("Memory file %s is damaged; starting a new one", self.path)
            return empty()
        data.setdefault("notes", [])
        data.setdefault("chats", {})
        return data

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def notes(self) -> list[dict]:
        return self._read()["notes"]

    def save_note(self, note: dict, max_notes: int) -> None:
        with self.lock:
            data = self._read()
            data["notes"] = [n for n in data["notes"] if n["id"] != note["id"]] + [note]
            data["notes"] = trim(sorted(data["notes"], key=lambda n: n.get("created", 0)), max_notes)
            self._write(data)

    def drop_note(self, note_id: str) -> bool:
        with self.lock:
            data = self._read()
            before = len(data["notes"])
            data["notes"] = [n for n in data["notes"] if n["id"] != note_id]
            self._write(data)
            return len(data["notes"]) < before

    def turns(self, chat: str) -> list[dict]:
        return self._read()["chats"].get(chat, [])

    def add_turn(self, chat: str, turn: dict, keep: int) -> None:
        with self.lock:
            data = self._read()
            turns = data["chats"].setdefault(chat, [])
            turns.append(turn)
            del turns[: max(0, len(turns) - keep)]
            self._write(data)

    def clear_chat(self, chat: str) -> None:
        with self.lock:
            data = self._read()
            data["chats"].pop(chat, None)
            self._write(data)


class WorkerStore:
    """The worker's D1 database (worker/agent.js /api/memory/...): one row per note and per message,
    so two runs writing at once never overwrite each other."""

    def __init__(self, url: str, token: str):
        self.url, self.headers = f"{url}/api/memory", {"Authorization": f"Bearer {token}"}

    def _call(self, method: str, path: str, **kw) -> dict:
        r = http.request(method, f"{self.url}{path}", headers=self.headers, timeout=30, **kw)
        r.raise_for_status()
        return http.json_of(r) if r.content else {}

    def notes(self) -> list[dict]:
        return self._call("GET", "/notes").get("notes", [])

    def save_note(self, note: dict, max_notes: int) -> None:
        self._call("PUT", f"/notes/{note['id']}", json={**note, "max": max_notes})

    def drop_note(self, note_id: str) -> bool:
        return bool(self._call("DELETE", f"/notes/{note_id}").get("deleted"))

    def turns(self, chat: str) -> list[dict]:
        return self._call("GET", f"/chats/{chat}").get("turns", [])

    def add_turn(self, chat: str, turn: dict, keep: int) -> None:
        self._call("POST", f"/chats/{chat}", json={**turn, "keep": keep})

    def clear_chat(self, chat: str) -> None:
        self._call("DELETE", f"/chats/{chat}")


class NoStore:
    """[memory] backend = "off": keeps nothing."""

    def notes(self) -> list[dict]:
        return []

    def save_note(self, note: dict, max_notes: int) -> None:
        pass

    def drop_note(self, note_id: str) -> bool:
        return False

    def turns(self, chat: str) -> list[dict]:
        return []

    def add_turn(self, chat: str, turn: dict, keep: int) -> None:
        pass

    def clear_chat(self, chat: str) -> None:
        pass


# ------------------------------------------------------------------ memory
class Memory:
    def __init__(self, store: Store, settings: config.MemorySettings):
        self.store, self.s = store, settings

    def notes(self) -> list[dict]:
        return self.store.notes()

    # ---- long-term notes
    def remember(self, text: str, kind: str = "fact", tags: list[str] | tuple = (), source: str = "") -> dict:
        text = " ".join(str(text).split())[: self.s.note_chars]
        if not text:
            raise ValueError("empty note")
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        why = unsafe(text)
        if why:
            raise ValueError(f"not stored: it looks like {why}, which the memory never keeps")
        tags = sorted({t.strip().lower() for t in tags if t and t.strip()})
        now = int(time.time())
        mine, note = set(words(text)), None
        for n in self.notes():
            theirs = set(words(n["text"]))
            if n["kind"] == kind and mine and theirs and len(mine & theirs) / len(mine | theirs) >= 0.75:
                # the same thing again: refresh, do not repeat
                note = {**n, "text": text, "updated": now, "uses": n.get("uses", 0) + 1,
                        "tags": sorted(set(n.get("tags", [])) | set(tags))}
                break
        if note is None:
            note = {"id": secrets.token_hex(3), "kind": kind, "text": text, "tags": tags, "created": now,
                    "updated": now, "uses": 0, "source": source}
        self.store.save_note(note, self.s.max_notes)
        return dict(note)

    def forget(self, note_id: str) -> bool:
        return self.store.drop_note(note_id.strip())

    def search(self, query: str, k: int = 0, tags: list[str] | tuple = (), kinds: tuple = (),
               notes: list[dict] | None = None) -> list[dict]:
        """The notes that best match the query (and tags), best first."""
        notes = [n for n in (self.notes() if notes is None else notes) if not kinds or n["kind"] in kinds]
        if not notes:
            return []
        q, want = Counter(words(query)), {t.lower() for t in tags}
        df = Counter(w for n in notes for w in set(words(n["text"] + " " + " ".join(n.get("tags", [])))))
        now, scored = time.time(), []
        for n in notes:
            nw = set(words(n["text"] + " " + " ".join(n.get("tags", []))))
            score = sum(math.log(1 + len(notes) / df[w]) for w in q if w in nw)
            score += 3 * len(want & set(n.get("tags", [])))
            if score <= 0:
                continue
            age_days = (now - n.get("updated", now)) / 86400
            score *= 1 + 0.1 * min(n.get("uses", 0), 10)
            score /= 1 + age_days / 90                 # old notes fade, slowly
            scored.append((score, n))
        scored.sort(key=lambda x: -x[0])
        return [n for _, n in scored[: (k or self.s.recall)]]

    def context(self, query: str, tags: list[str] | tuple = (), kinds: tuple = (), budget: int = 3000) -> str:
        """The notes block for the system prompt: preferences always, then the best matches."""
        notes = self.notes()
        prefs = [] if kinds else [n for n in notes if n["kind"] == "preference"][-15:]
        found = [n for n in self.search(query, tags=tags, kinds=kinds, notes=notes) if n not in prefs]
        lines, size = [], 0
        for n in prefs + found:
            line = f"- [{n['id']}] ({n['kind']}{', ' + ', '.join(n['tags']) if n.get('tags') else ''}; " \
                   f"{time.strftime('%d %b %Y', time.localtime(n.get('updated', 0)))}) {n['text']}"
            if size + len(line) > budget:
                break
            lines.append(line)
            size += len(line)
        return "\n".join(lines)

    # ---- incidents (the watcher)
    def incident(self, workflow_file: str, summary: str) -> dict | None:
        """Note what went wrong in a bot run; the same problem again only counts up."""
        text = f"{workflow_file}: {' '.join(summary.split())}"[: self.s.note_chars]
        if unsafe(text):
            text = f"{workflow_file}: alert sent (details withheld: they looked like personal data or a secret)"
        try:
            return self.remember(text, "incident", [workflow_file], source="watch")
        except ValueError:
            return None

    # ---- short-term: the conversation of each chat
    def history(self, chat: str) -> list[dict]:
        if not chat:
            return []
        cutoff = time.time() - self.s.history_days * 86400
        out = []
        for t in self.store.turns(str(chat))[-self.s.history_turns:]:
            if t.get("at", 0) >= cutoff:
                out += [{"role": "user", "content": t["q"]}, {"role": "assistant", "content": t["a"]}]
        return out

    def add_turn(self, chat: str, question: str, answer: str) -> None:
        if not chat or self.s.history_turns <= 0:
            return
        q, a = question[:1500], answer[:2500]
        if unsafe(q):
            q = "(a message with a password, key, phone number or email: not kept)"
        self.store.add_turn(str(chat), {"at": int(time.time()), "q": q, "a": a}, self.s.history_turns)

    def clear_chat(self, chat: str) -> None:
        self.store.clear_chat(str(chat))


_memory: Memory | None = None
_lock = threading.Lock()


def get() -> Memory:
    global _memory
    with _lock:
        if _memory is None:
            cfg = config.get()
            backend, (url, token) = cfg.memory.backend, cfg.worker()
            if backend == "auto":
                backend = "worker" if url and token else "file"
            if backend == "off":
                _memory = Memory(NoStore(), cfg.memory)
            elif backend == "worker":
                if not url or not token:
                    raise RuntimeError(f"[memory] backend = worker, but {cfg.worker_url_env} / {cfg.worker_token_env} are not set")
                _memory = Memory(WorkerStore(url, token), cfg.memory)
            else:
                _memory = Memory(FileStore(cfg.output / "agent" / "memory.json"), cfg.memory)
            log.info("Memory: %s", backend)
        return _memory


def reset() -> None:
    """Forget the chosen store (tests, or after the config changed)."""
    global _memory
    with _lock:
        _memory = None
