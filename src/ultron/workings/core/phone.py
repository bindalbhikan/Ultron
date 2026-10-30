"""Ultron Phone: work handed to the Android app (android app/), through the Telegram worker's
/api/phone routes (worker/src/worker.js), for what only a phone line can do - www.myntra.com
refuses GitHub's runners (HTTP 403) but answers a mobile connection.

    answers = phone.run_job("myntra_style", style_ids, wait_minutes=40)

The job waits in the worker until the phone asks for work (it asks every minute while Agent mode is
on), the phone answers it a part at a time, and run_job returns {item: answer} once the last part
is in. DASHBOARD_URL / DASHBOARD_TOKEN as for the dashboard pushes.
"""
from __future__ import annotations

import logging
import time
import uuid

import requests

from .config import env

log = logging.getLogger("bindal.phone")


class PhoneUnavailable(RuntimeError):
    pass


def _call(action: str, params: dict | None = None, body=None) -> dict:
    url, token = (env("DASHBOARD_URL") or "").rstrip("/"), env("DASHBOARD_TOKEN")
    if not url or not token:
        raise PhoneUnavailable("DASHBOARD_URL / DASHBOARD_TOKEN not set")
    r = requests.post(f"{url}/api/phone/{action}", params=params, json=body, timeout=60,
                      headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def status() -> dict:
    """When the phone last asked for work: {at (epoch ms), device, battery, version}, {} if never."""
    return _call("status")


def online(minutes: int = 20) -> bool:
    at = status().get("at") or 0
    return time.time() * 1000 - at < minutes * 60 * 1000


def run_job(kind: str, items: list, wait_minutes: float = 40, poll_seconds: int = 20) -> dict:
    """Queue a job for the phone and wait for its answers. Raises PhoneUnavailable when the phone
    has not asked for work lately, or does not take / finish the job in time."""
    if not online():
        raise PhoneUnavailable("the phone has not asked for work in the last 20 minutes (Agent mode off?)")
    job = f"{kind}-{uuid.uuid4().hex[:10]}"
    _call("job", body={"id": job, "kind": kind, "items": items})
    log.info("Phone job %s: %d items queued", job, len(items))
    deadline = time.time() + wait_minutes * 60
    taken_logged = False
    while time.time() < deadline:
        time.sleep(poll_seconds)
        got = _call("collect", {"job": job})
        if got.get("missing"):
            raise PhoneUnavailable(f"phone job {job} is gone from the worker")
        if got.get("taken") and not taken_logged:
            log.info("Phone job %s taken by the phone", job)
            taken_logged = True
        if got.get("done"):
            log.info("Phone job %s: %d answers", job, len(got.get("results") or {}))
            return got.get("results") or {}
    raise PhoneUnavailable(f"phone job {job} not finished in {wait_minutes:.0f} minutes"
                           + ("" if taken_logged else " (never taken)"))
