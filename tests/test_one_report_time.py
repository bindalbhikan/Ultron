"""9:30 AM is the one time the daily Myntra reports are asked for; the other workings reuse those jobs."""
from datetime import date, datetime, timedelta

import pandas as pd

from ultron.workings.portals import myntra as mp


def _ms(d: date) -> int:
    return int(datetime.combine(d, datetime.min.time()).timestamp() * 1000) + 10 * 3600 * 1000


def _job(rid, first, last, made, status="COMPLETED", jid=1):
    return {"id": jid, "reportId": rid, "status": status, "successFile": "f.csv", "createdOn": _ms(made),
            "queryParams": {**mp.QUERY, "reportStartDate": f"{first}", "reportEndDate": f"{last}"}}


def test_day_rows_cut_by_the_dates_the_portal_filters_on():
    from ultron.workings.myntra_reports.pipeline import day_rows
    day = date(2026, 11, 15)
    returns = pd.DataFrame({"return_created_date": ["2026-11-15 10:00", "1970-01-01 05:30", "2026-11-14 09:00", "1970-01-01"],
                            "order_rto_date": ["", "2026-11-15 11:00", "", "2026-11-13"]})
    assert len(day_rows("Returns", returns, day)) == 2
    delivery = pd.DataFrame({"deliver_to_seller_date": ["2026-11-15 12:00", "2026-11-10 12:00"]})
    assert len(day_rows("Return Delivery", delivery, day)) == 1
    orders = pd.DataFrame({"created on": ["2026-11-15 01:00", "2026-11-01 01:00"]})
    assert len(day_rows("Orders", orders, day)) == 1
    assert len(day_rows("Returns", pd.DataFrame({"x": [1]}), day)) == 0


def test_daily_returns_jobs_are_the_spf_masters_30_days():
    from ultron.workings.myntra_reports import pipeline
    from ultron.workings.myntra_spf.pipeline import _windows
    asked = {}

    class Portal:
        def ensure(self, rid, a, b, fresh=False):
            asked[rid] = (a, b)
            return {}
    today = date(2026, 11, 16)
    for label in ("Orders", "Returns", "Return Delivery"):
        pipeline._job(Portal(), label, pipeline.REPORTS[label], today - timedelta(days=1))
    w = _windows(today)
    assert asked[mp.RETURNS_REPORT_ID] == w[mp.RETURNS_REPORT_ID][-1]
    assert asked[84] == w[84][-1]
    assert asked[mp.REPORT_ID] == w[mp.REPORT_ID][-1]


def test_covering_job_serves_a_shorter_range_and_is_cut():
    jobs = [_job(4, date(2026, 10, 17), date(2026, 11, 15), date(2026, 11, 16), jid=7),
            _job(4, date(2026, 11, 1), date(2026, 11, 10), date(2026, 11, 11), jid=8)]
    assert mp.covering_job(jobs, 4, date(2026, 11, 1), date(2026, 11, 15))["id"] == 7
    assert mp.covering_job(jobs, 4, date(2026, 10, 1), date(2026, 11, 15)) is None
    data = b"created on,x\n2026-10-31 10:00,1\n2026-11-01 10:00,2\n2026-11-15 23:00,3\n"
    cut = pd.read_csv(__import__("io").BytesIO(mp.cut_orders(data, date(2026, 11, 1), date(2026, 11, 15))))
    assert cut["x"].tolist() == [2, 3]


def test_reports_without_asking_waits_for_the_daily_run_job(monkeypatch):
    monkeypatch.setattr(mp.time, "sleep", lambda s: None)
    yday = date.today() - timedelta(days=1)
    listings = [[], [_job(4, yday - timedelta(days=29), yday, date.today(), status="COMPLETED", jid=5)]]
    portal = mp.MyntraPortal.__new__(mp.MyntraPortal)
    calls = {"jobs": 0}

    def jobs(size=50, start=0):
        calls["jobs"] += 1
        return listings[min(calls["jobs"] - 1, 1)]
    portal.jobs = jobs
    portal.schedule = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not ask"))
    portal.download = lambda job: ("r.csv", b"created on\n")
    monkeypatch.setattr(mp, "data_stamp", lambda text: datetime.combine(date.today(), datetime.min.time()))
    files, covered = portal.reports([yday], wait_minutes=5, ask=False)
    assert yday in covered and len(files) == 1 and calls["jobs"] >= 2


def test_grouping_takes_the_newest_listings_job_of_today_or_yesterday():
    from ultron.workings.myntra_grouping.pipeline import newest_listings_job
    today = date.today()
    jobs = [{"id": 1, "reportId": 14, "status": "COMPLETED", "successFile": "a", "createdOn": _ms(today - timedelta(days=3))},
            {"id": 2, "reportId": 14, "status": "COMPLETED", "successFile": "b", "createdOn": _ms(today)},
            {"id": 3, "reportId": 14, "status": "IN_PROGRESS", "createdOn": _ms(today) + 1}]
    assert newest_listings_job(jobs, today - timedelta(days=1))["id"] == 2
    assert newest_listings_job(jobs[:1], today - timedelta(days=1)) is None


def test_portal_reports_fresh_reuses_only_a_job_made_today(monkeypatch):
    from ultron.workings.portal_monthly import pipeline
    first, last = date(2026, 10, 1), date(2026, 10, 31)
    old = _job(4, first, last, date(2026, 11, 2), jid=1)
    new = _job(4, first, last, date.today(), jid=2)

    class Portal:
        def __init__(self, jobs):
            self._jobs = jobs

        def jobs(self, size=100):
            return self._jobs

        def schedule(self, a, b, rid):
            return {"id": "new"}

        def ensure(self, rid, a, b):
            return mp.exact_job(self._jobs, rid, a, b)
    monkeypatch.setattr(pipeline, "FRESH_FROM", date.today())
    assert pipeline.myntra_job(Portal([old]), 4, first, last)["id"] == "new"
    assert pipeline.myntra_job(Portal([old, new]), 4, first, last)["id"] == 2
    monkeypatch.setattr(pipeline, "FRESH_FROM", None)
    assert pipeline.myntra_job(Portal([old]), 4, first, last)["id"] == 1


def test_myntra_reports_asks_anew_when_the_orders_data_is_short(monkeypatch, tmp_path):
    from ultron.workings.myntra_reports import pipeline
    from ultron.workings.return_analysis import sources
    fresh_asks = []

    class Portal:
        def ensure(self, rid, start, end, fresh=False):
            if fresh:
                fresh_asks.append(rid)
            return {"id": rid, "fresh": fresh}

        def schedule(self, start, end, rid):
            return {"id": rid, "fresh": False}

        def jobs(self, size=50):
            return []

        def collect(self, job, wait):
            stamp = "2026-11-16 10:00:00" if job["fresh"] else "2026-11-15 03:00:00"
            return "x.csv", f"type,created on\nReturn,{stamp}\n".encode()

        def cookies(self):
            return []
    monkeypatch.setattr(sources, "myntra_portal", lambda a: Portal())
    monkeypatch.setattr(mp, "save_to_worker", lambda *a: True)
    got, _, notes = pipeline.fetch_account("MAIN", date(2026, 11, 15), tmp_path, 1)
    assert notes == [] and set(got) == set(pipeline.REPORTS)
    assert sorted(fresh_asks) == sorted(pipeline.REPORTS[k] for k in pipeline.RANGE_DAYS)
