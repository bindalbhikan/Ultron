"""Myntra TAT: the SLA is Myntra's pack-by time from the Seller API, OMSGuru's (by AWB) when the API has none.
Live check 23 Nov 2026: 1,259 orders scored, 58 late both ways, every SLA equal."""
from datetime import date, datetime

import polars as pl

from ultron.workings.myntra_tat import pipeline as tat

NOW = datetime(2026, 11, 23, 18, 30)
REP = pl.DataFrame({
    "account": ["MAIN", "MAIN", "MAIN"], "awb": ["A1", "A2", "A3"], "courier": ["EK", "EK", "XB"],
    "status": ["C", "C", "C"], "so": ["s1", "s2", "s3"], "po": ["PPMP", "PPMP", "FBM"],
    "created": [datetime(2026, 11, 18, 10)] * 3, "packed": [datetime(2026, 11, 19, 9)] * 3,
    "pickup": [datetime(2026, 11, 19, 15), datetime(2026, 11, 20, 15), datetime(2026, 11, 19, 15)],
    "cancelled": pl.Series([None, None, None], dtype=pl.Datetime("us"))})
OMS = {"A1": datetime(2026, 11, 19, 12), "A2": datetime(2026, 11, 21, 12), "A3": datetime(2026, 11, 20, 12)}


def test_the_api_sla_wins_and_omsguru_fills_the_rest():
    api = {"s1": datetime(2026, 11, 20, 12), "s2": datetime(2026, 11, 19, 12)}   # s3 (FBM) not in the API
    df = tat.score(REP, OMS, date(2026, 11, 16), date(2026, 11, 21), NOW, api).sort("awb")
    assert df["sla"].to_list() == [api["s1"], api["s2"], OMS["A3"]]
    assert df["late"].to_list() == [False, True, False]


def test_without_the_api_omsguru_scores_as_before():
    df = tat.score(REP, OMS, date(2026, 11, 16), date(2026, 11, 21), NOW).sort("awb")
    assert df["sla"].to_list() == [OMS["A1"], OMS["A2"], OMS["A3"]]
    assert df["late"].to_list() == [True, False, False]
