"""Every `from ultron... import name` in the source resolves, the lazy ones inside functions too.

A name removed from a module (23 Nov 2026: `tables.to_polars`, gone with pandas) broke the portal sale report only
when it ran, because the import sat inside a function; this test finds such an import before a run does."""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def _imports():
    for f in sorted((SRC / "ultron").rglob("*.py")):
        parts = list(f.relative_to(SRC).with_suffix("").parts)
        package = parts[:-1]        # a module's package; an __init__'s own package is its folder too
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level:
                base = package[:len(package) - node.level + 1]
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            if target.split(".")[0] == "ultron":
                yield f, node.lineno, target, [a.name for a in node.names]


def test_every_ultron_import_resolves():
    missing = []
    for f, line, target, names in _imports():
        try:
            module = importlib.import_module(target)
        except ModuleNotFoundError as e:
            if (e.name or "").split(".")[0] == "ultron":
                missing.append(f"{f.name}:{line} no module {target}")
            continue        # a third-party extra not installed here: not this test's concern
        for name in names:
            if name == "*" or hasattr(module, name):
                continue
            try:
                importlib.import_module(f"{target}.{name}")
            except ModuleNotFoundError:
                missing.append(f"{f.relative_to(SRC)}:{line} {target} has no {name!r}")
    assert not missing, "\n".join(missing)
