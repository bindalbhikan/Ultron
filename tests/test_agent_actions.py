"""The agent's actions: what may run at once (auto) is the same in agent.toml and the worker's AGENT_ACTIONS,
and only report bots are auto."""
import tomllib
from pathlib import Path

from ultron.agents import chat
from ultron.core import config

ROOT = Path(__file__).resolve().parents[1]
CHANGES_OUTSIDE = {"ajiotat", "ajiospf", "myntraspf", "invpush", "labels", "smscatchup", "myntraotp",
                   "myntrareports", "myntrazerotd"}


def test_agent_toml_and_the_worker_list_the_same_actions_and_auto():
    agent = tomllib.loads((ROOT / "agent.toml").read_text(encoding="utf-8"))["actions"]
    worker = tomllib.loads((ROOT / "worker" / "wrangler.toml").read_text(encoding="utf-8"))["vars"]["AGENT_ACTIONS"]
    assert set(agent) == set(worker)
    for name, a in agent.items():
        assert a["workflow"] == worker[name]["workflow"] and a["inputs"] == worker[name]["inputs"], name
        assert a.get("auto", False) == worker[name].get("auto", False), name


def test_nothing_that_changes_something_outside_runs_without_approval():
    agent = tomllib.loads((ROOT / "agent.toml").read_text(encoding="utf-8"))["actions"]
    assert not [n for n in CHANGES_OUTSIDE if agent[n].get("auto")]


def test_run_now_refuses_an_action_that_needs_approval(monkeypatch):
    cfg = config.get()
    assert "propose_action" in chat.run_now(next(n for n in CHANGES_OUTSIDE if n in cfg.actions), "x")
    assert chat.run_now("nope", "x").startswith("Error: unknown action")
