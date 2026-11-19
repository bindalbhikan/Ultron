"""A complete VMS run must publish Polars SLA dates, including orders without a scan."""
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

from ultron.workings.core.xlsx import write_sheets
from ultron.workings.vms import pipeline as P
from ultron.workings.vms.workbook import FIRST_ROW, VmsWorkbook


@pytest.mark.parametrize("scanned", [(True, True), (False, True), (False, False)])
def test_run_saves_and_publishes_orders_with_date_slas(tmp_path, monkeypatch, scanned):
    day = date(2026, 11, 19)
    path = tmp_path / "vms.xlsx"
    # An existing month sheet with its three header rows and one report day.
    write_sheets(path, {"NOV-26": (["November"], [["TLPL"], ["DATE"], [day]])})
    frame = pl.DataFrame({
        "SLA Date": pl.Series([day, day], dtype=pl.Date),
        "Code": ["TLPL", "TLPL"],
        "Myntra AWB": ["TEST-AWB-1", "TEST-AWB-2"],
        "In VMS": list(scanned),
    })
    monkeypatch.setattr(P, "report_dates", lambda args: [day])
    drive = SimpleNamespace(upload=Mock())
    monkeypatch.setattr(P, "open_book", lambda args: (drive, path))
    monkeypatch.setattr(P, "collect", lambda dates, cache: (frame, [], []))
    monkeypatch.setattr(P, "output_dir", lambda bot: tmp_path)
    send, publish = Mock(), Mock()
    monkeypatch.setattr(P.telegram, "send", send)
    monkeypatch.setattr(P.dashboard, "publish", publish)
    args = SimpleNamespace(snapshot=None, erp_only=False, only_no_vms=False,
                           no_erp=True, no_telegram=False)

    assert P.run(args) == 0

    drive.upload.assert_called_once_with(path)
    send.assert_called_once()
    publish.assert_called_once()
    key, payload = publish.call_args.args
    assert key == "vms"
    expected = [{"date": day, "code": "TLPL", "awb": f"TEST-AWB-{i}"}
                for i, in_vms in enumerate(scanned, 1) if not in_vms]
    assert payload["no_vms"] == expected
    # Exercise the same date serialization used by the dashboard HTTP publisher.
    encoded = json.loads(json.dumps(payload, default=P.dashboard._default))
    assert encoded["no_vms"] == [{**row, "date": day.isoformat()} for row in expected]
    assert encoded["days"] == [{"date": day.isoformat(), "codes": {
        "TLPL": [2, sum(scanned)], "MMRJ": [0, 0], "BOAT": [0, 0],
    }}]

    saved = VmsWorkbook(path)
    ws = saved.wb["NOV-26"]
    assert (ws.cell(FIRST_ROW, 2).value, ws.cell(FIRST_ROW, 3).value) == (2, sum(scanned))
    rows = list(saved.wb["NO VMS"].iter_rows(min_row=2, values_only=True))
    assert [(r[0].date(), r[1], r[2], r[3]) for r in rows] == [
        (day, "TLPL", r["awb"], "NO VMS") for r in expected
    ]
