"""Business report (owner, 16 Nov 2026): returns / RTO from the return sheet only, dated from the order month's 1st
to the next month's 14th."""
import pandas as pd

from ultron.workings.business_report import ajio, flipkart


def test_flipkart_window():
    returns = pd.DataFrame({"order_item_id": ["OI:1", "OI:2", "OI:3", "OI:4"],
                            "return_approval_date": ["2026-10-20", "2026-11-14 23:00:00", "2026-11-15", "2026-11-02"],
                            "return_status": ["completed", "completed", "completed", "cancelled"]})
    import polars as pl
    from datetime import datetime
    month = pl.DataFrame({"oi": ["1", "2", "3", "4"], "_om": [datetime(2026, 10, 1)] * 4})
    got = flipkart.windowed_returns(returns, month)
    assert got["oi"].to_list() == ["1", "2"]         # the 15th is out; a cancelled return is out


def test_ajio_window():
    rtv = pd.DataFrame({"Cust Order No": ["A", "B", "C"], "SELLER SKU": ["s", "s", "s"],
                        "Return Created Date": ["Wed Sep 30 23:21:44 IST 2026", "Sat Nov 14 10:00:00 IST 2026",
                                                "Sun Nov 15 10:00:00 IST 2026"]})
    import polars as pl
    from datetime import datetime
    month = pl.DataFrame({"key": ["A|s", "B|s", "C|s"], "_om": [datetime(2026, 10, 1)] * 3})
    got = ajio.windowed_rtv(rtv, month)
    assert got["Cust Order No"].to_list() == ["B"]   # before the order month and after the 14th are out


def test_months_without_their_return_reports_are_not_known():
    """A month's returns need its own and the next month's return report, per account with orders: else "-"."""
    from datetime import date

    from ultron.workings.business_report.pipeline import returns_not_known
    f = lambda kind, m, acc="": {"kind": kind, "month": m, "account": acc}  # noqa: E731
    files = [f("RETURN", date(2025, 7, 1)), f("RETURN", date(2025, 8, 1)), f("RETURN", date(2025, 9, 1))]
    months = {pd.Timestamp(2025, m, 1) for m in (6, 7, 8, 9)}
    assert returns_not_known(files, months) == {pd.Timestamp(2025, 6, 1), pd.Timestamp(2025, 9, 1)}
    my = [f("ORDER", date(2026, 10, 1), "MAIN"), f("ORDER", date(2026, 10, 1), "DBCC"),
          f("RETURN", date(2026, 10, 1), "MAIN"), f("RETURN", date(2026, 11, 1), "MAIN"), f("RETURN", date(2026, 10, 1), "DBCC")]
    assert returns_not_known(my, {pd.Timestamp(2026, 10, 1)}) == {pd.Timestamp(2026, 10, 1)}   # DBCC's Nov partial missing
    my.append(f("RETURN", date(2026, 11, 1), "DBCC"))
    assert returns_not_known(my, {pd.Timestamp(2026, 10, 1)}) == set()


def test_flipkart_raw_polars_small():
    """raw_data in Polars: status from the window, sale value from the Sales Report first, settlement summed."""
    orders = pd.DataFrame({"order_item_id": ["OI:1", "OI:2", "OI:3"], "order_id": ["A", "B", "C"],
                           "order_date": ["2026-10-02 10:00:00", "2026-10-03 11:00:00", "2026-10-04 12:00:00"],
                           "sku": ["X-TOP-1", "SKU:Y-DRESS-2", "Z"], "fsn": ["f"] * 3, "product_title": ['"T"'] * 3,
                           "quantity": ["1", "2", "1"], "fulfilment_type": ["x"] * 3,
                           "order_item_status": ["RETURNED", "DELIVERED", "CANCELLED"],
                           "return_reason": [None] * 3, "return_sub_reason": [None] * 3, "return_id": [None] * 3,
                           "order_cancellation_date": [None, None, "2026-10-05 00:00:00"], "dispatched_date": [None] * 3,
                           "order_delivery_date": [None] * 3, "dispatch_sla_breached": [None] * 3,
                           "pickup_logistics_partner": ["E", None, None], "delivery_logistics_partner": [None, "D", None]})
    returns = pd.DataFrame({"order_item_id": ["OI:2", "OI:2"], "return_approval_date": ["2026-10-20 00:00:00.5", "2026-11-20"],
                            "return_status": ["completed", "completed"], "return_type": ["courier_return", "customer_return"],
                            "return_id": ["R1", "R2"], "return_result": ["ok", "ok"], "return_reason": ["r", "r2"],
                            "return_sub_reason": ["s", "s2"], "quantity": ["2", "1"]})
    master = pd.DataFrame({"Channel Name": ["Flipkart"], "Channel Listing SKU Code": ["Y-DRESS-2"], "MY SKU": ["m"],
                           "FINAL SKU": ["f"], "FINAL MY SKU": ["fm"], "DESIGN-NO": ["D9"], "Brand": ["BR"]})
    settled = pd.DataFrame({"Order item ID": ["1", "1"], "NEFT ID": ["N1", "N2"], "Payment Date": ["2026-10-10", "2026-10-12"],
                            "Sale Amount (Rs.)": ["500", "0"], "Bank Settlement Value (Rs.)": ["300", "-10"]})
    raw = flipkart.raw_data(orders, returns, master, settled, {"D9": "Dresses"})
    by = raw.set_index("ORDER ITEM ID")
    assert by["FINAL STATUS"].to_dict() == {"1": "Delivered", "2": "RTO", "3": "Cancelled"}   # RETURNED without a line
    assert by.loc["2", "RETURN ID"] == "R1" and by.loc["2", "BRAND"] == "BR" and by.loc["2", "CATEGORY"] == "Dresses"
    assert by.loc["1", "CATEGORY"] == "Tops" and by.loc["3", "CATEGORY"] == "Not Mapped" and by.loc["1", "BRAND"] == "Not Mapped"
    assert by.loc["1", "NET SETTLEMENT"] == 290 and by.loc["1", "SALE VALUE"] == 500 and by.loc["1", "NEFT ID"] == "N2"
    assert by.loc["1", "PAYMENT STATUS"] == "Settled" and by.loc["2", "PAYMENT STATUS"] == "Not Applicable"
    assert by.loc["1", "COURIER"] == "E" and by.loc["2", "COURIER"] == "D" and by.loc["1", "PRODUCT TITLE"] == "T"
    assert flipkart.returned_units(raw, returns).tolist() == [0.0, 2.0, 0.0]
