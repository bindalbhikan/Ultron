"""Myntra partner portal schedule(): one wait of the 16-minute cooldown, only for a cooldown refusal."""
import pytest

from ultron.workings.portals import myntra as mp


def _portal(answers):
    p = mp.MyntraPortal.__new__(mp.MyntraPortal)
    calls = []

    def call(method, path, **kw):
        calls.append(path)
        a = answers[len(calls) - 1]
        if isinstance(a, Exception):
            raise a
        return a
    p._call = call
    return p, calls


REFUSED = RuntimeError("Myntra portal /report/jobs/schedule: HTTP 200 Internal server error while scheduling report job.")


def test_a_cooldown_refusal_is_waited_out_once(monkeypatch):
    waits = []
    monkeypatch.setattr(mp.time, "sleep", waits.append)
    p, calls = _portal([REFUSED, {"data": [{"id": 7}]}])
    assert p.schedule(None, None, 14)["id"] == 7
    assert len(calls) == 2 and waits == [16 * 60]


def test_refused_twice_raises_the_refusal(monkeypatch):
    waits = []
    monkeypatch.setattr(mp.time, "sleep", waits.append)
    p, calls = _portal([REFUSED, REFUSED])
    with pytest.raises(RuntimeError, match="Internal server error"):
        p.schedule(None, None, 14)
    assert len(calls) == 2 and waits == [16 * 60]


def test_no_wait_when_asked_not_to_or_for_another_error(monkeypatch):
    waits = []
    monkeypatch.setattr(mp.time, "sleep", waits.append)
    p, calls = _portal([REFUSED])
    with pytest.raises(RuntimeError):
        p.schedule(None, None, 14, cooldown_wait=0)
    p, calls = _portal([mp.SessionExpired("logged out")])
    with pytest.raises(mp.SessionExpired):
        p.schedule(None, None, 14)
    p, calls = _portal([RuntimeError("HTTP 403 forbidden")])
    with pytest.raises(RuntimeError, match="403"):
        p.schedule(None, None, 14)
    assert waits == []


def test_no_job_in_the_answer_is_an_error(monkeypatch):
    p, _ = _portal([{"data": []}])
    with pytest.raises(RuntimeError, match="did not return the scheduled report job"):
        p.schedule(None, None, 14)
