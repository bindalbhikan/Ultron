"""Portal answers checked before any working reads them (docs/libraries/05-pydantic.md), in one place.

    check_rows(rows, MyntraJob, "Myntra report job")   the rows, unchanged; PortalChanged naming the field
                                                       when one came in another shape

Each model holds only the fields the workings read, checked first on real answers (counts in the docstring);
other fields are allowed. A model is the portal's contract: when a portal changes, the run stops with the field
named instead of reading on with empty or 0 values ("data must never be wrong").
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, ValidationError


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
