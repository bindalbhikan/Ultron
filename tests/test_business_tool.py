"""tools/business.py: the agent's sale / return / GMV answers, with the business report's definitions."""
from datetime import date

import polars as pl
import pytest

from ultron.tools import business


def _facts():
    rows = [  # portal, order date, qty, value, status
        ("MYNTRA", date(2026, 10, 3), 1, 1000.0, "Delivered"),
        ("MYNTRA", date(2026, 10, 4), 1, 500.0, "Customer Return"),
        ("MYNTRA", date(2026, 10, 5), 2, 800.0, "RTO"),
        ("MYNTRA", date(2026, 10, 6), 1, 300.0, "Cancelled"),
        ("MYNTRA", date(2026, 9, 30), 1, 999.0, "Delivered"),          # outside October
        ("AJIO", date(2026, 10, 10), 3, 1500.0, "Delivered"),
    ]
    frame = pl.DataFrame(rows, schema=["PORTAL", "ORDER DATE", "QTY", "VALUE", "FINAL STATUS"], orient="row").with_columns(
        pl.col("ORDER DATE").dt.truncate("1mo").alias("ORDER MONTH"), pl.lit("Brand A").alias("BRAND"),
        pl.col("QTY").cast(pl.Float64))
    return {p: frame.filter(pl.col("PORTAL") == p) for p in ("MYNTRA", "AJIO")}, ["FLIPKART"]


def test_periods_in_plain_words():
    assert business.span("Oct-26") == (date(2026, 10, 1), date(2026, 10, 31))
    assert business.span("october 2026") == (date(2026, 10, 1), date(2026, 10, 31))
    assert business.span("2026-10") == (date(2026, 10, 1), date(2026, 10, 31))
    assert business.span("10/2026") == (date(2026, 10, 1), date(2026, 10, 31))
    assert business.span("2026-10-05 to 2026-10-20") == (date(2026, 10, 5), date(2026, 10, 20))
    with pytest.raises(ValueError):
        business.span("someday")


def test_portal_wise_numbers_follow_the_report(monkeypatch):
    monkeypatch.setattr(business, "_facts", _facts)
    text = business.business_numbers("Oct-26")
    myntra = next(line for line in text.splitlines() if line.startswith("MYNTRA"))
    cells = [c.strip() for c in myntra.split("|")]
    # gross 5 qty, GMV 2,600; cancelled 1; RTO 2 of dispatched 4 = 50%; return 1 of (1+1) = 50%; net 1 qty, 1,000
    assert cells == ["MYNTRA", "5", "2,600", "1", "2", "50.0%", "1", "50.0%", "500", "1", "1,000"]
    assert next(line for line in text.splitlines() if line.startswith("AJIO")).split("|")[1].strip() == "3"
    assert "Not included (no facts yet): FLIPKART" in text            # named, never counted as 0


def test_one_portal_and_by_month(monkeypatch):
    monkeypatch.setattr(business, "_facts", _facts)
    text = business.business_numbers("2026-09-01 to 2026-10-31", portal="myntra", by="month")
    assert "Sep-26 | 1 |" in text and "Oct-26 | 5 |" in text and "AJIO" not in text


def test_query_is_read_only_and_answers(monkeypatch):
    monkeypatch.setattr(business, "_facts", _facts)
    out = business.business_query('SELECT PORTAL, SUM(QTY) AS qty FROM facts GROUP BY PORTAL ORDER BY PORTAL')
    assert "AJIO" in out and "MYNTRA" in out
    assert business.business_query("DELETE FROM facts").startswith("Error")
    assert business.business_query("SELECT 1; SELECT 2").startswith("Error")
