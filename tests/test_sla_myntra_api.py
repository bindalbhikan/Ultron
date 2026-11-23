"""SLA warning: the Myntra accounts' lines from the Seller API (WP = OMSGuru's "New", SLA = packByTime), OMSGuru's
lines kept for an account whose API call fails. Live check 23 Nov 2026: 285 open lines both ways, every SLA equal."""
from datetime import date, datetime

from ultron.portals.omsguru_orders import at_risk
from ultron.workings.portals import myntra_api
from ultron.workings.sla import pipeline

NOW = datetime(2026, 11, 23, 15, 0)
OMS = [{"channel": "45111", "order": "old-main", "status": "New", "sla": datetime(2026, 11, 23, 12), "awb": ""},
       {"channel": "47460", "order": "dbcc-1", "status": "New", "sla": datetime(2026, 11, 23, 12), "awb": ""},
       {"channel": "37864", "order": "meesho-1", "status": "Pending", "sla": datetime(2026, 11, 23, 23, 59), "awb": ""}]


def _wp(so, pack_by, status="WP"):
    return {"sellerOrderId": so, "status_code": status, "packByTime": pack_by, "createdOn": datetime(2026, 11, 22, 9),
            "quantity": 1, "sku": "S", "lineFinalAmount": 500}


class _Api:
    def __init__(self, lines):
        self.lines = lines

    def open_lines(self, start, end, statuses=("WP",)):
        return [x for x in self.lines if x["status_code"] in statuses]


def test_myntra_lines_come_from_the_api_and_omsguru_stays_for_the_rest(monkeypatch):
    by = {"MAIN": [_wp("m-1", datetime(2026, 11, 23, 12)), _wp("m-2", datetime(2026, 11, 25, 12)),
                   _wp("m-3", datetime(2026, 11, 23, 12), "PK")],
          "DBCC": [], "FMCC": [], "EXIM": []}
    monkeypatch.setattr(myntra_api.MyntraApi, "for_account", classmethod(lambda cls, acc, oms=None: _Api(by[acc])))
    notes = []
    lines = pipeline.myntra_from_api(None, OMS, date(2026, 11, 16), NOW, notes)
    orders = {r["order"] for r in lines}
    assert orders == {"m-1", "m-2", "meesho-1"}          # OMSGuru's MAIN / DBCC lines replaced; PK is ready to ship
    assert [r["order"] for r in at_risk(lines, NOW)] == ["m-1", "meesho-1"]
    assert notes == []


def test_an_account_whose_api_fails_keeps_omsgurus_lines(monkeypatch):
    def for_account(cls, acc, oms=None):
        if acc == "DBCC":
            raise myntra_api.MyntraApiError("expired")
        return _Api([])
    monkeypatch.setattr(myntra_api.MyntraApi, "for_account", classmethod(for_account))
    notes = []
    lines = pipeline.myntra_from_api(None, OMS, date(2026, 11, 16), NOW, notes)
    assert {r["order"] for r in lines} == {"dbcc-1", "meesho-1"}
    assert notes == ["Myntra DBCC: Seller API failed, OMSGuru used (expired)"]
