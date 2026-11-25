"""AJIO TAT, owner 25 Nov 2026: an order cancelled after it was packed (OMSGuru Cancelled Return Received) is read
from OMSGuru again, leaves pickup pending, gets one pickup ticket at most and is never followed up or reported."""
from datetime import datetime, timedelta

import polars as pl

from ultron.workings.ajio_tat import pipeline


def _frame(now):
    t = now - timedelta(days=3)
    rows = [  # Order ID, Pickup Status, Process Status, Order Time, Pickup Time, RTS Time
        ("1", "Pending Pickup", "Late", t, None, t),                       # open, before the window
        ("2", "Cancelled", "Late", t, None, t),                            # cancelled after packing
        ("3", "On Time", "On Time", t, t, t),                              # picked
        ("4", "Pending Pickup", "Late", now - timedelta(days=40), None, t),  # too old
        ("5", "Cancelled", "Not Processed", t, None, None),                # cancelled before it was processed
        ("6", "Cancelled", "Late", t, None, None),                         # same-day cancel: processed, no RTS
    ]
    return pl.DataFrame(rows, orient="row", schema={
        "Order ID": pl.Utf8, "Pickup Status": pl.Utf8, "Process Status": pl.Utf8, "Order Time": pl.Datetime("us"),
        "Pickup Time": pl.Datetime("us"), "RTS Time": pl.Datetime("us")}).with_columns(
        pl.when(pl.col("Order ID") == "5").then(None).otherwise(pl.col("Order Time")).alias("Processed Time"),
        pl.lit("AWB").alias("AWB"), (pl.col("Order Time") + timedelta(days=1)).alias("Dispatch Deadline"))


def test_open_orders_before_the_window_are_read_again():
    now = datetime.now()
    assert pipeline.open_before(_frame(now), now - timedelta(days=1)) == ["1"]


def test_cancelled_after_packing_is_a_candidate_once_and_not_reported():
    now = datetime.now()
    cands = pipeline.pickup_ticket_candidates(_frame(now), now)
    assert cands.select("Order ID", "_cancelled").rows() == [("1", False), ("2", True), ("6", True)]
    pending = _frame(now).filter(pipeline.pickup_pending(now))["Order ID"].to_list()
    assert pending == ["1", "4"]
    done = [{"Order ID": "1", "Courier": "Delhivery", "Result": "created", "New": "T1", "Cancelled": False},
            {"Order ID": "2", "Courier": "Delhivery", "Result": "created", "New": "T1", "Cancelled": True}]
    head = pipeline.pickup_ticket_report([d for d in done if not d["Cancelled"]])[0]
    assert "1 orders" in head
