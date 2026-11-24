"""Queued report snapshots must be refreshed after another report used the wait budget."""
from types import SimpleNamespace

import pytest

from ultron.workings.portals import myntra as mp
from ultron.workings.myntra_reports.pipeline import account_rows


def test_wait_refreshes_completed_job_even_after_shared_deadline(monkeypatch):
    queued = {"id": 1, "status": "CREATED"}
    completed = {**queued, "status": "COMPLETED", "successFile": "report.csv"}
    portal = SimpleNamespace(jobs=lambda: [completed])
    monkeypatch.setattr(mp.time, "time", lambda: 101)
    assert mp.MyntraPortal._wait(portal, queued, 100, 30) == completed


def test_wait_still_fails_when_portal_job_is_pending_after_deadline(monkeypatch):
    queued = {"id": 1, "status": "CREATED"}
    portal = SimpleNamespace(jobs=lambda: [queued])
    monkeypatch.setattr(mp.time, "time", lambda: 101)
    with pytest.raises(RuntimeError, match="not ready in time"):
        mp.MyntraPortal._wait(portal, queued, 100, 30)


def test_wait_preserves_portal_failure_after_refresh(monkeypatch):
    queued = {"id": 1, "status": "CREATED"}
    portal = SimpleNamespace(jobs=lambda: [{**queued, "status": "INTERRUPTED"}])
    monkeypatch.setattr(mp.time, "time", lambda: 101)
    with pytest.raises(RuntimeError, match="INTERRUPTED"):
        mp.MyntraPortal._wait(portal, queued, 100, 30)


def test_deliveries_without_validated_orders_never_rewrite_workbook():
    with pytest.raises(RuntimeError, match="no validated orders"):
        account_rows("EXIM", {"Return Delivery": {"id": 84}})
