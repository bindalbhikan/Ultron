"""Which model the agent talks to: the providers it has a key for, the best model of each, in order.

Every provider is reached through one client, the OpenAI SDK (chat completions: messages, tools,
tool_calls), each at its own OpenAI-compatible address:

    anthropic   https://api.anthropic.com/v1/                         ANTHROPIC_API_KEY
    openai      https://api.openai.com/v1                             OPENAI_API_KEY
    google      https://generativelanguage.googleapis.com/v1beta/openai/   GEMINI_API_KEY (or GOOGLE_API_KEY), Google AI Studio
    nvidia      https://integrate.api.nvidia.com/v1                   NVIDIA_API_KEY
    groq        https://api.groq.com/openai/v1                        GROQ_API_KEY (free plan: about 30 requests a
                minute, 1,000 a day, 8,000 tokens a minute; a bigger request goes to the next provider)
    cloudflare  <worker>/api (Workers AI on the account's free daily allocation)   the worker's url / token

`[model]` in agent.toml (or the control panel, docs/agent/models.md):
    name   "auto": pick for itself; or one model, "provider:model" ("anthropic:claude-sonnet-5-5"),
           tried first, the others after it when it fails. AGENT_MODEL overrides it.
    tier   "smart" (the best model of the family) or "fast" (the cheap, quick one)
    order  the providers in the order they are tried; only those with a key count.

Auto-select: each provider's model list (GET /models, kept a day in <output>/agent/models.json) is
matched against its families for the tier, best family first, and of a family the newest version
(the numbers in the id) wins; previews, dated snapshots, embeddings, audio and image models never.
When a provider does not answer its list, the first family's known model is used.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .config import env

TIERS = ("smart", "fast")
SKIP = re.compile(r"preview|exp|embed|tts|audio|image|vision|realtime|transcribe|search|guard|reward|"
                  r"moderation|coder|-\d{8}$|\d{4}-\d{2}-\d{2}", re.I)
LIST_HOURS = 24


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    base_url: str              # "" for cloudflare: the worker's address
    key_envs: tuple[str, ...]
    families: dict[str, tuple[str, ...]]   # tier -> regexes over the model id, best first
    known: dict[str, str]                  # tier -> the model used when the list cannot be read

    def key(self) -> str:
        return next((env(k) for k in self.key_envs if env(k)), "")


PROVIDERS: dict[str, Provider] = {p.name: p for p in (
    Provider("anthropic", "Anthropic", "https://api.anthropic.com/v1/", ("ANTHROPIC_API_KEY",),
             {"smart": (r"^claude-opus-\d+(-\d+)?$", r"^claude-sonnet-\d+(-\d+)?$"),
              "fast": (r"^claude-haiku-\d+(-\d+)?$", r"^claude-sonnet-\d+(-\d+)?$")},
             {"smart": "claude-opus-5-5", "fast": "claude-haiku-5-5"}),
    Provider("openai", "OpenAI", "https://api.openai.com/v1", ("OPENAI_API_KEY",),
             {"smart": (r"^gpt-\d+(\.\d+)?$",), "fast": (r"^gpt-\d+(\.\d+)?-mini$",)},
             {"smart": "gpt-5", "fast": "gpt-5-mini"}),
    Provider("google", "Google AI Studio", "https://generativelanguage.googleapis.com/v1beta/openai/",
             ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
             # Google keeps listing a pro it has retired (gemini-2.5-pro: 404 "no longer available", 23 Nov 2026)
             # and has no newer non-preview pro, so its "-latest" alias (the current pro) comes first
             {"smart": (r"^(models/)?gemini-pro-latest$", r"^(models/)?gemini-\d+(\.\d+)?-pro$"),
              "fast": (r"^(models/)?gemini-\d+(\.\d+)?-flash$",)},
             {"smart": "gemini-pro-latest", "fast": "gemini-2.5-flash"}),
    Provider("nvidia", "NVIDIA", "https://integrate.api.nvidia.com/v1", ("NVIDIA_API_KEY",),
             {"smart": (r"^openai/gpt-oss-120b$", r"^nvidia/.*nemotron.*(ultra|super).*$"),
              "fast": (r"^openai/gpt-oss-20b$", r"^nvidia/.*nemotron.*nano.*$")},
             {"smart": "openai/gpt-oss-120b", "fast": "openai/gpt-oss-20b"}),
    Provider("groq", "Groq", "https://api.groq.com/openai/v1", ("GROQ_API_KEY",),
             {"smart": (r"^openai/gpt-oss-120b$",), "fast": (r"^openai/gpt-oss-20b$",)},
             {"smart": "openai/gpt-oss-120b", "fast": "openai/gpt-oss-20b"}),
    Provider("cloudflare", "Cloudflare Workers AI", "", (),
             {"smart": (r"^@cf/openai/gpt-oss-120b$", r"^@cf/nvidia/nemotron"),
              "fast": (r"^@cf/openai/gpt-oss-20b$",)},
             {"smart": "@cf/openai/gpt-oss-120b", "fast": "@cf/openai/gpt-oss-20b"}),
)}
DEFAULT_ORDER = ("anthropic", "openai", "google", "nvidia", "groq", "cloudflare")


@dataclass(frozen=True)
class Choice:
    provider: str
    model: str
    key: str = ""          # which of the provider's keys: "env" (its env var) or an app key's id; "" = any

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def parse(spec: str) -> Choice | None:
    """"provider:model", or a Workers AI id ("@cf/..."); None for "auto" / ""."""
    spec = spec.strip()
    if not spec or spec == "auto":
        return None
    if spec.startswith("@cf/"):
        return Choice("cloudflare", spec)
    provider, sep, model = spec.partition(":")
    if not sep or provider not in PROVIDERS or not model:
        raise ValueError(f"model {spec!r}: write provider:model ({', '.join(PROVIDERS)}) or auto")
    return Choice(provider, model)


def version(model_id: str) -> tuple[int, ...]:
    """The numbers in an id, for "newest": claude-opus-5-5 -> (5, 5), gemini-2.5-pro -> (2, 5)."""
    return tuple(int(n) for n in re.findall(r"\d+", model_id.rsplit("/", 1)[-1]))


def best(provider: Provider, tier: str, ids: list[str]) -> str:
    """The provider's best model of the tier among `ids` (its list); its known one when none matches."""
    usable = [i for i in ids if not SKIP.search(i.rsplit("/", 1)[-1])]
    for family in provider.families[tier]:
        found = [i for i in usable if re.search(family, i)]
        if found:
            # Google lists "models/gemini-..." but its chat endpoint wants the bare name (404 otherwise)
            return max(found, key=lambda i: (version(i), -len(i))).removeprefix("models/")
    return provider.known[tier]


class ModelLists:
    """The model ids of each provider, read once a day (GET /models through the SDK); `fresh` is told of a
    list just read (the agent passes it on for the app's model picker)."""

    def __init__(self, path: Path, fetch, fresh=None):
        self.path, self.fetch, self.fresh = path, fetch, fresh

    def _saved(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def ids(self, provider: str) -> list[str]:
        saved = self._saved()
        entry = saved.get(provider) or {}
        if entry.get("at", 0) > time.time() - LIST_HOURS * 3600 and entry.get("ids"):
            return entry["ids"]
        try:
            ids = sorted(self.fetch(provider))
        except Exception:  # noqa: BLE001 - a provider without a list still has its known model
            return entry.get("ids") or []
        saved[provider] = {"at": int(time.time()), "ids": ids}
        if self.fresh is not None:
            try:
                self.fresh(provider, ids)
            except Exception:  # noqa: BLE001 - the picker's list is a convenience
                pass
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(saved), encoding="utf-8")
        except OSError:
            pass
        return ids


def available(order: tuple[str, ...], keys: dict[str, list[str]], worker_ready: bool) -> list[str]:
    """The providers of `order` that can be used here: one with a key (cloudflare: the worker set up)."""
    out = []
    for name in order:
        if name not in PROVIDERS:
            raise ValueError(f"[model] order: unknown provider {name!r} ({', '.join(PROVIDERS)})")
        if (worker_ready if name == "cloudflare" else bool(keys.get(name))) and name not in out:
            out.append(name)
    return out


def candidates(pinned: Choice | None, order: tuple[str, ...], tier: str, worker_ready: bool,
               lists: ModelLists, keys: dict[str, list[str]]) -> list[Choice]:
    """The models to try, in order: the pinned model on each of its provider's keys, then the best model of
    every available provider, once per key (`keys`: provider -> key ids in the order they are tried)."""
    if tier not in TIERS:
        raise ValueError(f"[model] tier must be one of {', '.join(TIERS)}")

    def on_keys(provider: str, model: str) -> list[Choice]:
        if provider == "cloudflare":
            return [Choice(provider, model, "worker")]
        return [Choice(provider, model, k) for k in keys.get(provider, [])]

    out = on_keys(pinned.provider, pinned.model) if pinned else []
    for name in available(order, keys, worker_ready):
        ids = lists.ids(name)
        models = [best(PROVIDERS[name], tier, ids)]
        if name == "cloudflare":
            models.extend(PROVIDERS[name].known.values())
        for model in models:
            for choice in on_keys(name, model):
                if choice not in out:
                    out.append(choice)
    return out
