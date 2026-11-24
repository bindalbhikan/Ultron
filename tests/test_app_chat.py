"""App chat reuses the agent without Telegram owner actions or shared memory writes."""
from types import SimpleNamespace

import httpx
import pytest

from ultron.agents import chat
from ultron.core import config, http


def test_read_only_tools_exclude_action_and_memory_modules(monkeypatch):
    seen = []
    monkeypatch.setattr(config, "load_tools", lambda names: seen.extend(names) or [])
    chat.tools(read_only=True)
    assert set(seen) == {"runs", "omsguru", "business", "knowledge"}


def test_app_reply_is_private_and_reports_safe_failures(monkeypatch):
    monkeypatch.setattr(config, "get", lambda: SimpleNamespace(worker=lambda: ("https://worker.test", "test-token")))
    monkeypatch.setattr(http, "get", lambda *a, **k: httpx.Response(200, json={"question": "hello", "userId": "one"}, request=httpx.Request("GET", "https://worker.test")))
    calls = []
    def answer(question, conversation, **kw):
        calls.append((question, conversation, kw))
        raise RuntimeError("private upstream detail")
    monkeypatch.setattr(chat, "answer", answer)
    def put(method, url, **kw):
        assert method == "PUT" and kw["json"]["status"] == "failed"
        assert "private upstream" not in kw["json"]["answer"]
        return httpx.Response(200, request=httpx.Request(method, url))
    monkeypatch.setattr(http, "request", put)
    assert chat.app_reply("00000000-0000-4000-8000-000000000001") == 1
    assert calls == [("hello", "app:one", {"read_only": True})]


def test_app_reply_rejects_invalid_request_before_network():
    with pytest.raises(ValueError, match="invalid app chat"):
        chat.app_reply("../other-user")
