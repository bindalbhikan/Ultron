"""One way to try a call again (docs/libraries/04-tenacity.md), on tenacity.

    retry_call(fn, tries=7, wait=backoff(3, 60), on=(requests.RequestException,), log=log, what="GET ...")

* tries: an int, or a function of the last error giving the tries allowed for that kind of error
  (e.g. a server error 7, a refusal 3).
* wait: seconds before try n+1 as a function of n (1-based); backoff(first, cap) doubles up to cap.
* on: the errors worth another try; any other error goes straight up, untried.
* sleep: injectable (tests; callers whose own module's time.sleep a test patches).
Every failed try is logged as a warning "<what> failed: <error> (attempt n)"; after the last one the error
itself is raised.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from tenacity import RetryCallState, Retrying, retry_if_exception_type

T = TypeVar("T")


def backoff(first: float, cap: float) -> Callable[[int], float]:
    """first, 2 x first, 4 x first ... seconds, at most cap."""
    return lambda n: min(cap, first * 2 ** (n - 1))


def retry_call(fn: Callable[[], T], *, tries: int | Callable[[BaseException], int],
               wait: Callable[[int], float], on: tuple[type[BaseException], ...],
               log: logging.Logger | None = None, what: str = "call",
               sleep: Callable[[float], None] | None = None) -> T:
    attempt = 0

    def once() -> T:
        nonlocal attempt
        attempt += 1
        try:
            return fn()
        except on as exc:
            if log:
                log.warning("%s failed: %s (attempt %d)", what, exc, attempt)
            raise

    def stop(state: RetryCallState) -> bool:
        exc = state.outcome.exception() if state.outcome else None
        limit = tries(exc) if callable(tries) and exc is not None else tries
        return state.attempt_number >= int(limit)  # type: ignore[arg-type]

    return Retrying(stop=stop, wait=lambda state: wait(state.attempt_number),
                    retry=retry_if_exception_type(on), sleep=sleep or (lambda s: time.sleep(s)),
                    reraise=True)(once)
