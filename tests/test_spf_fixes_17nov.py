"""17 Nov 2026: a claim disputed once is not disputed again; Myntra's payment history is asked again on a 504."""
from datetime import date

import pytest

from ultron.workings.myntra_spf import tickets
from ultron.workings.portals import myntra as mp


class Portal:
    def __init__(self, claims):
        self.claims, self.disputed = claims, []

    def spf_claim(self, tid):
        return self.claims[tid]

    def spf_dispute(self, claim, text):
        self.disputed.append(claim["ticketId"])


def test_a_claim_disputed_once_is_named_not_disputed_again(monkeypatch):
    monkeypatch.setattr(tickets.time, "sleep", lambda s: None)
    p = Portal({1: {"ticketId": 1, "status": "REJECT", "fwTicketId": None},
                2: {"ticketId": 2, "status": "REJECT", "fwTicketId": 555},
                3: {"ticketId": 3, "status": "ACCEPT", "fwTicketId": None}})
    lines = tickets.open_disputes(p, "FMCC", [1, 2, 3], live=True)
    assert p.disputed == [1]
    assert lines[0] == "FMCC SPF disputes: 1 opened of 3 due"
    assert "1 rejected again after a dispute" in lines[1] and lines[1].endswith(": 2")


def test_payment_history_page_asked_again_on_a_504(monkeypatch):
    waits = []
    monkeypatch.setattr(mp.time, "sleep", waits.append)
    p = mp.MyntraPortal.__new__(mp.MyntraPortal)
    calls = []
    pay = {"paymentMethod": "NEFT", "utrNumber": "U1", "paymentDate": "2026-11-10", "yearMonth": 202611,
           "amount": 10.0, "utrDetailsLink": None, "adviceId": None}

    def call(method, path, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("Myntra portal /report/summary/payment-history: HTTP 200 Error: failed with status: 504")
        return {"data": {"payments": [pay], "totalElements": 1}}
    p._call = call
    assert p.payment_history(date(2026, 11, 1), date(2026, 11, 10)) == [pay]
    assert waits == [15]


def test_payment_history_other_error_not_asked_again(monkeypatch):
    monkeypatch.setattr(mp.time, "sleep", lambda s: None)
    p = mp.MyntraPortal.__new__(mp.MyntraPortal)
    calls = []

    def call(method, path, **kw):
        calls.append(1)
        raise RuntimeError("Myntra portal: HTTP 400 bad request")
    p._call = call
    with pytest.raises(RuntimeError):
        p.payment_history(date(2026, 11, 1), date(2026, 11, 10))
    assert len(calls) == 1
