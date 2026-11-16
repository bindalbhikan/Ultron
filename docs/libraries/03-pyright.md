# 3. pyright — type check

**Status**: ⏳

**Why**: finds wrong types before a run (a `str` id where an `int` is compared, `None` not handled, a
renamed function argument); the fastest and most complete Python type checker.

**Plan**
1. `[tool.pyright]` in `pyproject.toml`, `basic` mode on `src/ultron` (core) first, then `workings/` folder by folder.
2. Fix what it finds, no behaviour change; CI step next to ruff once a folder is clean.
