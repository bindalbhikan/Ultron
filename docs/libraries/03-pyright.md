# 3. pyright — type check

**Status**: 🔧 in progress — config written (`pyproject.toml` `[tool.pyright]`), first run and fixes to do.

**Why**: finds wrong types before a run (a `str` id where an `int` is compared, `None` not handled, a
renamed function argument); the fastest and most complete Python type checker.

**Plan**
1. `[tool.pyright]`: `basic` mode on the seller-neutral core (`src/ultron` without `workings/`) first. ✅ written
2. Run it (`npx pyright` or `pip install pyright`), fix what it finds with no behaviour change, tests green.
3. A CI step next to ruff in `lint.yml` once the core is clean; then `workings/` folder by folder.
