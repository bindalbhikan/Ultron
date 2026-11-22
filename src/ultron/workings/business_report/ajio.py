"""AJIO sale / return analysis (business reporting): the Myntra layout (workbook.py) from the AJIO
reports kept in PORTAL REPORTS.

  ORDER REPORT    Dropship order report: one row per order line (Cust Order No + Seller SKU), status,
                  Selling Price (what the customer paid), Invoice Value (what AJIO pays us)
  RETURN REPORT   Dropship RTV report: one row per return line; RVP / REPL / SELF_SHIP and
                  SELF_SHIP_WITHOUT_SHIPPING_CHARGE =
                  customer return (REPL = exchange, counted as a return as on Myntra), RTO = RTO
  PAYMENT REPORT  SRM statement of accounts (the AJIO ledger; owner's rule, 2 Nov 2026): G4 = payment
                  received for an invoice (REFERENCE = the Seller Invoice No), IC = a payment reversed for a
                  return (INVOICE REFERENCE NUMBER = the DOCNO of that invoice's G4), the rest (bank
                  clearing, TOT, ads, holds) are neither received nor reversed money of an order line

  MONTHLY REPORT  the owner's monthly file (sheet SALE, Oct-25 to Jan-26): the order report's lines less the cancelled
                  ones and without Description, carrier or SLA (price and invoice value the same as the order report
                  on all 626 + 838 lines both have, Dec-25 and Jan-26). It adds the lines the order report does not
                  have (SOURCE = Monthly file).
  OMSGURU REPORT  business_report/oms.py: the status of each line, and the lines of days no order report or monthly file reaches
                  (SOURCE = OMSGuru: order id, SKU, qty, status, its value as INVOICE VALUE, no selling price)

FINAL STATUS: Customer Return / RTO from the RTV line (return qty > 0), Cancelled (status Cancelled),
Delivered (status Delivered, no return; or Shipped over SHIPPED_DAYS ago with no return: a report's status is as
old as its file), In Transit (Shipped lately and the rest).
SALE VALUE = Selling Price x qty; NET SETTLEMENT = G4 received less IC reversed (sign turned so money
to us is positive), both matched by invoice number. An invoice can hold several order lines: G4 is shared
by invoice value, IC by the credit note value of the invoice's returned lines, so no rupee counts twice.
BRAND from the order report; CATEGORY = the article type Myntra lists the same design under (MasterSheet
channel AJIO for the design), else the order's Description.
"""
from __future__ import annotations

import logging
from pathlib import Path

from typing import TYPE_CHECKING

from datetime import datetime

from .workbook import Report

if TYPE_CHECKING:
    import polars as pl

log = logging.getLogger("bindal.business_report")
AJIO_FMT = "%a %b %d %H:%M:%S %Y"
CUSTOMER = {"RVP", "REPL", "SELF_SHIP", "SELF_SHIP_WITHOUT_SHIPPING_CHARGE"}
SHIPPED_DAYS = 60


from ..core.tables import pnum  # noqa: E402 - one number reader (docs/CENTRALISE.md)

def read(files: list[Path]) -> "pl.DataFrame":
    """Every file's first sheet as one Polars text table (`_file` = the file's name)."""
    import polars as pl

    from ..core.tables import read_excel_text
    # openpyxl engine: AJIO's texts keep their outer spaces, as pandas read them (core/tables.read_excel_text)
    frames = [read_excel_text(f, 0, engine="openpyxl").with_columns(_file=pl.lit(f.name)) for f in files]
    frames = [f for f in frames if f.height]
    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


MONTHLY_COLUMNS = {"cust order no": "Cust Order No", "fwd seller order no": "FWD Seller Order NO", "seller invoice no": "Seller Invoice No",
                   "status": "Status", "jiocode": "JioCode", "seller style code": "Seller Style Code", "seller sku": "Seller SKU",
                   "shipped qty": "Order Qty", "listing mrp": "Listing MRP", "selling price": "Selling Price",
                   "invoice value": "Invoice Value", "brand": "Brand", "fulfillment type": "Fulfillment Type"}


def read_monthly(files: list[Path]) -> "pl.DataFrame":
    """The SALE sheet of the owner's monthly files in the order report's columns; a later file's line wins (Polars)."""
    import polars as pl

    from ..core.tables import pany_date, read_excel_text, sheet_names, unread_dates
    frames = []
    for f in files:                                                  # in month order
        sheet = next(s for s in sheet_names(f) if s.strip().lower() == "sale")
        df = read_excel_text(f, sheet, engine="openpyxl")             # outer spaces kept, as pandas read them
        df = df.rename({c: " ".join(str(c).split()).lower() for c in df.columns})
        df = df.with_columns(_day=pany_date(pl.col("cust order date")))
        unread_dates(df.filter(pl.col("cust order no").is_not_null()), "cust order date", "_day", f.name, log)
        df = df.filter(pl.col("cust order no").is_not_null() & pl.col("_day").is_not_null())     # no total row
        frames.append(df.select(*[(pl.col(c) if c in df.columns else pl.lit(None, dtype=pl.Utf8)).alias(name)
                                  for c, name in MONTHLY_COLUMNS.items()],
                                pl.col("_day").dt.strftime(AJIO_FMT).alias("Cust Order Date"), pl.lit(f.name).alias("_file")))
    if not frames:
        return pl.DataFrame()
    m = pl.concat(frames, how="diagonal_relaxed").with_columns(_key=_key("Cust Order No", "Seller SKU"))
    return m.unique("_key", keep="last", maintain_order=True).drop("_key")


def forward_values(rtv) -> "pl.DataFrame":
    """The return lines with qty, once each: key = order line, fwd = FWD B2B Invoice Amt (what a return takes back in the
    owner's monthly files), created = Return Created Date."""
    import polars as pl
    r = _frame(rtv)
    if not r.height:
        return pl.DataFrame(schema={"key": pl.Utf8, "fwd": pl.Float64, "created": pl.Datetime("us")})
    r = (r.filter(pnum(pl.col("Return QTY")).fill_null(0) > 0)
          .unique(["RETURN ORDER NUMBER", "SELLER SKU"], keep="last", maintain_order=True))
    return r.select(_key("Cust Order No", "SELLER SKU").alias("key"), pnum(pl.col("FWD B2B Invoice Amt")).fill_null(0).alias("fwd"),
                    padate(pl.col("Return Created Date")).alias("created"))


def _line_key() -> "pl.Expr":
    """The order line of a RAW DATA row: "CUST ORDER NO|SELLER SKU" (an empty part is the text "nan", as the old code had it)."""
    return _text("CUST ORDER NO") + "|" + _text("SELLER SKU")


def file_payment(raw: "pl.DataFrame", rtv, months: set) -> "pl.DataFrame":
    """The payment of order months the SRM ledger does not reach, worked out as the owner's monthly files do: the line's
    Invoice Value received, less FWD B2B Invoice Amt of its returns. A statement of what is due, not of the bank."""
    import polars as pl
    fwd = forward_values(rtv)
    by_line = fwd.filter(pl.col("key").is_not_null()).group_by("key").agg(_fwd=pl.col("fwd").sum())
    month = pl.col("ORDER MONTH").is_in(list(months)).fill_null(False)
    hit = month & (pl.col("FINAL STATUS") != "Cancelled").fill_null(True)
    x = raw.with_columns(_k=_line_key()).join(by_line, left_on="_k", right_on="key", how="left", maintain_order="left")
    debit = -pl.col("_fwd").fill_null(0)
    oms_line = hit & (pl.col("SOURCE") == "OMSGuru").fill_null(False)    # no order report: OMSGuru's value, nothing kept on a return
    value = pl.col("INVOICE VALUE")
    return x.with_columns(
        pl.when(hit).then(value).when(month).then(None).otherwise(pl.col("INVOICE PAID")).alias("INVOICE PAID"),
        pl.when(hit).then(pl.when(debit != 0).then(debit)).when(month).then(None).otherwise(pl.col("CREDIT NOTE DEBIT"))
          .alias("CREDIT NOTE DEBIT"),
        pl.when(oms_line).then(pl.when(pl.col("FINAL STATUS") == "Delivered").then(value).otherwise(0.0))
          .when(hit).then(value.fill_null(0) + debit).when(month).then(None).otherwise(pl.col("NET SETTLEMENT")).alias("NET SETTLEMENT"),
        pl.when(month).then(None).otherwise(pl.col("PAYMENT DATE")).alias("PAYMENT DATE"),
        pl.when(oms_line).then(pl.lit("As per OMSGuru")).when(hit).then(pl.lit("As per monthly file"))
          .when(month).then(pl.lit("Not Applicable")).otherwise(pl.col("PAYMENT STATUS")).alias("PAYMENT STATUS"),
    ).drop("_k", "_fwd")


def monthly_expenses(files: list[tuple[Path, datetime]]) -> dict:
    """Month -> the charges on the EXP sheet of the owner's monthly file (money off, so negative)."""
    import polars as pl

    from ..core.tables import read_excel_text, sheet_names
    out = {}
    for f, month in files:
        sheet = next((s for s in sheet_names(f) if s.strip().lower().startswith("exp")), None)
        if not sheet:
            continue
        e = read_excel_text(f, sheet, engine="openpyxl")
        e = e.rename({c: str(c).strip().upper() for c in e.columns})
        if "AMOUNT" in e.columns:
            out[month] = -abs(float(e.select(pnum(pl.col("AMOUNT")).sum())[0, 0] or 0.0))
    return out


def file_payment_months(raw: "pl.DataFrame", rtv, months: set, charges: dict | None = None) -> "pl.DataFrame":
    """Those months in the cash table (first column `m`): Invoice Value of the month's orders, FWD B2B Invoice Amt of the
    month's returns, the charges of the file's EXP sheet."""
    import polars as pl
    t = (raw.filter(pl.col("ORDER MONTH").is_in(list(months)).fill_null(False))
            .group_by("ORDER MONTH").agg(pl.col("INVOICE PAID").fill_nan(None).sum().alias("Received (G4)"))
            .rename({"ORDER MONTH": "m"}).sort("m"))
    fwd = forward_values(rtv).with_columns(m=pl.col("created").dt.truncate("1mo"))
    rev = fwd.filter(pl.col("m").is_in(list(months)).fill_null(False)).group_by("m").agg(_r=pl.col("fwd").sum())
    exp = pl.DataFrame({"m": list((charges or {}).keys()), "_e": list((charges or {}).values())},
                       schema={"m": pl.Datetime("us"), "_e": pl.Float64})
    return (t.with_columns(pl.col("m").cast(pl.Datetime("us")))
             .join(rev, on="m", how="left", maintain_order="left").join(exp, on="m", how="left", maintain_order="left")
             .select("m", "Received (G4)", (-pl.col("_r").fill_null(0)).alias("Reversed (IC)"),
                     pl.col("_e").fill_null(0).alias("Other (EXP sheet)")))


def payment_match(raw: "pl.DataFrame", ledger_, table: "pl.DataFrame") -> list[tuple[str, float]]:
    """From the bank (KP) to NET SETTLEMENT in RAW DATA, step by step: every rupee named."""
    import polars as pl
    lg = ledger(ledger_)
    both = pl.col("DT").is_in(["G4", "IC"])
    total = lambda df, c: float(df.select(pl.col(c).cast(pl.Float64).fill_nan(None).sum()).item() or 0.0)  # noqa: E731
    paid = total(table, "Bank Paid (KP)")
    cleared_unpaid = total(table, "Difference")
    charges = total(lg.filter(pl.col("paid").is_not_null() & ~both & (pl.col("DT") != "KP").fill_null(True)), "amt")
    open_lines = total(lg.filter(pl.col("paid").is_null() & both), "amt")
    whole = total(lg.filter(both), "amt")
    file_lines = total(raw.filter(pl.col("PAYMENT STATUS") == "As per monthly file"), "NET SETTLEMENT")
    on_lines = total(raw, "NET SETTLEMENT")
    return [("Bank paid (KP), all months", paid),
            ("Cleared in the ledger, bank payment still to come", cleared_unpaid),
            ("Add back: charges in the ledger, no order line (TOT, GST retention, other)", -charges),
            ("Not cleared yet in the ledger (G4 + IC)", open_lines),
            ("= G4 + IC, the whole ledger", whole),
            ("Order months before the ledger: as per the monthly files", file_lines),
            ("G4 + IC of those months' invoices, already in the line above", on_lines - file_lines - whole),
            ("= NET SETTLEMENT in RAW DATA = Net Received in MONTH WISE", on_lines)]


# ------------------------------------------------------------------ Polars (docs/libraries/06-polars.md)
def _pl():
    import polars as pl
    return pl


def padate(e: "pl.Expr") -> "pl.Expr":
    """adate() in Polars: AJIO's "Wed Sep 30 23:21:44 IST 2026" as a datetime; anything else -> null."""
    pl = _pl()
    return e.cast(pl.Utf8).str.replace(" IST", "", literal=True).str.to_datetime(AJIO_FMT, strict=False, time_unit="us")


def _frame(df) -> "pl.DataFrame":
    from ..core.tables import to_polars
    pl = _pl()
    return pl.DataFrame() if df is None else to_polars(df)


def _key(order: str, sku: str) -> "pl.Expr":
    """The order line: "Cust Order No|Seller SKU" (empty when either is)."""
    pl = _pl()
    return pl.col(order).str.strip_chars() + "|" + pl.col(sku).str.strip_chars()


def _text(c: str) -> "pl.Expr":
    """pandas' astype(str).str.strip(): an empty cell is the text "nan" (as the old code matched it)."""
    pl = _pl()
    return pl.col(c).cast(pl.Utf8).fill_null("nan").str.strip_chars()


def windowed_rtv(rtv, month_of_key: "pl.DataFrame") -> "pl.DataFrame":
    """The RTV (return sheet) lines dated (Return Created Date) from their order line's order month's 1st to the next
    month's 14th (owner, 16 Nov 2026: a month's returns and RTO come from the return sheet, within that window).
    month_of_key: `key` ("Cust Order No|Seller SKU") -> `_om` (order month). A line of no known order line is left out.
    The lines keep their columns plus `key` and `created`."""
    pl = _pl()
    r = _frame(rtv)
    if not r.height:
        return r
    om = month_of_key.unique("key", keep="last", maintain_order=True)
    return (r.with_columns(key=_key("Cust Order No", "SELLER SKU"), created=padate(pl.col("Return Created Date")))
             .join(om, on="key", how="inner", maintain_order="left")
             .filter((pl.col("created") >= pl.col("_om")) & (pl.col("created") < pl.col("_om").dt.offset_by("1mo").dt.offset_by("14d")))
             .drop("_om"))


def credit_notes(rtv: "pl.DataFrame") -> "pl.DataFrame":
    """Order line `key` -> `note`: the credit note value of its return lines (which line of an invoice an IC is for)."""
    pl = _pl()
    if not rtv.height:
        return pl.DataFrame({"key": [], "note": []}, schema={"key": pl.Utf8, "note": pl.Float64})
    lines = rtv.unique(["RETURN ORDER NUMBER", "SELLER SKU"], keep="last", maintain_order=True)
    return (lines.filter(pl.col("key").is_not_null())
                 .group_by("key").agg(note=pnum(pl.col("Credit Note Value")).fill_null(0).clip(lower_bound=0).sum()))


def ledger(ledger_) -> "pl.DataFrame":
    """ledger_lines() in Polars: the ledger's lines once each; amt: money to us is positive; paid: the clearing date."""
    pl = _pl()
    lg = _frame(ledger_)
    return (lg.with_columns(amt=-pnum(pl.col("AMOUNT")).fill_null(0),
                            paid=pl.col("CLEARINGDOCUMENTDATE").str.strip_chars().str.to_datetime("%d.%m.%Y", strict=False, time_unit="us"))
              .unique(["DT", "REFERENCE", "DOCNO", "AMOUNT"], keep="first", maintain_order=True))


def raw_data(orders, rtv, ledger_, master, category_of_design: dict[str, str] | None = None, monthly=None) -> "pl.DataFrame":
    """One row per order line (order report, then lines only the owner's monthly files have) with its final status,
    return and payment (G4 / IC by invoice)."""
    pl = _pl()
    o = (_frame(orders).with_columns(key=_key("Cust Order No", "Seller SKU"))
         .unique("key", keep="last", maintain_order=True).with_columns(_source=pl.lit("Order report")))
    m = _frame(monthly)
    if m.height:                                                     # lines only the owner's monthly files have
        extra = m.with_columns(key=_key("Cust Order No", "Seller SKU"))
        extra = extra.filter(~pl.col("key").is_in(o["key"].implode(), nulls_equal=True))
        # the same design's Description from the order report
        names = (o.drop_nulls(["Seller Style Code", "Description"]).unique("Seller Style Code", keep="first", maintain_order=True)
                  .select("Seller Style Code", pl.col("Description").alias("_desc")))
        extra = (extra.drop("Description", strict=False).join(names, on="Seller Style Code", how="left", maintain_order="left")
                      .rename({"_desc": "Description"}).with_columns(_source=pl.lit("Monthly file")))
        o = pl.concat([o, extra], how="diagonal_relaxed")
    for c in ["Brand", "Description", "FWD Carrier", "FWD Shipment Date", "SLA Status", "Fulfillment Type", "Listing MRP",
              "Selling Price", "Invoice Value", "Order Qty", "JioCode", "Seller Style Code", "Seller Invoice No", "FWD Seller Order NO"]:
        if c not in o.columns:
            o = o.with_columns(pl.lit(None, dtype=pl.Utf8).alias(c))
    o = o.with_row_index("_row")

    r_all = windowed_rtv(rtv, o.select("key", _om=padate(pl.col("Cust Order Date")).dt.truncate("1mo")))
    if r_all.height:
        # one return per order line: an RTO first, then one with qty, then the latest
        r = (r_all.with_columns(qty=pnum(pl.col("Return QTY")).fill_null(0), is_rto=pl.col("Return Type") == "RTO")
                  .sort(["key", "is_rto", "qty", "created"], descending=[False, True, True, True], nulls_last=True, maintain_order=True)
                  .unique("key", keep="first", maintain_order=True)
                  .select("key", *[pl.col(c).alias(f"r.{c}") for c in ["Return Type", "qty", "created", "Cust Return Reason",
                                                                         "RETURN ORDER NUMBER", "Return Status", "Credit Note Number"]]))
    else:
        r = pl.DataFrame({"key": []}, schema={"key": pl.Utf8}).with_columns(
            *[pl.lit(None, dtype=pl.Utf8).alias(f"r.{c}") for c in ["Return Type", "Cust Return Reason", "RETURN ORDER NUMBER",
                                                                    "Return Status", "Credit Note Number"]],
            pl.lit(None, dtype=pl.Float64).alias("r.qty"), pl.lit(None, dtype=pl.Datetime("us")).alias("r.created"))

    am = (_frame(master).filter(pl.col("Channel Name").str.to_uppercase().str.starts_with("AJIO"))
          .unique("Channel Listing SKU Code", keep="first", maintain_order=True)
          .select(pl.col("Channel Listing SKU Code").alias("_sku"),
                  *[pl.col(c).alias(f"m.{c}") for c in ["MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO", "Brand"]]))
    x = (o.with_columns(_sku=pl.col("Seller SKU").str.strip_chars())
          .join(am, on="_sku", how="left", maintain_order="left")
          .join(r, on="key", how="left", maintain_order="left"))
    titles = {d: d.title() for d in x["Description"].drop_nulls().unique().to_list()}   # pandas' str.title exactly
    cats = category_of_design or {}
    day = padate(pl.col("Cust Order Date")).dt.truncate("1d")
    today = datetime.combine(datetime.today().date(), datetime.min.time())
    st0 = pl.col("Status").str.strip_chars().str.to_lowercase()
    # a status is as old as its file (the order report of a month is saved once): Shipped long ago with no RTV line since was delivered
    stale = ((pl.lit(today) - day).dt.total_days() > SHIPPED_DAYS).fill_null(False) & (st0 == "shipped").fill_null(False)
    st = pl.when(stale).then(pl.lit("delivered")).otherwise(st0)
    rtype, rqty = pl.col("r.Return Type"), pl.col("r.qty").fill_null(0)
    final = (pl.when(rtype == "RTO").then(pl.lit("RTO"))
               .when(rtype.is_in(sorted(CUSTOMER)) & (rqty > 0)).then(pl.lit("Customer Return"))
               .when(st == "cancelled").then(pl.lit("Cancelled"))
               .when(st == "delivered").then(pl.lit("Delivered"))
               .otherwise(pl.lit("In Transit")))
    x = x.with_columns(_final=final, _stale=stale, _qty=pnum(pl.col("Order Qty")).fill_null(1), _sp=pnum(pl.col("Selling Price")))
    ret = pl.col("_final").is_in(["Customer Return", "RTO"])
    d = x.select(
        day.alias("ORDER DATE"), day.dt.truncate("1mo").alias("ORDER MONTH"),
        pl.col("Cust Order No").alias("CUST ORDER NO"), pl.col("FWD Seller Order NO").alias("SELLER ORDER NO"),
        pl.col("Seller Invoice No").alias("SELLER INVOICE NO"), pl.col("JioCode").alias("JIOCODE"),
        pl.col("Seller Style Code").alias("SELLER STYLE CODE"), pl.col("_sku").alias("SELLER SKU"),
        *[pl.col(f"m.{c}").alias(c) for c in ["MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO"]],
        pl.coalesce(pl.col("Brand"), pl.col("m.Brand"), pl.lit("Not Mapped")).alias("BRAND"),
        pl.coalesce(pl.col("m.DESIGN-NO").replace_strict(cats, default=None, return_dtype=pl.Utf8) if cats else pl.lit(None, dtype=pl.Utf8),
                    pl.col("Description").replace_strict(titles, default=None, return_dtype=pl.Utf8) if titles else pl.lit(None, dtype=pl.Utf8),
                    pl.lit("Not Mapped")).alias("CATEGORY"),
        pl.col("Description").alias("DESCRIPTION"), pl.col("_qty").alias("QTY"), pnum(pl.col("Listing MRP")).alias("MRP"),
        pl.col("_sp").alias("SELLING PRICE"), (pl.col("_sp") * pl.col("_qty")).alias("SALE VALUE"),
        pnum(pl.col("Invoice Value")).alias("INVOICE VALUE"), pl.col("Fulfillment Type").alias("FULFILLMENT TYPE"),
        pl.col("Status").alias("PORTAL ORDER STATUS"), pl.col("_source").alias("SOURCE"), pl.col("_stale").alias("STALE SHIPPED"),
        pl.col("_final").alias("FINAL STATUS"), rtype.alias("RETURN TYPE"),
        pl.when(ret).then(pl.col("r.Cust Return Reason").fill_null("")).otherwise(pl.lit("")).alias("REASON"),
        pl.col("r.RETURN ORDER NUMBER").alias("RETURN ORDER NUMBER"), pl.col("r.Return Status").alias("RETURN STATUS"),
        pl.col("r.created").dt.truncate("1d").alias("RETURN CREATED DATE"),
        pl.col("r.created").dt.truncate("1d").dt.truncate("1mo").alias("RETURN MONTH"),
        pl.col("r.Credit Note Number").alias("CREDIT NOTE NUMBER"), pl.col("FWD Carrier").alias("COURIER"),
        padate(pl.col("FWD Shipment Date")).dt.truncate("1d").alias("SHIPMENT DATE"), pl.col("SLA Status").alias("SLA STATUS"),
        "key", "_row",
    )
    # payments by invoice number: G4 received (REFERENCE), IC reversed (through the DOCNO of the G4)
    lg = ledger(ledger_) if ledger_ is not None and len(ledger_) else None
    if lg is not None:
        lg = lg.with_columns(*[_text(c).alias(c) for c in ("REFERENCE", "DOCNO", "INVOICE REFERENCE NUMBER")])
        received, ic = lg.filter(pl.col("DT") == "G4"), lg.filter(pl.col("DT") == "IC")
        g4 = received.group_by("REFERENCE").agg(g_amt=pl.col("amt").sum(), g_paid=pl.col("paid").max()).rename({"REFERENCE": "_inv"})
        invoice_of = received.unique("DOCNO", keep="first", maintain_order=True).select(
            pl.col("DOCNO").alias("INVOICE REFERENCE NUMBER"), pl.col("REFERENCE").alias("_inv"))
        reversed_ = (ic.join(invoice_of, on="INVOICE REFERENCE NUMBER", how="inner")
                       .group_by("_inv").agg(rev=pl.col("amt").sum()))
        notes = credit_notes(r_all)
        d = (d.with_columns(_inv=_text("SELLER INVOICE NO"),
                            _val=pl.col("INVOICE VALUE").fill_null(0).clip(lower_bound=0))
              .join(g4, on="_inv", how="left", maintain_order="left")
              .join(reversed_, on="_inv", how="left", maintain_order="left")
              .join(notes, on="key", how="left", maintain_order="left")
              .with_columns(_total=pl.col("_val").sum().over("_inv"), _n=pl.len().over("_inv"),
                            _note=pl.col("note").fill_null(0)))
        share = pl.when(pl.col("_total") > 0).then(pl.col("_val") / pl.col("_total")).otherwise(1 / pl.col("_n"))
        d = d.with_columns(_share=share, _noted=pl.col("_note").sum().over("_inv"))
        debit = pl.col("rev") * pl.when(pl.col("_noted") > 0).then(pl.col("_note") / pl.col("_noted")).otherwise(pl.col("_share"))
        d = d.with_columns(**{"INVOICE PAID": pl.col("g_amt") * pl.col("_share"), "PAYMENT DATE": pl.col("g_paid"),
                              "CREDIT NOTE DEBIT": pl.when(debit != 0).then(debit)})
        d = d.with_columns(**{"NET SETTLEMENT": pl.when(pl.col("INVOICE PAID").is_not_null() | pl.col("CREDIT NOTE DEBIT").is_not_null())
                              .then(pl.col("INVOICE PAID").fill_null(0) + pl.col("CREDIT NOTE DEBIT").fill_null(0))})
    else:
        d = d.with_columns(*[pl.lit(None, dtype=pl.Float64).alias(c) for c in ["INVOICE PAID", "CREDIT NOTE DEBIT", "NET SETTLEMENT"]],
                           pl.lit(None, dtype=pl.Datetime("us")).alias("PAYMENT DATE"))
    d = d.with_columns(**{"PAYMENT STATUS": pl.when(pl.col("INVOICE PAID").is_not_null()).then(pl.lit("Settled"))
                          .when(pl.col("FINAL STATUS").is_in(["Delivered", "Customer Return"])).then(pl.lit("Payment Pending"))
                          .otherwise(pl.lit("Not Applicable"))})
    cols = ["ORDER DATE", "ORDER MONTH", "CUST ORDER NO", "SELLER ORDER NO", "SELLER INVOICE NO", "JIOCODE", "SELLER STYLE CODE",
            "SELLER SKU", "MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO", "BRAND", "CATEGORY", "DESCRIPTION", "QTY", "MRP",
            "SELLING PRICE", "SALE VALUE", "INVOICE VALUE", "FULFILLMENT TYPE", "PORTAL ORDER STATUS", "SOURCE", "STALE SHIPPED",
            "FINAL STATUS", "RETURN TYPE", "REASON", "RETURN ORDER NUMBER", "RETURN STATUS", "RETURN CREATED DATE", "RETURN MONTH",
            "CREDIT NOTE NUMBER", "COURIER", "SHIPMENT DATE", "SLA STATUS", "INVOICE PAID", "PAYMENT DATE", "CREDIT NOTE DEBIT",
            "NET SETTLEMENT", "PAYMENT STATUS"]
    d = d.sort(["ORDER DATE", "CUST ORDER NO", "_row"], nulls_last=True).select(cols)
    return d


def returned_units(raw: "pl.DataFrame", rtv) -> "pl.Series":
    """Units returned per row of raw: the Return QTY of the line's return orders, each once; no more than the row holds
    (a replacement can come back again)."""
    pl = _pl()
    keys = raw.select(_line_key().alias("key"), pl.col("ORDER MONTH").cast(pl.Datetime("us")).alias("_om"),
                      pl.col("QTY").cast(pl.Float64).alias("_q"))
    r = windowed_rtv(rtv, keys.select("key", "_om"))
    if not r.height:
        return pl.Series("units", [0.0] * raw.height, dtype=pl.Float64)
    units = (r.filter(pnum(pl.col("Return QTY")).fill_null(0) > 0)
              .unique(["RETURN ORDER NUMBER", "SELLER SKU"], keep="last", maintain_order=True)
              .filter(pl.col("key").is_not_null())
              .group_by("key").agg(_u=pnum(pl.col("Return QTY")).sum()))
    got = keys.join(units, on="key", how="left", maintain_order="left")
    return got.select(pl.min_horizontal(pl.col("_u").fill_null(0).cast(pl.Float64), pl.col("_q")).alias("units"))["units"]


def cancelled_units(raw: "pl.DataFrame", orders) -> "pl.Series":
    """Units cancelled per row of raw: Cancelled Qty of the order report (the newest file's line)."""
    import polars as pl
    o = _frame(orders)
    if not o.height or "Cancelled Qty" not in o.columns:
        return pl.Series("units", [0.0] * raw.height, dtype=pl.Float64)
    o = (o.with_columns(key=_key("Cust Order No", "Seller SKU")).unique("key", keep="last", maintain_order=True)
          .filter(pl.col("key").is_not_null()).select("key", _c=pnum(pl.col("Cancelled Qty")).fill_null(0)))
    got = raw.select(_line_key().alias("key")).join(o, on="key", how="left", maintain_order="left")
    return got["_c"].fill_null(0).cast(pl.Float64).alias("units")


RETURN_COLS = ["REASON", "RETURN TYPE", "RETURN ORDER NUMBER", "RETURN STATUS", "RETURN CREATED DATE", "RETURN MONTH", "CREDIT NOTE NUMBER"]
RAW_COLS = ["ORDER DATE", "ORDER MONTH", "SOURCE", "OMS STATUS", "CUST ORDER NO", "SELLER ORDER NO", "SELLER INVOICE NO", "JIOCODE",
            "SELLER STYLE CODE", "SELLER SKU", "MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO", "BRAND", "CATEGORY",
            "DESCRIPTION", "QTY", "MRP", "SELLING PRICE", "SALE VALUE", "INVOICE VALUE", "FULFILLMENT TYPE",
            "PORTAL ORDER STATUS", "FINAL STATUS", "RETURN TYPE", "REASON", "RETURN ORDER NUMBER", "RETURN STATUS",
            "RETURN CREATED DATE", "RETURN MONTH", "CREDIT NOTE NUMBER", "COURIER", "SHIPMENT DATE", "SLA STATUS",
            "INVOICE PAID", "PAYMENT DATE", "CREDIT NOTE DEBIT", "NET SETTLEMENT", "PAYMENT STATUS"]
MONEY = {"MRP", "SELLING PRICE", "SALE VALUE", "INVOICE VALUE", "INVOICE PAID", "CREDIT NOTE DEBIT", "NET SETTLEMENT"}


def report(raw: "pl.DataFrame", ledger_, input_log: list, file_months: "pl.DataFrame | None" = None) -> Report:
    import polars as pl

    from .workbook import present
    have_pay = bool(present(raw["NET SETTLEMENT"]).any())
    pay_months = None
    if ledger_ is not None and len(ledger_):
        lg = (ledger(ledger_).with_columns(m=pl.col("paid").dt.truncate("1mo"))
                .filter(pl.col("m").is_not_null() & pl.col("DT").is_not_null()))
        t = lg.group_by("m", "DT").agg(pl.col("amt").sum()).pivot(on="DT", index="m", values="amt").fill_null(0).sort("m")
        dts = [c for c in t.columns if c != "m"]
        for c in ("G4", "IC"):
            if c not in dts:
                t = t.with_columns(pl.lit(0.0).alias(c))
        others = sorted(c for c in dts if c not in ("G4", "IC"))
        t = t.select("m", pl.col("G4").alias("Received (G4)"), pl.col("IC").alias("Reversed (IC)"),
                     *[pl.col(c).alias(f"Other ({c})") for c in others])
        # KP = the bank payment itself
        bank = (t.select("m", (-pl.col("Other (KP)")).alias("Bank Paid (KP)")) if "Other (KP)" in t.columns
                else t.select("m", pl.lit(0.0).alias("Bank Paid (KP)")))
        t = t.drop("Other (KP)", strict=False)
        if file_months is not None and file_months.height:        # before the ledger: as the owner's monthly files
            later = t.filter(~pl.col("m").is_in(file_months["m"].to_list()))
            names = list(file_months.columns) + [c for c in t.columns if c not in file_months.columns]
            t = (pl.concat([file_months.with_columns(pl.col("m").cast(pl.Datetime("us"))), later], how="diagonal_relaxed")
                   .select(names).fill_null(0).sort("m", maintain_order=True))
        money = [c for c in t.columns if c != "m"]
        t = (t.with_columns(pl.sum_horizontal(money).alias("Net Due"))
              .join(bank, on="m", how="left", maintain_order="left")    # none before the ledger: a monthly file shows what is due
              .with_columns((pl.col("Net Due") - pl.col("Bank Paid (KP)")).round(0).alias("Difference")))
        pay_months = t
    return Report(
        portal="AJIO", raw=raw, raw_cols=RAW_COLS, value="SALE VALUE",
        settle="NET SETTLEMENT" if have_pay else None, money_cols=MONEY,
        reasons=[("Customer Return Reason", "Customer Return"), ("RTO Reason", "RTO")],
        pay_table=[("Invoice Value", "INVOICE VALUE"), ("Invoices Paid", "INVOICE PAID"),
                   ("Credit Notes", "CREDIT NOTE DEBIT"), ("Net Settlement", "NET SETTLEMENT")],
        pay_months=pay_months, input_log=input_log, min_orders=200, recv_all=True)
