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

* Moved too, each with a test run on the old code first and then the new (same tries, waits, errors):
  * Telegram `_post` (bots): 3 tries on a dropped connection / timeout, waits 5, 10 s, a file rewound each
    time, another request error not tried again — `tests/test_telegram_post.py`.
  * Myntra portal `schedule()`: one wait of the cooldown (16 min) only for a cooldown refusal, none for a
    logged-out session or another error, none with `cooldown_wait=0` — `tests/test_myntra_schedule.py`.
  * ERP `report()`: asked again (4 tries, waits 5, 10, 15 s) only while rows and count disagree; an HTTP error
    or an answer without data stops at once — `tests/test_erp_report.py`.

  * Drive `_with_retries` (every read through `RetrySession`, the safe uploads): 3 tries, waits 10, 30 s, on a
    5xx / 429 / rate limit or a dropped connection; the last answer returned, a last dropped connection
    `DriveError` — `tests/test_drive_retries.py`.
  * AJIO `_req`: 3 tries, waits 3, 6 s, on a 5xx or a request error; the last 5xx answer returned —
    `tests/test_ajio_req.py`.
  * Flipkart `login()` (3 tries on a dropped connection, waits 20, 40 s; a refused login once) and `_post()`
    (3 tries on a 5xx or a dropped connection, waits 5, 10 s) — `tests/test_flipkart_retries.py`.

  * The agent's Telegram (`integrations/telegram.py`) had **no retry at all**: it now is the one sender of the
    agent and the bots (the bots' `_post` calls it), with the bots' rule — `tests/test_telegram_post.py`.

**To do, one by one (each keeping its tries and waits exactly)**: the SPF master's report queue, zero TD's phone retries, the AWB tracker's http
client, the phone's collect loop.
