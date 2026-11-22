"""The agent's model: chat completions (messages, tools, tool_calls) through the OpenAI SDK, at
whichever provider has a key: Anthropic, OpenAI, Google AI Studio, NVIDIA, Groq, or the seller's
Cloudflare worker (Workers AI, free daily allocation). core/models.py picks the model; when one
fails (no credit, rate limit, down, a request it refuses) the next one is tried, and every
fallback is logged.

`tool` turns a typed function with an "Args:" docstring into a tool; `agent_loop` runs the
model and the tools until it answers.
"""
from __future__ import annotations

import inspect
import json
import logging
import re
import threading
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Callable, get_type_hints

from . import config, models
from .config import env

if TYPE_CHECKING:
    from openai import OpenAI

log = logging.getLogger("ultron")

JSON_TYPES = {int: "integer", str: "string", float: "number", bool: "boolean"}


class LLMError(RuntimeError):
    """The model could not be reached: free allocation used up, model down, worker not set up."""


def tool(fn: Callable) -> Callable:
    """Attach a function-calling schema built from the signature and the "Args:" docstring."""
    doc = inspect.getdoc(fn) or ""
    summary, _, args_doc = doc.partition("Args:")
    descr = dict(re.findall(r"^\s*(\w+):\s*(.+(?:\n\s{8,}.+)*)", args_doc, re.M))
    props, required, hints = {}, [], get_type_hints(fn)
    for name, p in inspect.signature(fn).parameters.items():
        props[name] = {"type": JSON_TYPES.get(hints.get(name), "string"),
                       "description": " ".join((descr.get(name) or name).split())}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    fn.schema = {"type": "function", "function": {
        "name": fn.__name__, "description": " ".join(summary.split()),
        "parameters": {"type": "object", "properties": props, "required": required}}}
    return fn


_clients: dict[str, "OpenAI"] = {}
_resting: dict[str, float] = {}         # key id -> until when it is left out (its limit, or a refusal)
_lock = threading.Lock()
LIMIT_REST = 3600                       # a key at its limit rests an hour unless the provider says how long
_keys_cache: dict = {"at": 0.0, "keys": []}


def worker_get(path: str):
    """GET <worker><path> with the worker token; None when the worker is not set up or does not answer."""
    from . import http
    url, token = config.get().worker()
    if not url or not token:
        return None
    try:
        r = http.get(f"{url}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        r.raise_for_status()
        return http.json_of(r)
    except Exception as exc:  # noqa: BLE001 - the app's keys and settings are optional
        log.info("worker %s not read (%s)", path, type(exc).__name__)
        return None


def worker_send(method: str, path: str, body: dict) -> None:
    """A report to the worker (a key's state, the model lists); never fails the caller."""
    from . import http
    url, token = config.get().worker()
    if not url or not token:
        return
    try:
        http.request(method, f"{url}{path}", headers={"Authorization": f"Bearer {token}"}, json=body, timeout=10)
    except Exception as exc:  # noqa: BLE001
        log.info("worker %s not told (%s)", path, type(exc).__name__)


def app_keys() -> list[dict]:
    """The API keys added in the app (the worker's GET /api/keys: id, provider, key, restingUntil), read every
    5 minutes; kept as last read when the worker does not answer."""
    if time.time() - _keys_cache["at"] > 300:
        got = worker_get("/api/keys")
        if isinstance(got, dict) and isinstance(got.get("keys"), list):
            _keys_cache["keys"] = got["keys"]
        _keys_cache["at"] = time.time()
    return _keys_cache["keys"]


def keys() -> dict[str, list[tuple[str, str]]]:
    """provider -> [(key id, secret)] in the order they are tried: the env var's key first, then the app's."""
    out: dict[str, list[tuple[str, str]]] = {}
    for name, p in models.PROVIDERS.items():
        if name != "cloudflare" and p.key():
            out.setdefault(name, []).append(("env", p.key()))
    now_ms = time.time() * 1000
    for k in app_keys():
        if k.get("provider") in models.PROVIDERS and k.get("key"):
            if float(k.get("restingUntil") or 0) > now_ms:
                _resting[k["id"]] = max(_resting.get(k["id"], 0), float(k["restingUntil"]) / 1000)
            out.setdefault(k["provider"], []).append((k["id"], k["key"]))
    return out


def client(provider: str, key_id: str = "") -> "OpenAI":
    """The OpenAI SDK client of a provider at its OpenAI-compatible address, with one of its keys."""
    from openai import OpenAI
    with _lock:
        name = f"{provider}|{key_id}"
        if name not in _clients:
            p = models.PROVIDERS[provider]
            if provider == "cloudflare":
                url, token = config.get().worker()
                base, secret = f"{url}/api", token
            else:
                found = dict(keys().get(provider, []))
                secret = found.get(key_id) or next(iter(found.values()), "")
                base = p.base_url
            _clients[name] = OpenAI(api_key=secret, base_url=base, timeout=180, max_retries=1)
        return _clients[name]


def _list_ids(provider: str) -> list[str]:
    """A provider's model list, through its first key that is not resting."""
    usable = [k for k, _ in keys().get(provider, []) if _resting.get(k, 0) <= time.time()] or [""]
    return [m.id for m in client(provider, usable[0]).models.list()]


def _rest(choice: models.Choice, status: str, error: str, until: float) -> None:
    """Leave a key out until `until`, and tell the app (a key added there) why."""
    _resting[choice.key] = until
    if choice.key not in ("", "env", "worker"):
        worker_send("POST", "/api/keys/report", {"id": choice.key, "status": status, "error": error[:200],
                                                 "until": int(until * 1000)})


_panel: dict = {"at": 0.0, "values": {}}


def panel() -> dict:
    """What the app's control panel saved (the worker's GET /api/settings: model, tier, order), read
    every 5 minutes; {} when the worker is not set up or does not answer (agent.toml then counts)."""
    if time.time() - _panel["at"] > 300:
        got = worker_get("/api/settings")
        if got is not None:
            _panel["values"] = got if isinstance(got, dict) else {}
        _panel["at"] = time.time()
    return _panel["values"]


def settings() -> tuple[str, str, tuple[str, ...]]:
    """(model, tier, order): AGENT_MODEL / AGENT_MODEL_TIER / AGENT_MODEL_ORDER, else what the control
    panel saved, else [model] in agent.toml."""
    cfg, saved = config.get(), panel()
    order = (tuple(o.strip() for o in env("AGENT_MODEL_ORDER").split(",") if o.strip())
             or tuple(saved.get("order") or ()) or cfg.model_order)
    return (env("AGENT_MODEL", str(saved.get("model") or cfg.model)),
            env("AGENT_MODEL_TIER", str(saved.get("tier") or cfg.model_tier)), order)


def choices(tier: str = "") -> list[models.Choice]:
    """The models to try now, best first: each provider once per key; a key resting after its limit or a
    refusal goes last (still tried when nothing else is left)."""
    cfg = config.get()
    spec, default_tier, order = settings()
    url, token = cfg.worker()
    lists = models.ModelLists(cfg.output / "agent" / "models.json", _list_ids,
                              fresh=lambda provider, ids: worker_send("PUT", "/api/models", {provider: ids}))
    key_ids = {provider: [k for k, _ in found] for provider, found in keys().items()}
    found = models.candidates(models.parse(spec), order, tier or default_tier, bool(url and token), lists, key_ids)
    now = time.time()
    return sorted(found, key=lambda c: _resting.get(c.key, 0) > now)


def chat(messages: list[dict], tools: Sequence[Callable] = (), model: str = "", max_tokens: int = 4000,
         tier: str = "") -> dict:
    """One chat-completions answer (a dict in the OpenAI shape, with "model" = "provider:model").
    `model` ("provider:model") is tried first; then the auto-selected ones."""
    import openai
    tried = choices(tier)
    if model:
        first = models.parse(model)
        if first:
            own = [c for c in tried if c.provider == first.provider]
            pinned = [models.Choice(first.provider, first.model, c.key) for c in own] or [first]
            tried = [*pinned, *[c for c in tried if c not in pinned]]
    if not tried:
        cfg = config.get()
        raise LLMError("no model: set a key (ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, NVIDIA_API_KEY, GROQ_API_KEY) "
                       f"or the worker ({cfg.worker_url_env} / {cfg.worker_token_env})")
    failed = []
    for choice in tried:
        body = {"model": choice.model, "messages": messages, "max_tokens": max_tokens}
        if tools:
            body["tools"] = [t.schema for t in tools]
        try:
            data = client(choice.provider, choice.key).chat.completions.create(**body).model_dump()
        except openai.APIStatusError as exc:
            why = f"HTTP {exc.status_code} {str(exc.message)[:200]}"
            if exc.status_code in (402, 429):          # this key's limit: the next key of the provider goes on
                wait = exc.response.headers.get("retry-after", "") if exc.response is not None else ""
                until = time.time() + (float(wait) if wait.replace(".", "", 1).isdigit() else LIMIT_REST)
                _rest(choice, "limit", why, until)
            elif exc.status_code in (401, 403):        # the key refused: left out until it is fixed in the app
                _rest(choice, "bad", why, time.time() + 24 * 3600)
        except openai.APIError as exc:          # not reached, timed out, an answer that is no JSON
            why = f"{type(exc).__name__}: {str(exc)[:200]}"
        else:
            if data.get("choices"):
                if failed:
                    log.warning("model: %s answered after %s", choice, "; ".join(failed))
                data["model"] = str(choice)
                return data
            why = f"no answer: {str(data)[:200]}"
        failed.append(f"{choice} ({why})")
    raise LLMError("every model failed: " + "; ".join(failed))


def _run_tool(fns: dict[str, Callable], call: dict) -> str:
    fn = fns.get(call["function"]["name"])
    if fn is None:
        return f"Error: no tool {call['function']['name']!r}"
    try:
        args = call["function"].get("arguments") or "{}"
        args = json.loads(args) if isinstance(args, str) else args
        if isinstance(args, str):                 # some models send the JSON twice encoded
            args = json.loads(args)
        return str(fn(**args))
    except Exception as exc:  # noqa: BLE001 - the model reads the error and can try again
        return f"Error: {type(exc).__name__}: {str(exc)[:300]}"


def agent_loop(system: str, task: str, tools: list[Callable], max_steps: int = 8,
               model: str = "", history: Sequence[dict] = ()) -> tuple[str, dict]:
    """(final answer text, usage) after letting the model call the tools up to max_steps times.
    `history`: earlier user / assistant messages of the conversation, oldest first."""
    fns = {t.__name__: t for t in tools}
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": task}]
    usage = {"input": 0, "output": 0, "steps": 0, "model": model}
    for step in range(max_steps + 1):
        last = step == max_steps
        if last:   # out of steps: answer now from what was read
            messages.append({"role": "user", "content": "No more tool calls: give your answer now."})
        data = chat(messages, [] if last else tools, model)
        usage["steps"] += 1
        usage["model"] = data["model"]
        u = data.get("usage") or {}
        usage["input"] += u.get("prompt_tokens") or 0
        usage["output"] += u.get("completion_tokens") or 0
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return (msg.get("content") or "").strip(), usage
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            log.info("agent tool %s %s", call["function"]["name"], str(call["function"].get("arguments"))[:200])
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": _run_tool(fns, call)})
    return "", usage


def cost(usage: dict) -> float | None:
    """What the call costs in US$ at the model's list price ([model.prices] in agent.toml); None
    when the price is not known. On the Workers AI free allocation it is within the day's free amount."""
    name = str(usage.get("model") or "").partition(":")[2] or str(usage.get("model") or "")
    price = config.get().prices.get(name)
    if not price:
        return None
    return round((usage["input"] * price[0] + usage["output"] * price[1]) / 1e6, 4)


def cost_text(usage: dict) -> str:
    """The cost for a log line: "$0.0123 at list price", or "price unknown"."""
    c = cost(usage)
    return "price unknown" if c is None else f"${c} at list price"
