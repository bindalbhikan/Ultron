"""Passing outages are tried again instead of failing the run (Nov 2026 failures)."""
from datetime import date
from types import SimpleNamespace

import pytest
import requests


def test_zero_td_asks_the_phone_again_for_styles_without_an_answer(monkeypatch):
    from ultron.workings.core import phone
    from ultron.workings.myntra_zero_td import pipeline
    monkeypatch.setenv("MYNTRA_ZERO_TD_VIA", "phone")
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    calls = []

    def run_job(kind, items, wait_minutes=40):
        calls.append(list(items))
        if len(calls) == 1:
            return {"1": {"id": 1}, "2": "UnknownHostException: Unable to resolve host", "3": "NOT FOUND"}
        return {str(i): {"id": i} for i in items}
    monkeypatch.setattr(phone, "run_job", run_job)
    got = pipeline.lookup([1, 2, 3])
    assert calls == [[1, 2, 3], [2]]
    assert got == {1: {"id": 1}, 2: {"id": 2}, 3: "NOT FOUND"}


def test_myntra_reports_second_round_for_a_refused_or_killed_report(monkeypatch):
    from ultron.workings.myntra_reports import pipeline
    from ultron.workings.portals import myntra as mp
    from ultron.workings.return_analysis import sources
    asked = []

    class Portal:
        def ensure(self, rid, start, end, fresh=False):
            asked.append(rid)
            if rid == 12 and asked.count(12) == 1:
                raise RuntimeError("Internal server error while scheduling report job")
            return {"id": rid, "n": asked.count(rid)}

        def schedule(self, start, end, rid):
            return self.ensure(rid, start, end)

        def jobs(self, size=50):
            return []

        def _wait(self, job, deadline, poll):
            if job["id"] == 84 and job["n"] == 1:
                raise RuntimeError("Myntra report job INTERRUPTED: cluster is out of memory")
            return job

        def download(self, job):
            return "x.csv", b"type,created on\nReturn,2026-11-16 10:00:00\n"

        def cookies(self):
            return []
    monkeypatch.setattr(sources, "myntra_portal", lambda a: Portal())
    monkeypatch.setattr(mp, "save_to_worker", lambda *a: True)
    made, notes = pipeline.make_account("MAIN", date(2026, 11, 15), 1)
    assert set(made) == set(pipeline.REPORTS) and notes == []
    assert asked.count(12) == 2 and asked.count(84) == 2 and asked.count(4) == 1


def test_omsguru_get_waits_out_a_server_error(monkeypatch):
    from ultron.portals import omsguru
    monkeypatch.setattr(omsguru.time, "sleep", lambda s: None)
    answers = iter([500] * 5 + [200])
    client = SimpleNamespace(timeout=5, s=SimpleNamespace(
        get=lambda url, timeout, **kw: SimpleNamespace(status_code=next(answers), url=url)))
    assert omsguru.OmsGuruClient.get(client, "https://x/login").status_code == 200


def test_omsguru_get_gives_up_soon_on_a_client_error(monkeypatch):
    from ultron.portals import omsguru
    monkeypatch.setattr(omsguru.time, "sleep", lambda s: None)
    seen = []

    def get(url, timeout, **kw):
        seen.append(1)
        return SimpleNamespace(status_code=404, url=url)
    client = SimpleNamespace(timeout=5, s=SimpleNamespace(get=get))
    with pytest.raises(omsguru.OmsGuruError):
        omsguru.OmsGuruClient.get(client, "https://x/page")
    assert len(seen) == 3


def test_omsguru_get_retries_a_dropped_connection(monkeypatch):
    from ultron.portals import omsguru
    monkeypatch.setattr(omsguru.time, "sleep", lambda s: None)
    seen = []

    def get(url, timeout, **kw):
        seen.append(1)
        if len(seen) < 5:
            raise requests.ConnectionError("reset")
        return SimpleNamespace(status_code=200, url=url)
    client = SimpleNamespace(timeout=5, s=SimpleNamespace(get=get))
    assert omsguru.OmsGuruClient.get(client, "https://x/page").status_code == 200
