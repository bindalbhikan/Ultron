"""Hyper logs: every bot run's detailed log, kept on Drive.

run_bot() starts one per run: everything the bot's own loggers say down to DEBUG (the console keeps
INFO), with time to the millisecond, thread, module, function and line, a header (bot, arguments,
GitHub run, commit, host), every HTTP call (method, host/path, status, seconds, size) and a footer (exit code, minutes, the error's full traceback). Passwords,
tokens, cookies and other secrets are masked before anything is written. At the end of the run the
log goes to Drive:

  AGENT WORK/AGENT LOGS/<OCT-26>/<29-10-26>/<BOT> <05.31 PM> <OK|FAIL> #<GitHub run id>.log

(on GitHub always; a local run only with HYPERLOG_UPLOAD=1). The reporting sheet's LOGS tab
(work_schedule) lists the runs with a link to each log. HYPERLOG=0 turns it off.
"""
from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime

from .config import OUTPUT, env

log = logging.getLogger("bindal.hyperlog")

AGENT_WORK = "1uO-aOha_QKkI3f19EA7sweYPgkjMukZI"   # Drive BINDAL EXPORTS/AGENT WORK
FOLDER = "AGENT LOGS"
FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s [%(threadName)s] %(name)s %(funcName)s:%(lineno)d | %(message)s"
QUIET = ("urllib3", "requests", "google", "googleapiclient", "google_auth_httplib2", "openpyxl", "PIL",
         "asyncio", "httpx", "httpcore", "filelock", "charset_normalizer", "chardet", "matplotlib",
         "scrapy", "twisted", "selenium", "playwright", "patchright", "hpack", "multipart")
SECRET = [
    re.compile(r"(?i)\b(password|passwd|pwd|token|secret|authorization|cookie|set-cookie|api[_-]?key|"
               r"session|refresh_token|access_token|client_secret|otp)(\"?'?\s*[:=]\s*\"?'?)([^\s\"',;&]+)"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"),   # long keys / signed links
    re.compile(r"bot\d+:[A-Za-z0-9_-]+"),      # a Telegram bot token in a URL
]


def mask(text: str) -> str:
    text = SECRET[3].sub("bot***", text)
    text = SECRET[1].sub("Bearer ***", text)
    text = SECRET[0].sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    return SECRET[2].sub(lambda m: m.group(0)[:6] + "***", text)


class _Mask(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg, record.args = mask(record.getMessage()), ()
        except Exception:  # noqa: BLE001 - a log line must never break the bot
            pass
        return True


class HyperLog:
    def __init__(self, title: str, argv: list[str]):
        self.title, self.argv, self.started = title, argv, time.time()
        self.when = datetime.now()
        slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()
        self.path = OUTPUT / "hyperlog" / f"{slug}-{self.when:%Y%m%d-%H%M%S}.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handler = logging.FileHandler(self.path, encoding="utf-8")
        self.handler.setLevel(logging.DEBUG)
        self.handler.setFormatter(logging.Formatter(FORMAT, "%Y-%m-%d %H:%M:%S"))
        self.handler.addFilter(_Mask())
        root = logging.getLogger()
        for h in root.handlers:          # the console stays as it was
            if h.level == logging.NOTSET:
                h.setLevel(root.level or logging.INFO)
            h.addFilter(_Mask())
        root.setLevel(logging.DEBUG)
        for name in QUIET:
            logging.getLogger(name).setLevel(logging.WARNING)
        root.addHandler(self.handler)
        logging.captureWarnings(True)
        self._header()

    def _header(self):
        sha = os.getenv("GITHUB_SHA", "")[:7]
        if not sha:
            try:
                sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                     timeout=10).stdout.strip()
            except Exception:  # noqa: BLE001
                sha = "?"
        run = os.getenv("GITHUB_RUN_ID", "")
        url = f"https://github.com/{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{run}" if run else "local"
        for line in (f"===== {self.title} · started {self.when:%d-%m-%Y %I:%M:%S %p} IST =====",
                     f"arguments: {' '.join(self.argv) or '(none)'}",
                     f"mode: {env('RUN_MODE', 'local')} · workflow: {os.getenv('GITHUB_WORKFLOW', '-')} · "
                     f"event: {os.getenv('GITHUB_EVENT_NAME', '-')} · attempt: {os.getenv('GITHUB_RUN_ATTEMPT', '-')}",
                     f"run: {url} · commit: {sha}",
                     f"host: {platform.node()} · {platform.system()} {platform.release()} · "
                     f"python {sys.version.split()[0]}"):
            log.info(line)

    def finish(self, code: int, error: str = "", trace: str = "") -> None:
        minutes = (time.time() - self.started) / 60
        ok = code == 0 and not error
        log.info("===== finished: %s · exit code %s · %.1f min =====", "OK" if ok else "FAIL", code, minutes)
        if error:
            log.error("ERROR: %s", error)
        if trace:
            log.error("TRACEBACK:\n%s", trace)
        self.handler.flush()
        logging.getLogger().removeHandler(self.handler)
        self.handler.close()
        if env("RUN_MODE", "local") == "github-actions" or env("HYPERLOG_UPLOAD") == "1":
            self.upload(ok)

    def upload(self, ok: bool) -> None:
        """The log into AGENT WORK/AGENT LOGS/<MON-YY>/<dd-mm-yy>/; never fails the run."""
        try:
            from .drive import DriveFolder
            from .gauth import oauth_configured
            if not oauth_configured():
                print("hyperlog: not uploaded (no Drive OAuth token in this workflow)")
                return
            run = os.getenv("GITHUB_RUN_ID", "")
            name = (f"{re.sub(r'[^A-Za-z0-9 +-]+', '', self.title).upper()} {self.when:%I.%M %p} "
                    f"{'OK' if ok else 'FAIL'}{' #' + run if run else ''}.log")
            dest = self.path.with_name(name)
            dest.write_bytes(self.path.read_bytes())
            folder = (DriveFolder(env("AGENT_WORK_FOLDER_ID", AGENT_WORK)).subfolder(FOLDER, create=True)
                      .subfolder(f"{self.when:%b-%y}".upper(), create=True)
                      .subfolder(f"{self.when:%d-%m-%y}", create=True))
            folder.put(dest, "text/plain")
        except Exception as exc:  # noqa: BLE001 - the log is a by-product, the run's result stands
            print(f"hyperlog: not uploaded ({str(exc)[:200]})")


_http = logging.getLogger("bindal.http")
_patched = False


def _log_http() -> None:
    """Every requests call into the hyper log: method, host and path (no query string), status,
    seconds and size; a call that fails, its error."""
    global _patched
    if _patched:
        return
    try:
        import requests
    except ImportError:
        return
    original = requests.sessions.Session.send

    def send(self, request, **kw):
        t0 = time.time()
        where = re.sub(r"[?#].*", "", str(request.url))
        try:
            r = original(self, request, **kw)
        except Exception as exc:
            _http.debug("HTTP %s %s -> %s (%.2f s)", request.method, where, type(exc).__name__, time.time() - t0)
            raise
        size = r.headers.get("Content-Length") or (len(r.content) if not kw.get("stream") else "?")
        _http.debug("HTTP %s %s -> %s (%.2f s, %s bytes)", request.method, where, r.status_code, time.time() - t0, size)
        return r

    requests.sessions.Session.send = send
    _patched = True


def start(title: str, argv: list[str]) -> HyperLog | None:
    if env("HYPERLOG", "1") == "0":
        return None
    try:
        _log_http()
        return HyperLog(title, argv)
    except Exception as exc:  # noqa: BLE001
        print(f"hyperlog: off for this run ({exc})")
        return None
