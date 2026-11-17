"""HTTP in one place (docs/libraries/08-httpx.md): httpx, and JSON answers read by orjson.

    s = client(headers={...}, timeout=60)     an httpx.Client that follows redirects (as requests did); keep and reuse
    r = get(url, params=..., timeout=60)      one call without a client;  post(...), request("PUT", ...)
    json_of(r)                                the answer's JSON (orjson when installed, else the json module)
    HTTPError                                 every failure httpx raises (connection, timeout, a raised status)

httpx has requests' shape plus strict timeouts, HTTP/2 and async for a big seller's many calls at once. Two of its
ways differ from requests and are kept the requests way here: redirects are followed, and a text page with no
charset is read as UTF-8 (requests guessed). `r.url` is an httpx.URL: str(r.url) where text is meant.
curl_cffi stays where a site checks the browser's TLS fingerprint (Myntra partner portal, couriers).
"""
from __future__ import annotations

from typing import Any

import httpx

from .jsonx import loads

HTTPError = httpx.HTTPError
Response = httpx.Response
# what requests called RequestException (httpx's InvalidURL is not an HTTPError)
FAILED: tuple[type[Exception], ...] = (httpx.HTTPError, httpx.InvalidURL)
# what requests called ConnectionError / Timeout: a dropped or slow connection, worth trying again
PASSING: tuple[type[Exception], ...] = (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError)


def ok(r: Any) -> bool:
    """requests' r.ok: any status below 400."""
    return r is not None and r.status_code < 400


def client(*, headers: dict | None = None, timeout: float = 60, follow_redirects: bool = True, http2: bool = False,
           **kw) -> httpx.Client:
    """A reusable client (connection pool, cookies kept between calls)."""
    return httpx.Client(headers=headers, timeout=timeout, follow_redirects=follow_redirects, http2=http2, **kw)


def request(method: str, url: str, *, timeout: float = 60, follow_redirects: bool = True, **kw) -> httpx.Response:
    return httpx.request(method, url, timeout=timeout, follow_redirects=follow_redirects, **kw)


def get(url: str, **kw) -> httpx.Response:
    return request("GET", url, **kw)


def post(url: str, **kw) -> httpx.Response:
    return request("POST", url, **kw)


def json_of(r: Any) -> Any:
    """The JSON body of a response (httpx, requests or curl_cffi: anything with .content)."""
    return loads(r.content)
