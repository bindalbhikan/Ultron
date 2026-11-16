# 4. tenacity — one retry helper

**Status**: 🔧 in progress — helper + first user (OMSGuru `get()`) in (16 Nov 2026, tenacity 9.2.1 in `uv.lock`);
the other loops follow one by one.

**Why**: retries are written by hand in many places, each a bit different (OMSGuru `get()` 7 tries,
Myntra `schedule()` one cooldown wait, the SPF master's 3 tries, Telegram re-send, zero TD phone retries,
ERP `report()` 4 tries). Most failures of 9-16 Nov 2026 were retries too short. tenacity is the standard:
backoff, stop after N tries, retry only on chosen errors. Pure Python, so the core still installs on Termux.

**Done**
* `src/ultron/core/retry.py`: `retry_call(fn, tries=, wait=, on=, log=, what=, sleep=)` and `backoff(first, cap)`
  on tenacity. `tries` can depend on the error (a server error 7, a refusal 3); each failed try is logged
  "<what> failed: <error> (attempt n)"; an error not in `on` is never tried again.
* `pyproject.toml`: `tenacity>=9.0` in the core dependencies.
* OMSGuru `get()` moved onto it with the same behaviour: 7 tries on 5xx / 429 / a dropped connection, 3 on any
  other status, waits 3, 6, 12, 24, 48, 60 s, "Session expired" raised at once. Tests: the same tries and waits
  as before (`tests/test_retries.py`), the helper's log and error.

**To do, one by one (each keeping its tries and waits exactly)**: Myntra portal `schedule()` / `_wait()`,
Telegram send, Drive `RetrySession`, ERP `report()`, AJIO and Flipkart clients, the SPF master's report queue,
zero TD's phone retries, the AWB tracker's http client.
