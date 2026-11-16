"""Business report (owner, 16 Nov 2026): returns / RTO from the return sheet only, dated from the order month's 1st
to the next month's 14th."""
import pandas as pd

from ultron.workings.business_report import ajio, flipkart


def test_flipkart_window():
    returns = pd.DataFrame({"order_item_id": ["OI:1", "OI:2", "OI:3", "OI:4"],
                            "return_approval_date": ["2026-10-20", "2026-11-14 23:00:00", "2026-11-15", "2026-11-02"],
                            "return_status": ["completed", "completed", "completed", "cancelled"]})
    month = pd.Series([pd.Timestamp("2026-10-01")] * 4, index=["1", "2", "3", "4"])
    got = flipkart.windowed_returns(returns, month)
    assert got["oi"].tolist() == ["1", "2"]          # the 15th is out; a cancelled return is out


def test_ajio_window():
    rtv = pd.DataFrame({"Cust Order No": ["A", "B", "C"], "SELLER SKU": ["s", "s", "s"],
                        "Return Created Date": ["Wed Sep 30 23:21:44 IST 2026", "Sat Nov 14 10:00:00 IST 2026",
                                                "Sun Nov 15 10:00:00 IST 2026"]})
    month = pd.Series([pd.Timestamp("2026-10-01")] * 3, index=["A|s", "B|s", "C|s"])
    got = ajio.windowed_rtv(rtv, month)
    assert got["Cust Order No"].tolist() == ["B"]    # before the order month and after the 14th are out
