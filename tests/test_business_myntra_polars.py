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
