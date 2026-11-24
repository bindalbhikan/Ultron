"""A temporarily sleeping phone gets time to reconnect without exceeding the job budget."""
import pytest

from ultron.workings.core import phone


def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(phone.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(phone.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    return now


def test_reconnect_queues_only_when_online_and_collects_answer(monkeypatch):
    now = clock(monkeypatch)
    monkeypatch.setattr(phone, "online", lambda: now[0] >= 20)
    calls = []
    def call(action, params=None, body=None):
        calls.append((action, now[0]))
        return {"done": 1, "results": {"1": {"id": 1}}} if action == "collect" else {}
    monkeypatch.setattr(phone, "_call", call)
    assert phone.run_job("myntra_style", [1], wait_minutes=1) == {"1": {"id": 1}}
    assert calls == [("job", 20), ("collect", 40)]


def test_offline_timeout_never_leaves_a_job_for_a_later_run(monkeypatch):
    now = clock(monkeypatch)
    monkeypatch.setattr(phone, "online", lambda: False)
    monkeypatch.setattr(phone, "_call", lambda *a, **k: pytest.fail("offline phone must not receive a job"))
    with pytest.raises(phone.PhoneUnavailable, match="did not reconnect"):
        phone.run_job("myntra_style", [1], wait_minutes=1)
    assert now[0] == 60


def test_reconnect_and_processing_share_the_same_deadline(monkeypatch):
    now = clock(monkeypatch)
    monkeypatch.setattr(phone, "online", lambda: now[0] >= 40)
    monkeypatch.setattr(phone, "_call", lambda *a, **k: {})
    with pytest.raises(phone.PhoneUnavailable, match="not finished"):
        phone.run_job("myntra_style", [1], wait_minutes=1)
    assert now[0] == 60


def test_zero_td_retry_never_starts_another_full_wait(monkeypatch):
    from ultron.workings.myntra_zero_td import pipeline
    now = clock(monkeypatch)
    monkeypatch.setenv("MYNTRA_ZERO_TD_VIA", "phone")
    monkeypatch.setenv("MYNTRA_ZERO_TD_PHONE_MINUTES", "2")
    calls = []
    def run_job(kind, items, wait_minutes=40):
        calls.append(wait_minutes)
        if len(calls) == 1:
            now[0] += 70
            return {"1": {"id": 1}, "2": "HTTP 403"}
        pytest.fail("there is not enough time for the retry pause")
    monkeypatch.setattr(phone, "run_job", run_job)
    assert pipeline.lookup([1, 2]) == {1: {"id": 1}, 2: "HTTP 403"}
    assert calls == [2]
