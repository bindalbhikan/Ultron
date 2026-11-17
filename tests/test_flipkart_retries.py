"""Flipkart client retries: login (3 tries on a dropped connection, waits 20, 40 s) and _post (3 tries on a
5xx or a dropped connection, waits 5, 10 s; any other answer than 200 raised as FlipkartError)."""
import pytest
import json

import httpx

from ultron.workings.portals import flipkart


class R:
    def __init__(self, status, body=None):
        self.status_code, self._body, self.text = status, body or {}, "x"

    def json(self):
        return self._body

    @property
    def content(self):
        return json.dumps(self._body).encode()


def _client(monkeypatch):
    waits = []
    monkeypatch.setattr(flipkart.time, "sleep", waits.append)
    c = flipkart.FlipkartClient("u", "p")
    c.csrf = "t"
    return c, waits


def test_login_dropped_connection_tried_again(monkeypatch):
    c, waits = _client(monkeypatch)
    seen = []

    def login():
        seen.append(1)
        if len(seen) < 3:
            raise httpx.ConnectError("reset")
    c._login = login
    c.login()
    assert len(seen) == 3 and waits == [20, 40]


def test_login_refused_is_not_tried_again(monkeypatch):
    c, waits = _client(monkeypatch)
    seen = []

    def login():
        seen.append(1)
        raise flipkart.FlipkartError("wrong password")
    c._login = login
    with pytest.raises(flipkart.FlipkartError):
        c.login()
    assert len(seen) == 1 and waits == []


def test_login_dropped_every_time_raises(monkeypatch):
    c, waits = _client(monkeypatch)
    c._login = lambda: (_ for _ in ()).throw(httpx.ConnectError("reset"))
    with pytest.raises(httpx.ConnectError):
        c.login()
    assert waits == [20, 40]


def _posting(c, answers):
    seen = []

    def post(url, json, headers, timeout):
        seen.append(1)
        a = answers[len(seen) - 1]
        if isinstance(a, Exception):
            raise a
        return a
    c.s.post = post
    return seen


def test_post_5xx_and_drop_then_ok(monkeypatch):
    c, waits = _client(monkeypatch)
    seen = _posting(c, [R(502), httpx.ConnectError("x"), R(200, {"ok": 1})])
    assert c._post("/napi/x", {}) == {"ok": 1} and waits == [5, 10] and len(seen) == 3


def test_post_last_5xx_raised_as_flipkart_error(monkeypatch):
    c, waits = _client(monkeypatch)
    _posting(c, [R(500)] * 3)
    with pytest.raises(flipkart.FlipkartError, match="HTTP 500"):
        c._post("/napi/x", {})
    assert waits == [5, 10]


def test_post_4xx_at_once_and_one_try(monkeypatch):
    c, waits = _client(monkeypatch)
    seen = _posting(c, [R(403)])
    with pytest.raises(flipkart.FlipkartError, match="HTTP 403"):
        c._post("/napi/x", {})
    assert len(seen) == 1 and waits == []
    seen = _posting(c, [httpx.ConnectError("x")])
    with pytest.raises(httpx.ConnectError):
        c._post("/napi/x", {}, tries=1)
    assert waits == []
