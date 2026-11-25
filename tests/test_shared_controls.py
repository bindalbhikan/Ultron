"""Shared controls keep conversation identity outside model arguments."""
import json
from types import SimpleNamespace

import httpx

from ultron.agents import chat
from ultron.core import config, http
from ultron.tools import controls


def test_control_actor_is_taken_from_context_and_preview_is_forwarded(monkeypatch):
    monkeypatch.setattr(config, "get", lambda: SimpleNamespace(worker=lambda: ("https://worker.test", "test-token")))
    seen = []
    def post(url, **kw):
        seen.append(kw["json"])
        return httpx.Response(200, json={"preview": True})
    monkeypatch.setattr(http, "post", post)
    token = controls.actor.set({"source": "job", "jobId": "claimed-job"})
    try:
        result = json.loads(controls.agent_control("workflow.run", '{"action":"inventory"}', preview=True))
    finally:
        controls.actor.reset(token)
    assert result["preview"] is True
    assert seen == [{"actor": {"source": "job", "jobId": "claimed-job"}, "operation": "workflow.run",
                     "args": {"action": "inventory"}, "preview": True}]
    assert "confirmed" not in seen[0]


def test_app_tools_add_shared_controls_without_telegram_owner_tools(monkeypatch):
    names = []
    monkeypatch.setattr(config, "load_tools", lambda values: names.extend(values) or [])
    token = controls.actor.set({"source": "job", "jobId": "claimed-job"})
    try:
        chat.tools(read_only=True)
    finally:
        controls.actor.reset(token)
    assert set(names) == {"runs", "omsguru", "business", "knowledge", "controls"}


def test_control_without_identity_does_not_contact_the_service(monkeypatch):
    monkeypatch.setattr(http, "post", lambda *args, **kw: (_ for _ in ()).throw(AssertionError("network")))
    token = controls.actor.set(None)
    try:
        assert "verified conversation" in controls.agent_controls()
    finally:
        controls.actor.reset(token)
