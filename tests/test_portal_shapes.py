"""docs/libraries/05-pydantic.md: portal answers checked before any working reads them."""
import pytest

from ultron.workings.portals import myntra as mp

JOB = {"id": 7795614, "reportId": 84, "status": "COMPLETED", "createdOn": 1763270000000,
       "queryParams": {"storeId": "2297", "partnerType": "PPMP"}, "successFile": "https://x/a.csv",
       "statusMessage": "", "priority": 1}


def test_jobs_in_the_known_shape_come_back_unchanged():
    rows = [dict(JOB), {**JOB, "id": 1, "successFile": None, "status": "IN_PROGRESS"}]
    assert mp.checked_jobs(rows) is rows and rows[0] == JOB


def test_a_missing_or_renamed_field_is_named():
    bad = {k: v for k, v in JOB.items() if k != "status"} | {"jobStatus": "COMPLETED"}
    with pytest.raises(mp.PortalChanged, match=r"status \(missing\)"):
        mp.checked_jobs([JOB, bad])
    with pytest.raises(mp.PortalChanged, match=r"createdOn"):
        mp.checked_jobs([{**JOB, "createdOn": "yesterday"}])


def test_jobs_list_goes_through_the_check():
    p = mp.MyntraPortal.__new__(mp.MyntraPortal)
    p._call = lambda method, path, **kw: {"data": [{**JOB, "reportId": None}]}
    with pytest.raises(mp.PortalChanged, match="reportId"):
        p.jobs()
    p._call = lambda method, path, **kw: {"data": None}
    assert p.jobs() == []


PAYOUT = {"paymentMethod": "NEFT", "utrNumber": "UTR1", "paymentDate": "2026-11-10", "yearMonth": 202611,
          "amount": 1234.5, "utrDetailsLink": "https://x", "adviceId": None}


def test_payouts_checked_and_unchanged():
    from ultron.workings.core.shapes import MyntraPayout, PortalChanged, check_rows
    rows = [dict(PAYOUT), {**PAYOUT, "amount": 7}]
    assert check_rows(rows, MyntraPayout, "Myntra payout", key="utrNumber") is rows and rows[0] == PAYOUT
    with pytest.raises(PortalChanged, match=r"UTR1 came in another shape: amount"):
        check_rows([{**PAYOUT, "amount": "n/a"}], MyntraPayout, "Myntra payout", key="utrNumber")
    with pytest.raises(PortalChanged, match="paymentDate"):
        check_rows([{**PAYOUT, "paymentDate": "someday"}], MyntraPayout, "Myntra payout", key="utrNumber")


def test_payment_history_goes_through_the_check():
    from datetime import date
    p = mp.MyntraPortal.__new__(mp.MyntraPortal)
    p._call = lambda method, path, **kw: {"data": {"payments": [{**PAYOUT, "utrNumber": None}], "totalElements": 1}}
    with pytest.raises(mp.PortalChanged, match="utrNumber"):
        p.payment_history(date(2026, 11, 1), date(2026, 11, 10))


SRM = {"DOC_TYPE": "RV", "REF_DOC_NO_LONG": "R1", "VENDOR": "V1", "DOC_DATE": "05.11.2026", "DOC_NO": "D1",
       "EBELN": "P1", "FISC_YEAR": "2026", "amount": "-123.45", "due_date": "05.12.2026", "CLR_DOC_NO": "",
       "CLEAR_DATE": None, "ITEM_TEXT": "G4", "type": "Debit", "INV_REF": "I1"}


def test_srm_ledger_lines_checked():
    from ultron.workings.core.shapes import PortalChanged, SrmLedgerLine, check_rows
    assert check_rows([dict(SRM)], SrmLedgerLine, "SRM ledger line", key="DOC_NO")[0] == SRM
    with pytest.raises(PortalChanged, match="amount"):
        check_rows([{**SRM, "amount": "1,234.00"}], SrmLedgerLine, "SRM ledger line", key="DOC_NO")
    with pytest.raises(PortalChanged, match="DOC_DATE"):
        check_rows([{**SRM, "DOC_DATE": "2026-11-05"}], SrmLedgerLine, "SRM ledger line", key="DOC_NO")


FK = {"request_id": "abc", "report_group_name": "Fulfilment Reports", "report_name": "Orders", "created_at": 1763270000,
      "updated_at": 1763270100, "status": "FILE_STORED", "filters": [{"name": "date", "value": ["2026-10-01", "2026-10-31"]}]}


def test_flipkart_report_requests_checked():
    from ultron.workings.core.shapes import FlipkartReportRequest, PortalChanged, check_rows
    assert check_rows([dict(FK)], FlipkartReportRequest, "Flipkart report request", key="request_id")[0] == FK
    with pytest.raises(PortalChanged, match="created_at"):
        check_rows([{k: v for k, v in FK.items() if k != "created_at"}], FlipkartReportRequest, "Flipkart report request",
                   key="request_id")
