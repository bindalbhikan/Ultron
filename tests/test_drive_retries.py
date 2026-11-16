"""Drive _with_retries: three tries, waits 10 and 30 s, on a passing answer (5xx, 429, rate limit) or a dropped
connection; the last answer is returned, a last dropped connection raises DriveError."""
import pytest

from ultron.workings.core import drive


class R:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


def _run(monkeypatch, answers):
    waits, seen = [], []
    monkeypatch.setattr(drive.time, "sleep", waits.append)

    def send():
        seen.append(1)
        a = answers[len(seen) - 1]
        if isinstance(a, Exception):
            raise a
        return a
    return waits, seen, (lambda: drive._with_retries(send, "read of x"))


def test_a_502_then_ok(monkeypatch):
    waits, seen, call = _run(monkeypatch, [R(502), R(200)])
    assert call().status_code == 200 and waits == [10] and len(seen) == 2


def test_rate_limit_and_dropped_connection_then_ok(monkeypatch):
    waits, seen, call = _run(monkeypatch, [R(403, "userRateLimitExceeded"), ConnectionError("reset"), R(200)])
    assert call().status_code == 200 and waits == [10, 30]


def test_always_failing_answer_is_returned_after_three_tries(monkeypatch):
    waits, seen, call = _run(monkeypatch, [R(500), R(503), R(500)])
    assert call().status_code == 500 and waits == [10, 30] and len(seen) == 3


def test_a_last_dropped_connection_raises(monkeypatch):
    waits, seen, call = _run(monkeypatch, [OSError("timed out")] * 3)
    with pytest.raises(drive.DriveError, match="failed 3 times: OSError: timed out"):
        call()
    assert waits == [10, 30]


def test_a_refusal_is_not_tried_again(monkeypatch):
    waits, seen, call = _run(monkeypatch, [R(404), R(200)])
    assert call().status_code == 404 and waits == [] and len(seen) == 1
