"""HTTP in one place (ultron/core/http.py, jsonx.py; docs/libraries/08-httpx.md, 10-small.md)."""
import httpx
import pytest

from ultron.core import http, jsonx


def test_json_read_the_same_way_with_or_without_orjson(monkeypatch):
    body = b'{"a": [1, 2.5, "x\u20b9"], "b": null, "n": 123456789012345678}'
    fast = jsonx.loads(body)
    monkeypatch.setattr(jsonx, "_orjson", None)
    assert jsonx.loads(body) == fast == {"a": [1, 2.5, "x\u20b9"], "b": None, "n": 123456789012345678}


def test_what_orjson_refuses_json_still_reads():
    assert jsonx.loads("[NaN]")[0] != jsonx.loads("[NaN]")[0]          # NaN
    assert jsonx.loads(str(10**30)) == 10**30 and isinstance(jsonx.loads(str(10**30)), int)   # beyond 64 bits: exact
    assert jsonx.loads('{"id": 18446744073709551617}')["id"] == 18446744073709551617
    with pytest.raises(ValueError):
        jsonx.loads(b"not json")


def test_json_of_any_response_and_ok_like_requests():
    r = httpx.Response(200, content=b'{"ok": 1}')
    assert http.json_of(r) == {"ok": 1}
    assert http.ok(r) and http.ok(httpx.Response(302)) and not http.ok(httpx.Response(404)) and not http.ok(None)


def test_errors_grouped_as_requests_grouped_them():
    assert issubclass(httpx.ReadError, http.PASSING) and issubclass(httpx.ReadTimeout, http.PASSING)
    assert issubclass(httpx.ConnectError, http.CONNECTION) and not issubclass(httpx.ReadTimeout, http.CONNECTION)
    assert issubclass(httpx.InvalidURL, http.FAILED) and issubclass(httpx.HTTPStatusError, http.FAILED)


def test_a_client_follows_redirects():
    def answer(request):
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "/b"})
        return httpx.Response(200, text="here")
    with http.client(transport=httpx.MockTransport(answer)) as c:
        r = c.get("https://x/a")
    assert r.status_code == 200 and r.text == "here" and str(r.url) == "https://x/b"
