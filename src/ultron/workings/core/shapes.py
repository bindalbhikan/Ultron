"""Portal answers checked before any working reads them (docs/libraries/05-pydantic.md), in one place.

    check_rows(rows, MyntraJob, "Myntra report job")   the rows, unchanged; PortalChanged naming the field
                                                       when one came in another shape

Each model holds only the fields the workings read, checked first on real answers (counts in the docstring);
other fields are allowed. A model is the portal's contract: when a portal changes, the run stops with the field
named instead of reading on with empty or 0 values ("data must never be wrong").
"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError


class PortalChanged(RuntimeError):
    """A portal answered in another shape than the workings read."""


class _Row(BaseModel):
    model_config = ConfigDict(extra="allow")


class MyntraJob(_Row):
    """/api/partners/report/jobs/search; all 4,914 jobs of MAIN, DBCC and FMCC fitted on 16 Nov 2026."""
    id: int
    reportId: int
    status: str
    createdOn: int
    queryParams: dict
    successFile: str | None = None
    statusMessage: str | None = None


class MyntraPayout(_Row):
    """/api/partners/report/summary/payment-history payments; all 1,320 payouts of the last 400 days of the
    three accounts fitted on 16 Nov 2026 (adviceId always empty there)."""
    utrNumber: str
    paymentDate: date
    amount: float
    yearMonth: int
    paymentMethod: str
    utrDetailsLink: str | None = None
    adviceId: str | int | None = None


class MyntraSpfTicket(_Row):
    """SPF /v2/getTickets; all 18,458 tickets of MAIN, DBCC and FMCC (whole history) fitted on 16 Nov 2026."""
    ticketId: int
    orderLineId: int
    orderId: int
    issueCategory: str
    status: str
    createdOn: str
    lastModifiedOn: str
    returnId: int | None = None


class MyntraSpfSjitTicket(_Row):
    """SPF /v2/getTickets?modelType=SJIT (the new SJIT claim tool, 25 Nov 2026): claims are per item (factCoreId,
    the SJIT returns report's core_item_id); no SJIT ticket was on the portal yet to fit, so only the ticket id
    is required."""
    ticketId: int
    factCoreId: str | None = None
    orderLineId: int | None = None
    orderId: int | None = None
    issueCategory: str | None = None
    status: str | None = None
    createdOn: str | None = None
    lastModifiedOn: str | None = None


_DOTTED_DATE = r"^\d{2}\.\d{2}\.\d{4}$"
_AMOUNT = r"^-?\d+(\.\d+)?$"


class SrmLedgerLine(_Row):
    """Reliance SRM statement of accounts (AJIO's ledger: G4 payments, IC reversals), T_ITEMS; all 11,337 lines of
    the last 150 days fitted on 16 Nov 2026: every field text, dates DD.MM.YYYY, amounts plain numbers."""
    DOC_TYPE: str
    REF_DOC_NO_LONG: str
    VENDOR: str
    DOC_DATE: Annotated[str, StringConstraints(pattern=_DOTTED_DATE)]
    DOC_NO: str
    EBELN: str
    FISC_YEAR: str
    amount: Annotated[str, StringConstraints(pattern=_AMOUNT)]
    due_date: str
    CLR_DOC_NO: str
    CLEAR_DATE: str | None = None
    ITEM_TEXT: str
    type: str
    INV_REF: str


class MyntraSpfClaim(_Row):
    """SPF /v2/fetchClaimByTicketId, one claim (disputes, replies, payments); 66 claims of every status of the three
    accounts (REJECT, ACCEPT, PAYMENT_COMPLETED, AWAITING_AGENT_RESPONSE) fitted on 16 Nov 2026."""
    status: str
    orderId: int
    eligibleForTagLoop: bool
    description: str | None = None
    validationReason: str | None = None
    history: str | None = None
    fwTicketId: int | None = None
    returnId: int | None = None
    utr: str | None = None
    compensationAmount: float | None = None
    paymentInitiatedOn: str | None = None
    returnDeliveredDate: str | None = None


class AjioTicket(_Row):
    """AJIO Seller Central castellan/api/v1/tickets list (SPF, pickup, follow-up tickets); all 1,131 tickets of the
    last 120 days fitted on 17 Nov 2026 (RESOLVED, IN_PROGRESS, CUSTOMER_REPLIED, APPROVED)."""
    ticketId: str
    status: str
    ticketType: str
    orderId: str
    subCategory: str | None = None
    createdDate: str
    lastUpdatedOn: str | None = None


class AjioTicketDetail(_Row):
    """AJIO castellan/api/v1/tickets/<id> result; 45 tickets of every status fitted on 17 Nov 2026."""
    ticketId: str
    status: str
    ticketType: str
    createdDate: str
    comments: list
    resolution: str | None = None
    resolvedDate: str | None = None
    subIssueType: str | None = None
    orderDetails: dict | None = None


class FlipkartReportRequest(_Row):
    """Seller Hub report centre report/getReportsV2 report_requests; all 172 requests listed on 16 Nov 2026
    fitted (the download name is request_id + created_at, so both must be there)."""
    request_id: str
    report_name: str
    created_at: int
    status: str
    filters: list[dict]


def check_rows(rows: list, model: type[BaseModel], what: str, key: str = "id") -> list:
    """rows unchanged, each checked against model; PortalChanged naming the row (its `key`) and the fields."""
    for row in rows:
        try:
            model.model_validate(row)
        except ValidationError as exc:
            fields = ", ".join(".".join(str(p) for p in e["loc"]) + f" ({e['type']})" for e in exc.errors())
            name = row.get(key) if isinstance(row, dict) else row
            raise PortalChanged(f"{what} {str(name)[:30]} came in another shape: {fields}") from None
    return rows
