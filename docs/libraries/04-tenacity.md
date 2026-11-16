# 4. tenacity — one retry helper

**Status**: ⏳

**Why**: retries are written by hand in many places, each a bit different (OMSGuru `get()` 7 tries,
Myntra `schedule()` one cooldown wait, the SPF master's 3 tries, Telegram re-send, zero TD phone retries,
ERP `report()` 4 tries). Most failures of 9-16 Nov 2026 were retries too short. tenacity is the standard:
backoff, stop after N tries or M minutes, retry only on chosen errors, a log line per try.

**Plan**
1. `ultron/core/retry.py`: `retry_transient(tries, max_minutes, on=(...))` on tenacity, with the log format
   of the bots.
2. Move the hand-written loops one by one (OMSGuru, Myntra portal, Telegram, Drive, ERP, AJIO, Flipkart),
   each keeping its tries and waits exactly; the tests of `tests/test_retries.py` stay green.
