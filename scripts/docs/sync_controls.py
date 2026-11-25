"""Generate the shared Worker action registry from agent.toml and workflow input declarations."""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def build() -> dict:
    actions = tomllib.loads((ROOT / "agent.toml").read_text(encoding="utf-8"))["actions"]
    for name, action in actions.items():
        workflow = yaml.load((ROOT / ".github/workflows" / action["workflow"]).read_text(encoding="utf-8"),
                             Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        trigger = workflow.get("on", workflow.get(True, {})) or {}
        definition = trigger.get("workflow_dispatch") or {}
        declared = definition.get("inputs", {}) or {}
        unknown = set(action.get("inputs", [])) - set(declared)
        if unknown:
            raise ValueError(f"{name}: undeclared workflow inputs {sorted(unknown)}")
        action["chat"] = "chat_id" in declared
        action["fields"] = {key: {"description": str(declared[key].get("description", key)),
                                   "default": str(declared[key].get("default", "")),
                                   "type": declared[key].get("type", "string"),
                                   **({"options": declared[key]["options"]} if "options" in declared[key] else {})}
                            for key in action.get("inputs", [])}
    return actions


def main() -> int:
    target = ROOT / "worker/actions.json"
    content = json.dumps(build(), indent=2, ensure_ascii=False) + chr(10)
    if "--check" in sys.argv:
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            print("Run python scripts/docs/sync_controls.py; shared action registry is stale.")
            return 1
    else:
        target.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
