"""core/models.py + core/llm.py: the model auto-selected per provider, tried in order, the next one on a failure."""
import json

import httpx
import openai
import pytest

from ultron.core import llm, models
from ultron.core.models import PROVIDERS, Choice, ModelLists, best, candidates, parse


def test_best_is_the_newest_of_the_best_family_without_previews_or_snapshots():
    ids = ["claude-opus-5", "claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-4-8", "claude-opus-4-5-20251101"]
    assert best(PROVIDERS["anthropic"], "smart", ids) == "claude-opus-5-5"
    assert best(PROVIDERS["anthropic"], "fast", ids + ["claude-haiku-5-5", "claude-haiku-4-5"]) == "claude-haiku-5-5"
    g = ["models/gemini-2.5-pro", "models/gemini-3.1-pro", "models/gemini-3.5-pro-preview", "models/gemini-3.1-flash"]
    assert best(PROVIDERS["google"], "smart", g) == "models/gemini-3.1-pro"
    assert best(PROVIDERS["openai"], "smart", ["gpt-5", "gpt-5.1", "gpt-5.1-mini", "gpt-5-2025-08-07"]) == "gpt-5.1"
    assert best(PROVIDERS["groq"], "smart", []) == "openai/gpt-oss-120b"        # no list: the known model


def test_parse():
    assert parse("auto") is None and parse("") is None
    assert parse("@cf/openai/gpt-oss-20b") == Choice("cloudflare", "@cf/openai/gpt-oss-20b")
    assert parse("anthropic:claude-sonnet-5-5") == Choice("anthropic", "claude-sonnet-5-5")
    with pytest.raises(ValueError):
        parse("claude-sonnet-5-5")


def test_only_providers_with_a_key_in_order_pinned_first(monkeypatch, tmp_path):
    for p in PROVIDERS.values():
        for k in p.key_envs:
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    told = []
    lists = ModelLists(tmp_path / "m.json", lambda p: {"anthropic": ["claude-opus-5-5"], "groq": ["openai/gpt-oss-120b"]}[p],
                       fresh=lambda p, ids: told.append(p))
    keys = {"anthropic": ["env"], "groq": ["env", "k2"]}
    got = candidates(Choice("groq", "x"), ("anthropic", "google", "groq", "cloudflare"), "smart", False, lists, keys)
    assert got == [Choice("groq", "x", "env"), Choice("groq", "x", "k2"), Choice("anthropic", "claude-opus-5-5", "env"),
                   Choice("groq", "openai/gpt-oss-120b", "env"), Choice("groq", "openai/gpt-oss-120b", "k2")]
    assert told == ["anthropic", "groq"]          # each fresh list is passed on (the app's model picker)
    assert json.loads((tmp_path / "m.json").read_text())["anthropic"]["ids"] == ["claude-opus-5-5"]


def test_a_list_that_fails_keeps_the_last_one_read(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"nvidia": {"at": 0, "ids": ["openai/gpt-oss-120b"]}}))
    def down(_):
        raise RuntimeError("down")
    assert ModelLists(path, down).ids("nvidia") == ["openai/gpt-oss-120b"]


class FakeClient:
    def __init__(self, answer):
        self.answer, self.calls = answer, []
        self.chat = self
        self.completions = self

    def create(self, **body):
        self.calls.append(body)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self

    def model_dump(self):
        return {"choices": [{"message": {"content": self.answer}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}


def _status(code):
    req = httpx.Request("POST", "https://x/v1/chat/completions")
    return openai.APIStatusError("no", response=httpx.Response(code, request=req), body=None)


def test_the_next_model_answers_when_one_fails_and_a_refusing_provider_rests(monkeypatch):
    order = [Choice("anthropic", "claude-opus-5-5", "env"), Choice("google", "gemini-3.1-pro", "env"),
             Choice("groq", "openai/gpt-oss-120b", "env")]
    fakes = {"anthropic": FakeClient(_status(429)), "google": FakeClient(_status(500)), "groq": FakeClient("hi")}
    monkeypatch.setattr(llm, "choices", lambda tier="": list(order))
    monkeypatch.setattr(llm, "client", lambda p, k="": fakes[p])
    monkeypatch.setattr(llm, "_resting", {})
    monkeypatch.setattr(llm, "worker_send", lambda *a: None)
    data = llm.chat([{"role": "user", "content": "x"}])
    assert data["model"] == "groq:openai/gpt-oss-120b" and data["choices"][0]["message"]["content"] == "hi"
    assert set(llm._resting) == {"env"}                  # 429: that key rests; a 500 does not
    assert fakes["anthropic"].calls[0]["model"] == "claude-opus-5-5"


def test_every_model_failing_is_an_llm_error_naming_each(monkeypatch):
    monkeypatch.setattr(llm, "choices", lambda tier="": [Choice("openai", "gpt-5.1", "env")])
    monkeypatch.setattr(llm, "client", lambda p, k="": FakeClient(_status(401)))
    monkeypatch.setattr(llm, "_resting", {})
    monkeypatch.setattr(llm, "worker_send", lambda *a: None)
    with pytest.raises(llm.LLMError, match=r"openai:gpt-5.1 \(HTTP 401"):
        llm.chat([{"role": "user", "content": "x"}])


def test_cost_known_and_unknown(monkeypatch):
    assert llm.cost({"model": "anthropic:claude-sonnet-5-5", "input": 1_000_000, "output": 100_000}) == 3.0
    assert llm.cost({"model": "groq:openai/gpt-oss-120b", "input": 10, "output": 10}) is None


def test_every_provider_has_both_tiers():
    for p in models.PROVIDERS.values():
        assert set(p.families) == set(models.TIERS) == set(p.known)


def test_env_beats_the_control_panel_which_beats_agent_toml(monkeypatch):
    for k in ("AGENT_MODEL", "AGENT_MODEL_TIER", "AGENT_MODEL_ORDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "panel", lambda: {"model": "groq:openai/gpt-oss-120b", "order": ["groq"]})
    spec, tier, order = llm.settings()
    assert spec == "groq:openai/gpt-oss-120b" and order == ("groq",) and tier == "smart"
    monkeypatch.setenv("AGENT_MODEL", "anthropic:claude-haiku-5-5")
    monkeypatch.setenv("AGENT_MODEL_ORDER", "google, nvidia")
    assert llm.settings()[0] == "anthropic:claude-haiku-5-5" and llm.settings()[2] == ("google", "nvidia")
    monkeypatch.setattr(llm, "panel", lambda: {})
    monkeypatch.delenv("AGENT_MODEL")
    assert llm.settings()[0] == "auto"


def test_a_key_at_its_limit_hands_over_to_the_next_key_of_the_same_provider(monkeypatch):
    """Owner, 23 Nov 2026: several keys per provider; when one runs out the next is used at once."""
    order = [Choice("groq", "openai/gpt-oss-120b", "k1"), Choice("groq", "openai/gpt-oss-120b", "k2"),
             Choice("anthropic", "claude-opus-5-5", "env")]
    fakes = {"k1": FakeClient(_status(429)), "k2": FakeClient("from key two"), "env": FakeClient("never")}
    reports = []
    monkeypatch.setattr(llm, "choices", lambda tier="": list(order))
    monkeypatch.setattr(llm, "client", lambda p, k="": fakes[k])
    monkeypatch.setattr(llm, "_resting", {})
    monkeypatch.setattr(llm, "worker_send", lambda method, path, body: reports.append((path, body["id"], body["status"])))
    data = llm.chat([{"role": "user", "content": "x"}])
    assert data["choices"][0]["message"]["content"] == "from key two" and fakes["env"].calls == []
    assert reports == [("/api/keys/report", "k1", "limit")]         # the app shows k1 resting
    assert llm._resting["k1"] > 0


def test_keys_env_first_then_the_apps_in_order(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-secret")
    monkeypatch.setattr(llm, "_resting", {})
    monkeypatch.setattr(llm, "app_keys", lambda: [
        {"id": "a1", "provider": "groq", "key": "app-1", "restingUntil": 0},
        {"id": "a2", "provider": "groq", "key": "app-2", "restingUntil": 9_999_999_999_999},
        {"id": "x", "provider": "unknown", "key": "z"}])
    got = llm.keys()
    assert got["groq"] == [("env", "env-secret"), ("a1", "app-1"), ("a2", "app-2")] and "unknown" not in got
    assert llm._resting["a2"] > 1e9                                   # resting as the app last said
