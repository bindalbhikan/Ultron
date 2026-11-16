"""workings/core/telegram._post on ultron.core.retry: the same tries and waits as before (docs/libraries/04-tenacity.md)."""
import io

import requests

from ultron.workings.core import telegram


def _ok():
    r = requests.Response()
    r.status_code = 200
    return r


def test_a_dropped_connection_is_sent_again_and_files_rewound(monkeypatch):
    waits, seen = [], []
    monkeypatch.setattr(telegram.time, "sleep", waits.append)
    fh = io.BytesIO(b"abc")

    def post(url, timeout, **kw):
        seen.append(kw["files"]["document"][1].read())
        if len(seen) < 3:
            raise requests.ConnectionError("Connection reset by peer")
        return _ok()
    monkeypatch.setattr(telegram.requests, "post", post)
    r = telegram._post("t", "sendDocument", files={"document": ("a.txt", fh)})
    assert r is not None and r.status_code == 200
    assert seen == [b"abc", b"abc", b"abc"] and waits == [5, 10]


def test_gives_up_after_three_tries(monkeypatch):
    waits, seen = [], []
    monkeypatch.setattr(telegram.time, "sleep", waits.append)

    def post(url, timeout, **kw):
        seen.append(1)
        raise requests.Timeout("read timed out")
    monkeypatch.setattr(telegram.requests, "post", post)
    assert telegram._post("t", "sendMessage", json={}) is None
    assert len(seen) == 3 and waits == [5, 10]


def test_another_request_error_is_not_tried_again(monkeypatch):
    seen = []

    def post(url, timeout, **kw):
        seen.append(1)
        raise requests.exceptions.InvalidURL("bad")
    monkeypatch.setattr(telegram.requests, "post", post)
    assert telegram._post("t", "sendMessage", json={}) is None
    assert len(seen) == 1
