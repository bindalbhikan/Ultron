"""Sale today: MYNTRA from the Seller API (open lines created today) + OMSGuru's cancelled units; OMSGuru is the
backup per account. Live check 23 Nov 2026: GROSS 118 both ways, Cancel 6."""
from collections import Counter
from datetime import date, datetime

from ultron.workings.portals import myntra_api
from ultron.workings.sale import pipeline

TODAY = date(2026, 11, 23)
NAMES = {"45111": "BINDAL EXPORTS LIMITED - MYNTRA", "47460": "BINDAL EXPORTS LIMITED - Myntra DressBerry CC",
         "37863": "BINDAL EXPORTS LIMITED - Flipkart", "99999": "BINDAL EXPORTS LIMITED - Myntra Other"}
UNITS = Counter({(TODAY, "45111"): 51, (TODAY, "47460"): 48, (TODAY, "37863"): 300, (TODAY, "99999"): 4})
CANCEL = Counter({(TODAY, "45111"): 3, (TODAY, "47460"): 2})


def _lines(n, day=TODAY):
    return [{"createdOn": datetime(day.year, day.month, day.day, 10), "quantity": 1} for _ in range(n)]


class _Api:
    def __init__(self, lines):
        self.lines = lines

    def open_lines(self, start, end):
        return self.lines


def test_the_api_counts_myntra_and_omsguru_adds_its_cancellations(monkeypatch):
    open_by = {"MAIN": _lines(48) + _lines(5, date(2026, 11, 22)), "DBCC": _lines(46)}
    monkeypatch.setattr(myntra_api.MyntraApi, "for_account", classmethod(lambda cls, acc, oms=None: _Api(open_by[acc])))
    notes = []
    gross, cancel = pipeline.myntra_live(None, TODAY, UNITS, CANCEL, NAMES, notes)
    assert (gross, cancel) == (48 + 3 + 46 + 2 + 4, 5)       # the channel with no API account counts OMSGuru's 4
    assert notes == ["Myntra BINDAL EXPORTS LIMITED - Myntra Other: OMSGuru (no Seller API account)"]


def test_an_account_whose_api_fails_counts_omsguru_and_is_named(monkeypatch):
    def for_account(cls, acc, oms=None):
        if acc == "DBCC":
            raise myntra_api.MyntraApiError("OMSGuru channel 47460 (DBCC) holds no Myntra API token")
        return _Api(_lines(48))
    monkeypatch.setattr(myntra_api.MyntraApi, "for_account", classmethod(for_account))
    notes = []
    gross, _ = pipeline.myntra_live(None, TODAY, UNITS, CANCEL, NAMES, notes)
    assert gross == 48 + 3 + 48 + 4
    assert any(n.startswith("Myntra DBCC: Seller API failed, OMSGuru used") for n in notes)


def test_a_difference_between_the_two_is_named(monkeypatch):
    monkeypatch.setattr(myntra_api.MyntraApi, "for_account", classmethod(lambda cls, acc, oms=None: _Api(_lines(50))))
    notes = []
    pipeline.myntra_live(None, TODAY, UNITS, CANCEL, NAMES, notes)
    assert "Myntra MAIN: Seller API 50 open, OMSGuru 48 (live orders since)" in notes


def test_new_oms_marketplace_is_listed_before_first_sale_and_counted_once():
    from collections import Counter
    from datetime import date
    from ultron.workings.sale.oms_sales import blocks_of, report_blocks
    from ultron.workings.sale.pipeline import today_report

    names = {"1": "Seller - LimeRoad", "2": "Second seller - LIMEROAD", "3": "Seller - Snapdeal"}
    assert report_blocks(names).count("LIMEROAD") == 1
    day = date(2026, 11, 27)
    units = Counter({(day, "1"): 2, (day, "2"): 3, (day, "3"): 8, (day, "unknown"): 4})
    gross, missing = blocks_of(units, names)
    assert gross == {(day, "LIMEROAD"): 5}
    assert missing == {"unknown": 4}
    assert "limeroad" in today_report({"LIMEROAD": 5}, {}, []).lower()
