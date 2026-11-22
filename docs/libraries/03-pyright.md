# 3. pyright — type check

**Status**: ✅ 16 Nov 2026 for the seller-neutral core (`src/ultron` without `workings/`); `workings/` next,
folder by folder.

**Why**: finds wrong types before a run (a `str` id where an `int` is compared, `None` not handled, a
renamed function argument); the fastest and most complete Python type checker.

**What was done**
* `pyproject.toml` `[tool.pyright]`: `basic` mode, `include = src/ultron`, `exclude = src/ultron/workings`.
* First run: 35 errors in 31 files, now 0. One was a real crash: `omsguru_orders._row` read the channel id with
  `re.search(...).group(1)`, so a channel link in another shape stopped the whole read with `AttributeError`.
  Now `channel_id()` stops it with a clear error naming the link (never a line under no channel: the numbers
  would be wrong) — `tests/test_omsguru_rows.py`.
* The rest changed no behaviour: BeautifulSoup attribute values passed through `str()` (always one string
  there), `Sequence` for tuple defaults (`llm.py`), a generic `Memory.change`, `names.get(ch) or ch`, a guard on
  an impossible `None` in `fetch_orders`, and two pyright-ignore comments where the stubs are wrong
  (`stream.reconfigure`, one sheet of `ExcelFile.parse`).
* CI: `lint.yml` job `pyright` (pyright 1.1.414, on the bots' setup) on every push and pull request.

**Use**: `.venv\Scripts\python -m pyright` (pyright is put in `.venv` by `scripts/local/setup_pc.ps1`).

**Next**: `workings/` folder by folder — add each to `include` once it is clean.
