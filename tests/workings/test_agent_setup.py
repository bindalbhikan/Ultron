"""Bindal's setup of Ultron: agent.toml, the worker's AGENT_ACTIONS and the workflows agree, and
Ultron's own core (everything but ultron.workings) names no seller."""
import tomllib
from pathlib import Path

from ultron.core import config

ROOT = Path(__file__).resolve().parents[2]


def setup():
    config.get.cache_clear()
    return config.parse(ROOT / "agent.toml")


def test_agent_toml():
    cfg = setup()
    assert cfg.company and cfg.repo == "bindalbhikan/Ultron" and cfg.actions and "omsguru" in cfg.chat_tools
    assert {t.__name__ for t in config.load_tools(cfg.chat_tools)} >= {"find_order", "run_log"}


def test_worker_actions_match_agent_toml():
    worker = tomllib.loads((ROOT / "worker" / "wrangler.toml").read_text(encoding="utf-8"))["vars"]["AGENT_ACTIONS"]
    mine = {k: {"workflow": a.workflow, "inputs": list(a.inputs)} for k, a in setup().actions.items()}
    assert worker == mine


def test_action_workflows_exist():
    missing = [a.workflow for a in setup().actions.values() if not (ROOT / ".github" / "workflows" / a.workflow).is_file()]
    assert not missing


def test_action_inputs_exist_in_their_workflows():
    """An approved action sends only inputs its workflow declares (GitHub refuses any other)."""
    bad = []
    for name, a in setup().actions.items():
        text = (ROOT / ".github" / "workflows" / a.workflow).read_text(encoding="utf-8")
        bad += [f"{name}.{i}" for i in a.inputs if f"\n      {i}:" not in text]
    assert not bad


def test_ultron_core_names_no_seller():
    package = ROOT / "src" / "ultron"
    seller = setup().company.split()[0].lower()
    hits = [str(p.relative_to(package)) for p in package.rglob("*.py")
            if "workings" not in p.relative_to(package).parts and seller in p.read_text(encoding="utf-8").lower()]
    assert not hits, f"{seller!r} named in {hits}"
