"""Business report Myntra in Polars (docs/libraries/06-polars.md): the helpers' rules."""
from datetime import datetime

import polars as pl

from ultron.workings.business_report import myntra as m


def test_dates_in_the_three_iso_shapes_and_1970_dropped():
    s = pl.DataFrame({"d": ["2026-10-05", "2026-10-05 12:34:56", "2026-10-05 12:34:56.000", "1970-01-01", "", None, "x"]})
    got = s.select(m.pdt(pl.col("d")))["d"].to_list()
    assert got[:3] == [datetime(2026, 10, 5), datetime(2026, 10, 5, 12, 34, 56), datetime(2026, 10, 5, 12, 34, 56)]
    assert got[3:] == [None, None, None, None]


def test_commission_read_exactly_then_rounded_as_numpy():
    """16 Nov 2026: pandas read "13.145000000000001" as 13.145 and showed 13.14; the text rounds to 13.15."""
    s = pl.DataFrame({"c": ["13.145000000000001", "13.145", "2.675", "10"]})
    got = s.select(m.round2(m.pnum(pl.col("c"))))["c"].to_list()
    assert got == [13.15, 13.14, 2.68, 10.0]          # numpy's own results (the old reports): 13.145 -> 13.14, 2.675 -> 2.68


def test_ids_without_dot_zero_quote_or_nan():
    s = pl.DataFrame({"i": ["19170.0", "'12345", "nan", "None", None, "AB-1"]})
    assert s.select(m.pids(pl.col("i")))["i"].to_list() == ["19170", "12345", None, None, None, "AB-1"]


def test_rto_from_the_return_sheet_even_when_the_order_says_cancelled():
    """Owner, 17 Nov 2026: RTO / cancelled must match the return sheet (Myntra turns a returned RTO order to F)."""
    from ultron.workings.business_report.myntra import raw_data_pl
    text = lambda d: pl.DataFrame(d, schema={k: (pl.Int64 if k == "_order" else pl.Utf8) for k in d})  # noqa: E731
    o = text({"ACCOUNT": ["MAIN"] * 4, "order line id": ["1", "2", "3", "4"], "created on": ["2026-10-02"] * 4,
                      "order status": ["F", "F", "C", "C"], "store order id": ["s"] * 4, "order release id": ["r"] * 4,
                      **{c: [None] * 4 for c in ["style id", "myntra sku code", "seller sku code", "brand", "article type",
                                                  "size", "po_type", "total mrp", "discount", "final amount", "seller price",
                                                  "cancellation reason", "delivered on", "cancelled on", "rto creation date",
                                                  "courier code", "city", "state"]}})
    r = text({"order_line_id": ["1", "3"], "type": ["RTO", "Return"], "return_created_date": [None, "2026-10-20"],
                      "order_rto_date": ["2026-10-10", None], "_order": [0, 0],
                      **{c: [None] * 2 for c in ["exchange_id", "return_id", "order_id", "return_reason", "status", "refunded_date"]}})
    master = text({"Channel Name": ["MYNTRA"], "MYNTRA SKU CODE": ["x"], "Channel Listing SKU Code": ["x"],
                           **{c: ["v"] for c in m.MCOLS}})
    d = raw_data_pl(o, r, master, pl.DataFrame())
    got = dict(zip(d["ORDER LINE ID"].to_list(), zip(d["FINAL STATUS"].to_list(), d["SUB STATUS"].to_list())))
    assert got["1"] == ("RTO", "RTO (order report: cancelled)")
    assert got["2"] == ("Cancelled", "Cancelled before dispatch")
    assert got["3"][0] == "Customer Return" and got["4"][0] == "Delivered"
