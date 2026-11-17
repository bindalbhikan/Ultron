"""workings/core/telegram._post on ultron.core.retry: the same tries and waits as before (docs/libraries/04-tenacity.md)."""
import io

import httpx

from ultron.workings.core import telegram


def _ok():
    return httpx.Response(200)


def test_a_dropped_connection_is_sent_again_and_files_rewound(monkeypatch):
    waits, seen = [], []
    monkeypatch.setattr("time.sleep", waits.append)
    fh = io.BytesIO(b"abc")

    def post(url, timeout, **kw):
        seen.append(kw["files"]["document"][1].read())
        if len(seen) < 3:
            raise httpx.ReadError("Connection reset by peer")
        return _ok()
    monkeypatch.setattr("ultron.core.http.post", post)
    r = telegram._post("t", "sendDocument", files={"document": ("a.txt", fh)})
    assert r is not None and r.status_code == 200
    assert seen == [b"abc", b"abc", b"abc"] and waits == [5, 10]


def test_gives_up_after_three_tries(monkeypatch):
    waits, seen = [], []
    monkeypatch.setattr("time.sleep", waits.append)

    def post(url, timeout, **kw):
        seen.append(1)
        raise httpx.ReadTimeout("read timed out")
    monkeypatch.setattr("ultron.core.http.post", post)
    assert telegram._post("t", "sendMessage", json={}) is None
    assert len(seen) == 3 and waits == [5, 10]


def test_another_request_error_is_not_tried_again(monkeypatch):
    seen = []

    def post(url, timeout, **kw):
        seen.append(1)
        raise httpx.InvalidURL("bad")
    monkeypatch.setattr("ultron.core.http.post", post)
    assert telegram._post("t", "sendMessage", json={}) is None
    assert len(seen) == 1


def test_the_agent_sends_through_the_same_retrying_sender(monkeypatch):
    """docs/CENTRALISE.md step 3: the agent's Telegram had no retry at all before 16 Nov 2026."""
    from ultron.integrations import telegram as agent_telegram
    waits, seen = [], []
    monkeypatch.setattr(agent_telegram.time, "sleep", waits.append)

    def post(url, timeout, **kw):
        seen.append(1)
        if len(seen) < 2:
            raise httpx.ReadError("Connection reset by peer")
        return _ok()
    monkeypatch.setattr("ultron.core.http.post", post)
    assert agent_telegram._post("t", "sendMessage", json={}).status_code == 200
    assert len(seen) == 2 and waits == [5]
