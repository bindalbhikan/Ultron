"""The agent's actions: what may run at once (auto) is the same in agent.toml and the worker's AGENT_ACTIONS,
and only report bots are auto."""
import json
import tomllib
from pathlib import Path
import shutil
import subprocess

import pytest

from ultron.agents import chat
from ultron.core import config

ROOT = Path(__file__).resolve().parents[1]
CHANGES_OUTSIDE = {"ajiotat", "ajiospf", "myntraspf", "invpush", "labels", "smscatchup", "myntraotp",
                   "myntrareports", "myntrazerotd", "fkprice", "erpomsreturn", "ticketfollowup", "grouping", "mastersheet"}


def test_agent_toml_and_the_worker_list_the_same_actions_and_auto():
    agent = tomllib.loads((ROOT / "agent.toml").read_text(encoding="utf-8"))["actions"]
    worker = json.loads((ROOT / "worker" / "actions.json").read_text(encoding="utf-8"))
    assert "AGENT_ACTIONS" not in tomllib.loads((ROOT / "worker" / "wrangler.toml").read_text(encoding="utf-8")).get("vars", {})
    assert set(agent) == set(worker)
    for name, a in agent.items():
        assert a["workflow"] == worker[name]["workflow"] and a["inputs"] == worker[name]["inputs"], name
        assert a.get("auto", False) == worker[name].get("auto", False), name


def test_every_command_and_scheduled_input_uses_the_shared_catalog():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the Worker integration check")
    result = subprocess.run([node, "--input-type=module", "-e",
        'import {SCHEDULE,COMMANDS} from "./worker/src/worker.js"; console.log(JSON.stringify({schedule:SCHEDULE,commands:COMMANDS}));'],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True)
    exported = json.loads(result.stdout)
    actions = json.loads((ROOT / "worker/actions.json").read_text(encoding="utf-8"))
    by_file = {action["workflow"]: action for action in actions.values()}
    for name, command in exported["commands"].items():
        assert command["workflow"] in by_file, name
    for slot in exported["schedule"]:
        command = exported["commands"][slot["cmd"]]
        allowed = by_file[command["workflow"]]["inputs"]
        assert not set(slot.get("inputs", {})) - set(allowed), slot


def test_nothing_that_changes_something_outside_runs_without_approval():
    agent = tomllib.loads((ROOT / "agent.toml").read_text(encoding="utf-8"))["actions"]
    assert not [n for n in CHANGES_OUTSIDE if agent[n].get("auto")]


def test_run_now_refuses_an_action_that_needs_approval(monkeypatch):
    cfg = config.get()
    assert "propose_action" in chat.run_now(next(n for n in CHANGES_OUTSIDE if n in cfg.actions), "x")
    assert chat.run_now("nope", "x").startswith("Error: unknown action")
