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
