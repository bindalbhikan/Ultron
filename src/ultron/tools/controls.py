"""The shared, permission-checked agent controls used by app and Telegram chat."""
from __future__ import annotations

import contextvars
import json

from ..core import config, http, llm

actor: contextvars.ContextVar[dict | None] = contextvars.ContextVar("control_actor", default=None)


def _call(operation: str, args: dict | None = None, *, preview: bool = False) -> str:
    context = actor.get()
    if not context:
        return "Controls are unavailable without a verified conversation."
    url, token = config.get().worker()
    if not url or not token:
        return "The operations service is not configured."
    response = http.post(f"{url}/api/control", json={
        "actor": context, "operation": operation, "args": args or {}, "preview": preview,
    }, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    data = http.json_of(response)
    return json.dumps(data, ensure_ascii=False)


@llm.tool
def agent_controls() -> str:
    """Read the shared catalog of controls and allowed workflow inputs for this conversation's permissions."""
    return _call("catalog")


@llm.tool
def agent_control(operation: str, arguments: str = "{}", preview: bool = False) -> str:
    """Use a shared agent control. Changes wait for approval; permitted automatic reports may start at once.

    Args:
        operation: a control name from agent_controls, such as workflow.run, workflow.cancel, model.get or schedule.set.
        arguments: a JSON object with exactly the fields listed in the control catalog.
        preview: validate and show the plan without starting a run or changing anything.
    """
    try:
        args = json.loads(arguments)
    except ValueError:
        return "Arguments must be a JSON object."
    if not isinstance(args, dict):
        return "Arguments must be a JSON object."
    return _call(operation, args, preview=preview)


TOOLS = [agent_controls, agent_control]
