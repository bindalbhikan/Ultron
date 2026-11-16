"""docs/libraries/05-pydantic.md: portal answers checked before any working reads them."""
import pytest

from ultron.workings.portals import myntra as mp

JOB = {"id": 7795614, "reportId": 84, "status": "COMPLETED", "createdOn": 1763270000000,
       "queryParams": {"storeId": "2297", "partnerType": "PPMP"}, "successFile": "https://x/a.csv",
       "statusMessage": "", "priority": 1}


def test_jobs_in_the_known_shape_come_back_unchanged():
    rows = [dict(JOB), {**JOB, "id": 1, "successFile": None, "status": "IN_PROGRESS"}]
    assert mp.checked_jobs(rows) is rows and rows[0] == JOB


def test_a_missing_or_renamed_field_is_named():
    bad = {k: v for k, v in JOB.items() if k != "status"} | {"jobStatus": "COMPLETED"}
    with pytest.raises(mp.PortalChanged, match=r"status \(missing\)"):
        mp.checked_jobs([JOB, bad])
    with pytest.raises(mp.PortalChanged, match=r"createdOn"):
        mp.checked_jobs([{**JOB, "createdOn": "yesterday"}])


def test_jobs_list_goes_through_the_check():
    p = mp.MyntraPortal.__new__(mp.MyntraPortal)
    p._call = lambda method, path, **kw: {"data": [{**JOB, "reportId": None}]}
    with pytest.raises(mp.PortalChanged, match="reportId"):
        p.jobs()
    p._call = lambda method, path, **kw: {"data": None}
    assert p.jobs() == []
