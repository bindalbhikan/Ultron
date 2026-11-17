"""AJIO client _req: three tries, waits 3 and 6 s, on a 5xx or a request error; the last 5xx answer is
returned, a last request error raised; a 4xx answer at once."""
import pytest
import httpx

from ultron.workings.portals import ajio


class R:
    def __init__(self, status):
        self.status_code = status


def _client(monkeypatch, answers):
    waits, seen = [], []
    monkeypatch.setattr(ajio.time, "sleep", waits.append)
    c = ajio.AjioClient.__new__(ajio.AjioClient)
    c.timeout = 5

    class S:
        def request(self, method, url, timeout, **kw):
            seen.append(method)
            a = answers[len(seen) - 1]
            if isinstance(a, Exception):
                raise a
            return a
    c.s = S()
    return c, waits, seen


def test_a_5xx_then_ok(monkeypatch):
    c, waits, seen = _client(monkeypatch, [R(502), R(200)])
    assert c._req("GET", "/x").status_code == 200 and waits == [3] and len(seen) == 2


def test_last_5xx_is_returned(monkeypatch):
    c, waits, seen = _client(monkeypatch, [R(500), R(503), R(500)])
    assert c._req("POST", "/x").status_code == 500 and waits == [3, 6] and len(seen) == 3


def test_last_request_error_is_raised(monkeypatch):
    c, waits, seen = _client(monkeypatch, [httpx.ConnectError("a"), httpx.ReadTimeout("b"), httpx.ConnectError("c")])
    with pytest.raises(httpx.ConnectError, match="c"):
        c._req("GET", "/x")
    assert waits == [3, 6]


def test_a_4xx_is_returned_at_once(monkeypatch):
    c, waits, seen = _client(monkeypatch, [R(401), R(200)])
    assert c._req("GET", "/x").status_code == 401 and waits == [] and len(seen) == 1
