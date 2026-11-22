"""core/memory.py: notes remembered once, trimmed in order, recalled by relevance; chats kept short."""
import time

import pytest

from ultron.core import config, memory


def _mem(tmp_path, **kw):
    return memory.Memory(memory.FileStore(tmp_path / "m.json"), config.MemorySettings(**kw))


def test_the_same_note_again_is_refreshed_not_repeated(tmp_path):
    m = _mem(tmp_path)
    a = m.remember("Owner wants the Myntra sale report at 9 AM", "preference", ["myntra"])
    b = m.remember("owner wants the myntra sale report at 9 am", "preference", ["sale"])
    notes = m.notes()
    assert len(notes) == 1 and a["id"] == b["id"] and notes[0]["uses"] == 1 and notes[0]["tags"] == ["myntra", "sale"]


def test_secrets_and_customer_data_are_refused(tmp_path):
    m = _mem(tmp_path)
    for text in ("the OTP is 482913", "call 9876543210", "mail a@b.com"):
        with pytest.raises(ValueError):
            m.remember(text)
    assert m.notes() == []


def test_trim_drops_incidents_first_and_keeps_preferences(tmp_path):
    m = _mem(tmp_path, max_notes=2)
    m.remember("Owner prefers Hinglish answers", "preference")
    m.remember("vms.yml failed on a login page", "incident")
    m.remember("Ajio pays on Wednesdays", "fact")
    assert sorted(n["kind"] for n in m.notes()) == ["fact", "preference"]


def test_search_finds_the_matching_note(tmp_path):
    m = _mem(tmp_path)
    m.remember("Flipkart returns arrive within four months", "fact", ["flipkart"])
    m.remember("Myntra SPF tickets are never closed by the agent", "decision", ["myntra"])
    assert m.search("flipkart returns")[0]["text"].startswith("Flipkart")
    assert "Myntra SPF" in m.context("spf tickets")


def test_chat_history_keeps_the_last_turns_within_days(tmp_path):
    m = _mem(tmp_path, history_turns=2, history_days=1)
    for i in range(3):
        m.add_turn("42", f"q{i}", f"a{i}")
    assert [t["content"] for t in m.history("42")] == ["q1", "a1", "q2", "a2"]
    m.store.add_turn("42", {"at": int(time.time()) - 3 * 86400, "q": "old", "a": "old"}, 5)
    assert "old" not in [t["content"] for t in m.history("42")]
    m.clear_chat("42")
    assert m.history("42") == []


def test_forget(tmp_path):
    m = _mem(tmp_path)
    n = m.remember("A note to drop", "fact")
    assert m.forget(n["id"]) and not m.forget(n["id"]) and m.notes() == []


class FakeResponse:
    def __init__(self, body):
        self.body, self.content, self.status_code = body, b"x", 200

    def raise_for_status(self):
        pass


def test_worker_store_routes(monkeypatch):
    calls = []

    def request(method, url, headers=None, timeout=None, **kw):
        calls.append((method, url.split("/api/memory")[1], kw.get("json")))
        return FakeResponse({"notes": [], "turns": [], "deleted": True})
    monkeypatch.setattr(memory.http, "request", request)
    monkeypatch.setattr(memory.http, "json_of", lambda r: r.body)
    m = memory.Memory(memory.WorkerStore("https://w", "t"), config.MemorySettings(max_notes=7))
    note = m.remember("Ajio pays on Wednesdays", "fact")
    m.add_turn("-100", "q", "a")
    assert m.forget(note["id"])
    assert [c[:2] for c in calls] == [("GET", "/notes"), ("PUT", f"/notes/{note['id']}"), ("POST", "/chats/-100"),
                                      ("DELETE", f"/notes/{note['id']}")]
    assert calls[1][2]["max"] == 7 and calls[2][2]["keep"] == 10
