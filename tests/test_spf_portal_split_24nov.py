"""SPF masters, owner's rules of 24 Nov 2026: the portal decides the sheet (delivered sheet = only what the
portal marks delivered, in-transit sheet = the rest), RETURN MONTH is the delivery month on the delivered
sheet and the created month on the in-transit sheet, and a "Payment Received" return is still claimed."""
import datetime as dt

from openpyxl import Workbook

from ultron.workings.ajio_spf import master_engine as ae
from ultron.workings.myntra_spf import engine as me
from ultron.workings.myntra_spf import pipeline as mp
from ultron.workings.myntra_spf import tickets as mt

TODAY = dt.date(2026, 11, 24)


def _myntra(**kw):
    rec = {"order_line_id": "1", "model": "PPMP", "type": "Return", "return_tracking_number": "AWB",
           "return_created_date": dt.datetime(2026, 9, 20)}
    rec.update(kw)
    return rec


def test_myntra_sheet_follows_the_portal_only():
    # received in OMSGuru but the portal still says in transit: in-transit sheet
    assert me.is_in_transit(_myntra(status="Ret Created", **{"OMSGURU STATUS": "Return Received"}))
    # SPF paid, portal still in transit: in-transit sheet
    assert me.is_in_transit(_myntra(status="RTO Created", **{"SPF PAID": 500}))
    # no portal status at all: in-transit sheet
    assert me.is_in_transit(_myntra(status=None))
    # the portal says delivered: account sheet
    assert not me.is_in_transit(_myntra(status="Ret Delivered",
                                        deliver_to_seller_date=dt.datetime(2026, 10, 3)))
    assert not me.is_in_transit(_myntra(status="Delivered"))


def test_myntra_return_month_delivery_then_created():
    delivered = _myntra(status="Ret Delivered", deliver_to_seller_date=dt.datetime(2026, 10, 3))
    assert me.row_values(delivered, TODAY)["RETURN MONTH"] == "2026-10"
    transit = _myntra(status="Ret Created")
    assert me.row_values(transit, TODAY)["RETURN MONTH"] == "2026-09"
    f = me.build_formulas(5)["RETURN MONTH"]
    dlv, rcd = me.C["deliver_to_seller_date"] + "5", me.C["return_created_date"] + "5"
    assert f.startswith('=IF(%s<>"",TEXT(%s,"yyyy-mm")' % (dlv, dlv)) and rcd in f


def test_myntra_payment_received_is_still_claimed():
    paid = _myntra(status="Ret Created", return_created_date=dt.datetime(2026, 8, 20),
                   **{"ORDER SETTLEMENT": 899.0})
    assert mp.final_status(paid) == "Payment Received"
    assert not mp.resolved(paid)
    assert me.row_values(paid, TODAY)["CLAIM STATUS"] == "ELIGIBLE"        # 96 days, 60 to 120
    assert mp.claim_status(paid, 96) == "ELIGIBLE"
    assert mt.claim_of(paid, TODAY, set()) is not None
    assert 'AND({0}<>"",{0}<>"Payment Received")'.format(
        me.C["FINAL RETURN STATUS"] + "5") in me.build_formulas(5)["CLAIM STATUS"]
    # SPF paid or received: still no claim
    assert mp.resolved({**paid, "SPF PAID": 500})
    assert mt.claim_of({**paid, "OMSGURU STATUS": "Return Received"}, TODAY, set()) is None


def _ajio(**kw):
    rec = {"Return Created Date": dt.datetime(2026, 9, 20), "Return Status": "RETURN_CREATED"}
    rec.update(kw)
    return rec


def test_ajio_split_and_month():
    received_on_road = _ajio(**{"OMSGURU STATUS": "Return Received ERP"})
    assert not ae.delivered_to_us(received_on_road.get)
    assert ae.computed_values(received_on_road.get, TODAY)["RETURN MONTH"] == "2026-09"
    delivered = _ajio(**{"Return Status": "RETURN_DELIVERED", "Return Delivered Date": dt.datetime(2026, 10, 3)})
    assert ae.delivered_to_us(delivered.get)
    assert ae.computed_values(delivered.get, TODAY)["RETURN MONTH"] == "2026-10"
    # delivered by status, no delivered date: the challan date AGE counts from
    challan = _ajio(**{"Return Status": "RETURN_DELIVERED", "Delivery Challan Date": dt.datetime(2026, 11, 2)})
    assert ae.computed_values(challan.get, TODAY)["RETURN MONTH"] == "2026-11"


def test_ajio_summary_buckets_by_return_month():
    headers = [ae.SUMMARY_ACCOUNT_HEADER, "RETURN MONTH", "FINAL RETURN STATUS", "CLAIM STATUS", "CLAIM TYPE",
               "TICKET ID", ae.SUMMARY_AMOUNT_HEADER, "G4 PAYMENT", "IC REVERSE"]
    index = {h: i for i, h in enumerate(headers)}
    records = [["P1", None, None, None, None, None, 100.0, None, None],
               ["P1", None, None, None, None, None, 200.0, None, None]]
    worked = [{"RETURN MONTH": "2026-10", "FINAL RETURN STATUS": "", "CLAIM TYPE": "RETURN NOT RECEIVED"},
              {"RETURN MONTH": "2026-09", "FINAL RETURN STATUS": "", "CLAIM TYPE": "RETURN IN TRANSIT"}]
    wb = Workbook()
    _, values = ae.write_summary(wb, index, records, index, worked)
    ws = wb[ae.SUMMARY_SHEET]
    month_col = "$" + ae.get_column_letter(index["RETURN MONTH"] + 1)
    rows = {ws.cell(r, 2).value: r for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value == "P1"}
    assert values["C%d" % rows["2026-10"]] == 1 and values["C%d" % rows["2026-09"]] == 1
    assert month_col in ws.cell(rows["2026-10"], 3).value
