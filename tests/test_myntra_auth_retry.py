"""Myntra portal: a passing "Authorization could not be completed" is asked again, a real logout is not
(9, 12 and 21 Nov 2026: MAIN's daily reports stopped on it while the login still worked)."""
import pytest

from ultron.workings.portals import myntra as mp


class _Answer:
    def __init__(self, status_code, body):
        self.status_code, self._body, self.text = status_code, body, str(body)


def _portal(answers, monkeypatch):
    p = mp.MyntraPortal.__new__(mp.MyntraPortal)
    p.timeout = 5
    seen = []

    class _Http:
        def request(self, method, url, **kw):
            seen.append(url)
            return answers.pop(0)
    p.http = _Http()
    monkeypatch.setattr("ultron.core.http.json_of", lambda r: r._body)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return p, seen


REFUSED = {"status": {"statusType": "ERROR", "statusMessage": "Authorization could not be completed"}}
OK = {"status": {"statusType": "SUCCESS"}, "data": [1]}


def test_a_passing_authorization_refusal_is_asked_again(monkeypatch):
    p, seen = _portal([_Answer(200, REFUSED), _Answer(200, REFUSED), _Answer(200, OK)], monkeypatch)
    assert p._call("GET", "/report/jobs") == OK
    assert len(seen) == 3


def test_it_counts_as_logged_out_after_the_last_try(monkeypatch):
    p, seen = _portal([_Answer(200, REFUSED)] * 4, monkeypatch)
    with pytest.raises(mp.SessionExpired, match="could not be completed"):
        p._call("GET", "/report/jobs")
    assert len(seen) == 4


def test_http_403_is_a_logout_at_once(monkeypatch):
    p, seen = _portal([_Answer(403, {}), _Answer(200, OK)], monkeypatch)
    with pytest.raises(mp.SessionExpired, match="403"):
        p._call("GET", "/report/jobs")
    assert len(seen) == 1


def test_another_login_message_is_not_asked_again(monkeypatch):
    other = {"status": {"statusType": "ERROR", "statusMessage": "Invalid session, please login"}}
    p, seen = _portal([_Answer(200, other), _Answer(200, OK)], monkeypatch)
    with pytest.raises(mp.SessionExpired):
        p._call("GET", "/report/jobs")
    assert len(seen) == 1
