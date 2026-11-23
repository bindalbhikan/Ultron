"""Myntra Seller API V4 as the live order source: the token borrowed from OMSGuru per account, open lines with
their order detail (customer data left out). Checked against live data on 23 Nov 2026: MAIN's open lines created
22 Nov = the portal report's open PPMP lines of that day (97 of 98; SJIT/FBM are not in the API)."""
import base64
import json
from datetime import date, datetime, timedelta

import pytest

from ultron.workings.portals import myntra_api as ma


def _jwt(exp: datetime) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"exp": int(exp.timestamp())}).encode()).decode().rstrip("=")
    return f"h.{body}.s"


class _Oms:
    def __init__(self, html):
        self.html, self.seen = html, []

    def get(self, url):
        self.seen.append(url)
        return type("R", (), {"text": self.html})()


def _page(value: str) -> str:
    return f'<form><textarea name="data[ChannelCompany][api_token]">{value}</textarea></form>'


def test_the_token_is_read_from_the_accounts_omsguru_channel():
    tok = _jwt(datetime.now() + timedelta(days=9))
    oms = _Oms(_page(json.dumps({"access_token": tok, "refresh_token": "r"})))
    assert ma.borrowed_token("FMCC", oms) == tok
    assert oms.seen == ["https://client.omsguru.com/channel_companies/edit/49234/1/1"]


def test_the_new_exim_account_has_its_channel():
    assert ma.channels()["EXIM"] == "64106"


def test_an_expired_or_missing_token_is_named(monkeypatch):
    old = _jwt(datetime.now() - timedelta(days=1))
    with pytest.raises(ma.MyntraApiError, match="expired"):
        ma.borrowed_token("MAIN", _Oms(_page(json.dumps({"access_token": old}))))
    with pytest.raises(ma.MyntraApiError, match="holds no"):
        ma.borrowed_token("MAIN", _Oms("<form></form>"))
    with pytest.raises(ma.MyntraApiError, match="no OMSGuru Myntra channel"):
        ma.borrowed_token("NOPE", _Oms(""))


def test_open_lines_read_each_order_once_without_customer_data(monkeypatch):
    api = ma.MyntraApi("t", "S")
    lists = {"WP": [{"orderLines": [{"sellerOrderId": "A"}]}],
             "PK": [{"orderLines": [{"sellerOrderId": "B"}, {"sellerOrderId": "A"}]}]}
    monkeypatch.setattr(api, "order_list", lambda st, s, e: iter(lists.get(st, [])))
    detail = {"data": {"mobile": "secret", "address": "secret", "orderLineEntries": [
        {"orderLineId": 1, "status_code": "WP", "createdOn": "22-11-2026 09:18:39", "packByTime": "25-11-2026 12:00:00",
         "sku": "SKU-1", "mrp": 1999, "lineFinalAmount": 565, "quantity": 1}]}}
    asked = []
    monkeypatch.setattr(api, "order", lambda so: asked.append(so) or detail)
    lines = api.open_lines(date(2026, 11, 22), date(2026, 11, 24), workers=1)
    assert asked == ["A", "B"]
    assert len(lines) == 2 and lines[0]["sellerOrderId"] == "A"
    assert lines[0]["createdOn"] == datetime(2026, 11, 22, 9, 18, 39)
    assert lines[0]["packByTime"] == datetime(2026, 11, 25, 12, 0)
    assert "mobile" not in lines[0] and "address" not in lines[0]


def test_api_time_reads_the_apis_shape():
    assert ma.api_time("01-12-2026 11:30:00") == datetime(2026, 12, 1, 11, 30)
    assert ma.api_time(None) is None and ma.api_time("2026-12-01") is None


def test_a_range_longer_than_7_days_is_asked_in_7_day_windows(monkeypatch):
    api = ma.MyntraApi("t", "S")
    asked = []
    monkeypatch.setattr(api, "order_list", lambda st, s, e: asked.append((st, s, e)) or iter([]))
    api.open_lines(date(2026, 11, 15), date(2026, 11, 24), statuses=("WP",), workers=1)
    assert asked == [("WP", date(2026, 11, 15), date(2026, 11, 22)), ("WP", date(2026, 11, 22), date(2026, 11, 24))]
