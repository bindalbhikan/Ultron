"""Return Analysis must preserve the canonical business report's returned units."""
from datetime import date

import pandas as pd
import pytest

from ultron.workings.business_report.workbook import Report
from ultron.workings.return_analysis.reconciled import template_rows


@pytest.mark.parametrize("portal,sku_col,id_col,value", [
    ("MYNTRA", "SELLER SKU CODE", "ORDER LINE ID", "FINAL AMOUNT"),
    ("FLIPKART", "SKU", "ORDER ITEM ID", "SALE VALUE"),
    ("AJIO", "SELLER SKU", "CUST ORDER NO", "SALE VALUE"),
])
def test_monthly_returns_preserve_units_and_exclude_other_order_months(portal, sku_col, id_col, value):
    # A two-unit order returned in part is already split by the shared builder. Counting rows,
    # or assigning the prior month's return to this month, would both give the wrong answer.
    raw = pd.DataFrame({
        "ORDER MONTH": pd.to_datetime(["2026-10-01"] * 6 + ["2026-09-01"]),
        "FINAL STATUS": ["Customer Return", "Delivered", "Customer Return", "RTO", "Cancelled", "In Transit", "Customer Return"],
        "QTY": [1, 1, 2, 3, 4, 5, 9],
        "ACCOUNT": ["MAIN"] * 7,
        sku_col: ["TEST-SKU"] * 7,
        id_col: ["partial", "partial", "returned", "rto", "cancelled", "transit", "prior-month"],
        "FINAL SKU": ["TEST-FINAL"] * 7, "MY SKU": ["TEST"] * 7,
        "BRAND": ["Test"] * 7, "CATEGORY": ["Top"] * 7,
        "REASON": ["Test reason"] * 7, value: [100, 100, 200, 300, 400, 500, 900],
    })
    rep = Report(portal=portal, raw=raw, raw_cols=list(raw), value=value)
    rows = template_rows(rep, date(2026, 10, 1), "MAIN" if portal == "MYNTRA" else "")
    assert rows.loc[rows["ORDER STATUS"] == "Return", "QTY"].sum() == 3
    assert rows["QTY"].sum() == 4
    assert set(rows["MONTH"]) == {"10-2026"}
    assert set(rows["ORDER ID"]) == {"partial", "returned"}


def test_missing_return_source_does_not_become_zero_returns():
    month = date(2026, 10, 1)
    rep = Report(portal="FLIPKART", raw=pd.DataFrame(), raw_cols=[], unknown={"tq": {pd.Timestamp(month)}})
    with pytest.raises(ValueError, match="return report is missing"):
        template_rows(rep, month)


def test_saved_reports_include_the_next_months_whole_return_sheet(monkeypatch, tmp_path):
    from ultron.workings.business_report import pipeline as business

    class Folder:
        http = object()

        def __init__(self, children):
            self.items = {name: {"id": key} for name, key in children.items()}

        def children(self):
            return self.items

        def subfolder(self, _name):
            return self

        def download(self, _name, dest):
            return dest

    folders = {
        "year": Folder({"Oct-26": "oct", "Nov-26": "nov"}),
        "oct": Folder({"FLIPKART ORDER REPORT OCT-26.xlsx": "order",
                       "FLIPKART RETURN REPORT OCT-26.xlsx": "return",
                       "FLIPKART PAYMENT REPORT OCT-26.xlsx": "payment"}),
        "nov": Folder({"FLIPKART RETURN REPORT NOV-26.xlsx": "tail",
                       "FLIPKART ORDER REPORT NOV-26.xlsx": "next-order"}),
    }
    monkeypatch.setattr(business, "agent_folder", lambda *_: Folder({"2026": "year"}))
    monkeypatch.setattr(business, "DriveFolder", lambda key, _http: folders[key])
    files = business.portal_files("FLIPKART", date(2026, 10, 1), date(2026, 10, 1), tmp_path,
                                  kinds={"ORDER", "RETURN"})
    assert {f["name"] for f in files} == {
        "FLIPKART ORDER REPORT OCT-26.xlsx", "FLIPKART RETURN REPORT OCT-26.xlsx", "FLIPKART RETURN REPORT NOV-26.xlsx"
    }


def test_yearly_report_revalidates_legacy_saved_months(monkeypatch, tmp_path):
    from ultron.workings.return_analysis import yearly

    class Folder:
        def subfolder(self, _name):
            return self

        def children(self):
            return {"AJIO OCT-26.csv": {}}

    raw = pd.DataFrame({
        "ORDER MONTH": pd.to_datetime(["2026-10-01"]), "FINAL STATUS": ["Customer Return"],
        "QTY": [2], "SELLER SKU": ["TEST-SKU"], "CUST ORDER NO": ["TEST-ORDER"],
        "FINAL SKU": ["TEST-FINAL"], "MY SKU": ["TEST"], "BRAND": ["Test"], "CATEGORY": ["Top"],
        "REASON": ["Test reason"], "SALE VALUE": [200],
    })
    rep = Report(portal="AJIO", raw=raw, raw_cols=list(raw), value="SALE VALUE")

    def render(frames, *_args):
        assert frames["AJIO"]["QTY"].sum() == 2
        return [{"portal": "AJIO", "returned": 2}]

    monkeypatch.setattr(yearly, "build_period", render)
    results = yearly.rebuild_year(Folder(), 2026, tmp_path, tmp_path, upload=False,
                                   context=(None, None, None, None), reports_by_portal={"AJIO": rep})
    assert results[0]["returned"] == 2
