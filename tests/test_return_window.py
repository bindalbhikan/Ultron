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
