"""The one browser of Ultron: Patchright (a Playwright drop-in), and no other. Anything that needs a
browser opens it here, so settings and safety checks stay in one place.

Each session gets a new empty profile: no saved logins or cookies. Install with
`pip install -e ".[browser]"`, then `patchright install chromium`. Settings: BROWSER_HEADLESS (0 for
a visible window; default on), BROWSER_CHANNEL ("chrome" for the installed Chrome; default the
bundled Chromium).

A challenge (CAPTCHA, "verify you are human") is reported and never solved or worked around.
"""
from __future__ import annotations

import ipaddress
import socket
import tempfile
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator
from urllib.parse import urlsplit

from .config import env

LOAD_MS = 45_000       # the page must load within this
SETTLE_MS = 5_000      # then up to this for its scripts to fetch their data
INSTALL = 'pip install -e ".[browser]" and patchright install chromium'
CHALLENGE_WORDS = ("verify you are human", "not a robot", "are you a robot", "unusual traffic",
                   "checking your browser", "press & hold", "access denied", "captcha")
CHALLENGE_FRAMES = ("recaptcha", "hcaptcha", "challenges.cloudflare.com", "captcha-delivery")
CHALLENGE_MAX_CHARS = 1500   # a full page that only mentions these words is not a challenge


class BrowserError(RuntimeError):
    """The page could not be read; the message says why and is safe to show."""


@lru_cache(maxsize=256)
def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0].split("%")[0]).is_global for i in infos)


def check_url(url: str) -> str:
    """The URL when it is http(s) on the public internet; machines on the seller's own network and
    cloud metadata addresses are refused."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BrowserError(f"only http(s) addresses can be opened, not {url!r}")
    if not _is_public_host(parts.hostname):
        raise BrowserError(f"{parts.hostname} is not a public internet address, or does not exist")
    return url.strip()


def is_challenge(text: str, frame_urls: list[str]) -> bool:
    """A short page with CAPTCHA words or a CAPTCHA frame in it."""
    if len(text.strip()) > CHALLENGE_MAX_CHARS:
        return False
    low = text.lower()
    return any(w in low for w in CHALLENGE_WORDS) or any(f in u.lower() for u in frame_urls for f in CHALLENGE_FRAMES)


def _guard(route) -> None:
    """Keep every request of the page on the public internet, not only the page's own address."""
    host = urlsplit(route.request.url).hostname
    if route.request.url.startswith(("http:", "https:")) and not (host and _is_public_host(host)):
        route.abort()
    else:
        route.continue_()


@contextmanager
def session() -> Iterator:
    """A Patchright browser context with a new empty profile, closed and deleted afterwards."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        raise BrowserError(f"Patchright is not installed: {INSTALL}") from None
    with tempfile.TemporaryDirectory(prefix="ultron-browser-", ignore_cleanup_errors=True) as profile:
        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    profile, headless=env("BROWSER_HEADLESS", "1") != "0",
                    channel=env("BROWSER_CHANNEL") or None,
                    accept_downloads=False, service_workers="block")
            except Exception as exc:
                raise BrowserError(f"browser did not start ({INSTALL}): {str(exc)[:200]}") from None
            try:
                context.route("**/*", _guard)
                yield context
            finally:
                context.close()


def read_page(url: str) -> dict:
    """Open a public page and return {url, title, text, links}. Reads only: nothing is clicked,
    typed or sent. Raises BrowserError when the page failed, is empty or shows a challenge."""
    url = check_url(url)
    with session() as context:
        page = context.pages[0] if context.pages else context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=LOAD_MS)
        except Exception as exc:
            raise BrowserError(f"{url} did not load: {str(exc).splitlines()[0][:200]}") from None
        check_url(page.url)    # a redirect may have left the public internet
        try:
            page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
        except Exception:      # a page that keeps fetching is read as it stands
            pass
        check_url(page.url)
        text = page.locator("body").inner_text(timeout=SETTLE_MS).strip()
        frames = [f.url for f in page.frames]
        if is_challenge(text, frames):
            raise BrowserError(f"{page.url} shows a CAPTCHA or bot check. It was not solved: the page is left out.")
        if response is not None and response.status >= 400:
            raise BrowserError(f"{page.url} answered HTTP {response.status}")
        if not text:
            raise BrowserError(f"{page.url} shows no text")
        links = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => [e.innerText.trim().slice(0, 80), e.href])")
        return {"url": page.url, "title": page.title(), "text": text,
                "links": [(t, h) for t, h in links if h.startswith("http")]}
