#!/usr/bin/env python
"""Learn a portal's API from browser captures:  python scripts/knowledge/learn_netcap.py [FILE ...]

Reads netcap captures (the owner's "network-dom-capture" JSON exports, default: every
netcap/*.json; one file may hold several captures one after another) and writes, per portal
host, a catalogue of the API calls seen into docs/knowledge/api/<host>.md: method, path (ids as
{id}), query parameter names, request body field names, response field names (a few levels deep),
HTTP status, the portal page it was called from, how often, and whether the code already uses it.

Only NAMES are kept, never values: no cookies, tokens, headers, signatures, ids, customer data or
amounts reach the catalogue (the repo is public). Analytics, sockets, static files and signed blob
links are left out. The raw captures stay in netcap/ (git-ignored, local only).

The agent reads the catalogue with its knowledge tools (ultron.tools.knowledge); people read it on
GitHub. Run it again after a new capture; a section written by hand below the generated block of a
catalogue file is kept.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "knowledge" / "api"
SKIP = re.compile(r"socket\.io|google|gstatic|doubleclick|facebook|clarity|hotjar|sentry|newrelic|"
                  r"nr-data|analytics|beacon|/collect|telemetry|mixpanel|segment|delighted|"
                  r"blob\.core\.windows\.net|amazonaws\.com|\.(js|css|png|jpe?g|gif|svg|woff2?|ico|map)(\?|$)",
                  re.I)
ID = re.compile(r"/(\d{3,}|[0-9a-f]{8,}(?:-[0-9a-f]{4,})*|[A-Za-z0-9_]*\d[A-Za-z0-9_]{9,})(?=/|$)")
START, END = "<!-- AUTO:catalogue -->", "<!-- /AUTO:catalogue -->"


def captures(path: Path):
    """Every capture document in a file (several JSON objects may follow one another)."""
    text, i, dec = path.read_text(encoding="utf-8"), 0, json.JSONDecoder()
    while True:
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            return
        doc, i = dec.raw_decode(text, i)
        yield doc


def parsed(body):
    """The body as an object: captures wrap it as {type, value}; value may be JSON text or a form."""
    if isinstance(body, dict) and "value" in body and "type" in body:
        body = body["value"]
    if isinstance(body, str):
        t = body.strip()
        if not t:
            return None
        try:
            return json.loads(t)
        except ValueError:
            if re.match(r"^[\w\[\].%-]+=", t):
                return {k: "" for k, _ in parse_qsl(t, keep_blank_values=True)}
            return None
    return body


def shape(obj, depth: int = 0, limit: int = 4) -> str:
    """Field names only: {a, b: {c}, d: [{e}]}; never a value."""
    if isinstance(obj, dict):
        if depth >= limit:
            return "{…}"
        parts = []
        for k, v in list(obj.items())[:40]:
            k = "{id}" if ID.fullmatch("/" + str(k)) else str(k)
            sub = shape(v, depth + 1, limit) if isinstance(v, (dict, list)) else ""
            parts.append(f"{k}: {sub}" if sub else k)
        return "{" + ", ".join(dict.fromkeys(parts)) + "}"
    if isinstance(obj, list):
        first = next((x for x in obj if isinstance(x, (dict, list))), None)
        return f"[{shape(first, depth + 1, limit)}]" if first is not None else "[…]"
    return ""


def used_in_code(path: str) -> str:
    """The code files that already name this path (its last two fixed parts)."""
    fixed = [p for p in path.split("/") if p and p != "{id}"][-2:]
    if not fixed:
        return ""
    needle = "/".join(fixed)
    try:
        out = subprocess.run(["git", "grep", "-l", "-F", needle, "--", "src", "scripts"], cwd=ROOT,
                             capture_output=True, text=True, timeout=30).stdout.split()
    except Exception:  # noqa: BLE001 - no git: the column stays empty
        return ""
    return ", ".join(f"`{Path(p).name}`" for p in out if not p.startswith("scripts/knowledge"))


def learn(files: list[Path]) -> dict[str, dict]:
    """host -> {(method, path): entry}"""
    hosts: dict[str, dict] = defaultdict(dict)
    for f in files:
        for doc in captures(f):
            for r in doc.get("requests", []):
                if r.get("type") not in ("xhr", "fetch", "form-submit"):
                    continue
                url = r.get("url") or ""
                if not url.startswith("http") or SKIP.search(url):
                    continue
                sp = urlsplit(url)
                path = ID.sub("/{id}", sp.path) or "/"
                key = (r.get("method") or "GET", path)
                e = hosts[sp.netloc.split(":")[0]].setdefault(key, {
                    "n": 0, "query": set(), "req": "", "res": "", "status": set(), "pages": set(),
                    "files": set()})
                e["n"] += 1
                e["query"] |= {k for k, _ in parse_qsl(sp.query, keep_blank_values=True)}
                req, res = r.get("request") or {}, r.get("response") or {}
                e["req"] = e["req"] or shape(parsed(req.get("body")))
                e["res"] = e["res"] or shape(parsed(res.get("body")))
                if res.get("status"):
                    e["status"].add(str(res["status"]))
                page = ID.sub("/{id}", urlsplit(r.get("pageUrl") or "").path)
                if page:
                    e["pages"].add(page)
                e["files"].add(f.name)
    return hosts


def catalogue(host: str, calls: dict) -> str:
    lines = [f"Generated {date.today():%d %b %Y} by `scripts/knowledge/learn_netcap.py` from "
             f"{', '.join(sorted({n for e in calls.values() for n in e['files']}))}. Names only, no values.", ""]
    for (method, path), e in sorted(calls.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        used = used_in_code(path)
        lines.append(f"### `{method} {path}`")
        lines.append("")
        lines.append(f"- seen {e['n']}x, status {', '.join(sorted(e['status'])) or '?'}, from page "
                     f"{', '.join(f'`{p}`' for p in sorted(e['pages'])[:3]) or '?'}")
        if e["query"]:
            lines.append(f"- query: {', '.join(f'`{q}`' for q in sorted(e['query']))}")
        if e["req"]:
            lines.append(f"- body: `{e['req'][:600]}`")
        if e["res"]:
            lines.append(f"- answer: `{e['res'][:800]}`")
        lines.append(f"- in the code: {used or 'not used yet'}")
        lines.append("")
    return "\n".join(lines).rstrip()


def write(host: str, body: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{host}.md"
    block = f"{START}\n{body}\n{END}"
    if path.is_file():
        old = path.read_text(encoding="utf-8")
        if START in old and END in old:
            new = old[:old.index(START)] + block + old[old.index(END) + len(END):]
        else:
            new = old.rstrip() + "\n\n" + block + "\n"
    else:
        new = (f"# API calls seen on `{host}`\n\nWhat each call is for, and what is safe to do with it, is in\n"
               f"the portal's page in `docs/knowledge/`. Calls that change something (POST / PUT that\n"
               f"save, approve, raise or push) are never made by the agent without the owner's approval.\n\n"
               f"{block}\n\n## Notes (by hand)\n\n- \n")
    path.write_text(new, encoding="utf-8", newline="\n")
    return path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("files", nargs="*", type=Path, help="capture files (default: netcap/*.json)")
    args = p.parse_args(argv)
    files = args.files or sorted((ROOT / "netcap").glob("*.json"))
    if not files:
        print("no captures: put the netcap exports in netcap/")
        return 1
    for host, calls in sorted(learn(files).items()):
        path = write(host, catalogue(host, calls))
        print(f"{host}: {len(calls)} calls -> {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
