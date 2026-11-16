# 1. ruff — lint gate for bugs

**Status**: ✅ 16 Nov 2026.

**Why**: one tool (Rust, a whole repo in well under a second) in place of flake8 / pyflakes / isort / pyupgrade;
it finds bugs before a run does: undefined names, unused variables, mutable defaults, `except` without `from`.

**What was done**
* `pyproject.toml` `[tool.ruff]`: rules `F` (pyflakes), `E9` (syntax), `B` (bugbear); `B905` (zip strict) and
  `B023` (loop variable in a closure, 25 places) are not gated yet: each is looked at by hand first.
  Style rules are left off on purpose: a mass reformat of every file is not worth the risk to the numbers.
* Fixed (no output changes): 8 unused imports, an f-string without fields, `getattr` with a constant,
  `raise ... from None` (AJIO TAT master open in Excel), two unused loop variables, an unused xlsxwriter
  format renamed `_num0` (kept: it is registered in the workbook's styles), pandas named for the type
  checker where it was only in string annotations (`omsguru.py`, `portal_monthly`).
* Checked: every `ultron` module still imports; no removed import was used by another module; 63 tests pass.
* CI: `.github/workflows/lint.yml` runs `ruff check` on every push and pull request.

**Use**: `python -m ruff check src tests run.py` (add `--fix` for the safe fixes).

**Next on this page**: review the 25 `B023` places; then turn on `UP` (pyupgrade) and `SIM` file by file.
