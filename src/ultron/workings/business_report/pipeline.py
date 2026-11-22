"""Business reporting: the owner's sale / return / payment analysis workbook of every portal (Myntra,
Flipkart, AJIO), the same layout for each (workbook.py), from every month kept in Drive AGENT
WORK/PORTAL REPORTS (core/portal_reports.py) since --from (default Jan 2025: a portal's months
start where its reports do), into Drive AGENT WORK/BUSINESS REPORTING as
"<PORTAL> SALE RETURN ANALYSIS <FIRST MON-YY> TO <LAST MON-YY>.xlsx" (the portal's older one goes to
the trash). Telegram: one line per portal.

Run after the reports change: the 2nd (order + payment reports), the 10th and the 15th (return
reports) - the business-report workflow follows those runs - or by hand.

Tables are Polars (docs/libraries/06-polars.md); a month is datetime.datetime (the 1st, midnight).
"""
from __future__ import annotations

import argparse
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from ..core import portal_reports as pr
from ..core import telegram
from ..core.app import run_bot
from ..core.config import output_dir
from ..core.drive import API, DriveFolder, agent_folder
from . import ajio, flipkart, myntra, oms
from .workbook import LOG_COLS, add_months, build, num, present  # noqa: F401 - LOG_COLS: the INPUT LOG columns

log = logging.getLogger("bindal.business_report")

FOLDER = "BUSINESS REPORTING"
# Where Flipkart's and AJIO's reports start (owner's rule, 3 Nov 2026): Apr-25. What a month lacks shows "-".
# Flipkart from Feb-26 (owner, 17 Nov 2026): its Orders report starts there and every month after has its own return
# reports, so every figure is the portal's own; earlier months (Sales Report + OMSGuru, returns lost after ~4 months)
# are kept only in BUSINESS REPORTING/ARCHIVE (FLIPKART ... APR-25 TO OCT-26.xlsx). Each 15th adds the month before.
START = {"FLIPKART": date(2026, 2, 1), "AJIO": date(2025, 4, 1)}
NAME = re.compile(r"^(?P<portal>[A-Z]+) (?:(?P<acc>MAIN|DBCC|FMCC) )?(?P<kind>ORDER|RETURN|PAYMENT|SALES|MONTHLY|OMSGURU) REPORT "
                  r"(?P<mon>[A-Z]{3}-\d\d)(?P<partial> PARTIAL)?\.")


def month_of(text: str) -> date:
    y, m = text.split("-")
    return date(int(y), int(m), 1)


def mon(d) -> datetime:
    """A month (date, datetime) as the datetime of its 1st, midnight: the ORDER MONTH values of RAW DATA."""
    return datetime(d.year, d.month, 1)


def report_cache() -> Path:
    """The local copies of PORTAL REPORTS and the master, shared by every working of this machine: a file is downloaded
    again only when it changed on Drive (core/drive.DriveFolder.cached)."""
    return output_dir("cache") / "portal_reports"


def portal_files(portal: str, first: date, last: date, dest: Path | None = None, kinds: set[str] | None = None) -> list[dict]:
    """Every report file of the portal from first to last month, from the cache (dest, else report_cache()): one dict
    per file."""
    cache = (dest or report_cache()) / portal
    root = agent_folder(pr.ROOT)
    pf = root.subfolder(portal) if root else None
    out = []
    if not pf:
        return out
    nxt = (last.replace(day=28) + timedelta(days=4)).replace(day=1)
    for year, yf in sorted(pf.children().items()):
        if not year.isdigit() or not first.year <= int(year) <= nxt.year:
            continue
        for mlabel, mf in DriveFolder(yf["id"], pf.http).children().items():
            try:
                month = datetime.strptime(mlabel.strip(), "%b-%y").date()
            except ValueError:
                continue
            # the month after `last` only for its PARTIAL return report: the returns of last month's orders that
            # came in its 1st to 14th (the 15th's return analysis keeps them; owner, 16 Nov 2026)
            tail = month == nxt
            if not (first <= month <= last or tail):
                continue
            folder = DriveFolder(mf["id"], pf.http)
            for name, meta in folder.children().items():
                m = NAME.match(name)
                if not m or (tail and m["kind"] != "RETURN") or (kinds is not None and m["kind"] not in kinds):
                    continue
                path = folder.cached(name, cache, meta)    # downloaded only when the file changed on Drive
                out.append({"path": path, "month": month, "kind": m["kind"], "account": m["acc"] or "",
                            "partial": bool(m["partial"]), "name": name})
    log.info("PORTAL REPORTS/%s: %d files %s..%s", portal, len(out), first, last)
    return sorted(out, key=lambda x: (x["month"], x["kind"], x["account"]))


def master_sheet(dest: Path | None = None) -> pl.DataFrame:
    folder = agent_folder(FOLDER)
    path = folder.cached("MasterSheet.xlsx", dest or report_cache()) if folder else None
    if not path:
        raise RuntimeError(f"MasterSheet.xlsx not found in AGENT WORK/{FOLDER}")
    from ..core.tables import read_excel_text
    return read_excel_text(path, "Master")


def log_rows(files: list[dict], frames: dict[str, pl.DataFrame], date_col: dict[str, tuple[str, callable]]) -> list:
    """One INPUT LOG row per file: its rows and the first and last date of its date column (parse: a Polars expression)."""
    rows = []
    for f in files:
        df = frames.get(f["name"])
        n = df.height if df is not None else 0
        col, parse = date_col.get(f["kind"], (None, None))
        lo = hi = None
        if df is not None and col in df.columns:
            d = df.select(parse(pl.col(col)).alias("d"))["d"].drop_nulls()
            lo, hi = (d.min(), d.max()) if len(d) else (None, None)
        rows.append([f["kind"].title(), f["account"] or "-", f["name"], n, col or "-", lo, hi,
                     "days missing (PARTIAL)" if f["partial"] else ""])
    return rows


def read_any(path: Path, sheet: str | int = 0, header: int | None = 0) -> pl.DataFrame:
    """A report file as a Polars text table (core/tables: the same cells as pandas' readers gave)."""
    from ..core.tables import read_excel_text, read_text_csv
    if path.suffix.lower() == ".csv":
        return read_text_csv(path, na_words=True)
    return read_excel_text(path, sheet, header=header)


def by_file(*frames: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """Each file's own lines (`_file`) of these tables, for the INPUT LOG."""
    out = {}
    for df in frames:
        if df is not None and df.height and "_file" in df.columns:
            for (name,), g in df.partition_by("_file", as_dict=True).items():
                out[name] = g
    return out


def months_between(first: date, last: date) -> list[date]:
    out, m = [], first.replace(day=1)
    while m <= last:
        out.append(m)
        m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


# ------------------------------------------------------------------ portals
def missing_myntra_reports(files: list[dict], last: date) -> list[str]:
    """Order and return reports an account lacks: from its first report of that kind to the last
    month, or the whole kind when the account has none. Those months' figures are low."""
    out = []
    for kind in ("ORDER", "RETURN"):
        mine = [f for f in files if f["kind"] == kind]
        for account in myntra.ACCOUNT_OF.values():
            have = {f["month"] for f in mine if f["account"] == account}
            if not have:
                out.append(f"{account} {kind}: none")
                continue
            months = [m for m in months_between(min(have), last) if m not in have]
            if months:
                out.append(f"{account} {kind}: {month_names(months)}")
    return out


def build_myntra(files: list[dict], master: pl.DataFrame, missing: list[str] = ()) -> tuple:
    frames = {f["name"]: read_any(f["path"]).with_columns(ACCOUNT=pl.lit(f["account"])) for f in files}
    # _order: the file's place (month, kind, account) as a number: a later file's line is newer
    get = lambda k: [frames[f["name"]].with_columns(_order=pl.lit(i)) for i, f in enumerate(files) if f["kind"] == k]  # noqa: E731
    o, r, p = (pl.concat(get(k), how="diagonal_relaxed") if get(k) else pl.DataFrame() for k in ("ORDER", "RETURN", "PAYMENT"))
    if not len(o):
        raise RuntimeError("no Myntra order report in PORTAL REPORTS")
    p = myntra.payments_pl(p)
    raw = myntra.raw_data_pl(o, r, master, p)
    lg = log_rows(files, frames, {"ORDER": ("created on", myntra.pdt), "RETURN": ("return_created_date", myntra.pdt),
                                  "PAYMENT": ("Payment_Date", myntra.pdt)})
    lg.append(["Orders used", "ALL", "one row per order line", raw.height, "Order date", raw["ORDER DATE"].min(), raw["ORDER DATE"].max(), ""])
    lg.append(["SKU master", "ALL", "BUSINESS REPORTING/MasterSheet.xlsx (sheet Master)", master.height, "-", None, None, ""])
    for gap in missing:
        lg.append(["Report missing", "-", gap, "-", "-", None, None, "not in PORTAL REPORTS: the figures of these months are low"])
    unknown = mark_returns_not_known({}, files, set(raw["ORDER MONTH"].drop_nulls().to_list()), lg)
    rep = myntra.report_pl(raw, p, lg)
    rep.unknown = {k: set(rep.unknown.get(k, set())) | v for k, v in unknown.items()} if rep.unknown else unknown
    return rep, o


def category_map(myntra_orders, master: pl.DataFrame) -> dict[str, str]:
    """DESIGN-NO -> the article type Myntra lists it under (the most common; the first seen of equals), for the other portals."""
    if myntra_orders is None or not len(myntra_orders):
        return {}
    mm = master.filter(pl.col("Channel Name").str.starts_with("MYNTRA").fill_null(False))
    by_code = (mm.filter(pl.col("MYNTRA SKU CODE").is_not_null()).unique("MYNTRA SKU CODE", keep="first", maintain_order=True)
                 .select(pl.col("MYNTRA SKU CODE").alias("myntra sku code"), pl.col("DESIGN-NO").alias("_a")))
    # pandas' map matched an empty seller SKU to the master's first row without a listing SKU: kept (nulls_equal)
    by_sku = (master.unique("Channel Listing SKU Code", keep="first", maintain_order=True)
                    .select(pl.col("Channel Listing SKU Code").alias("seller sku code"), pl.col("DESIGN-NO").alias("_b")))
    t = (myntra_orders.select("myntra sku code", "seller sku code", "article type").with_row_index("_r")
         .join(by_code, on="myntra sku code", how="left", maintain_order="left")
         .join(by_sku, on="seller sku code", how="left", maintain_order="left", nulls_equal=True)
         .select("_r", d=pl.coalesce("_a", "_b"), a="article type").drop_nulls(["d", "a"]))
    best = (t.group_by("d", "a").agg(n=pl.len(), r=pl.col("_r").min())
             .sort(["d", "n", "r"], descending=[False, True, False]).unique("d", keep="first"))
    return dict(zip(best["d"].to_list(), best["a"].to_list()))


RETURN_KEYS = ("rq", "tq", "tv", "nq", "nv")     # RTO, customer return, and the net (delivered) that rests on them


def returns_not_known(files: list[dict], months: set) -> set:
    """Order months whose returns are not all in PORTAL REPORTS (owner, 17 Nov 2026: returns / RTO only from the return
    sheet): a month's orders come back in its own and the next month's return report (to the 14th), for every account
    with orders that month. Their RTO, returns and net are "-", never 0 (Flipkart keeps returns about 4 months)."""
    have = {(f["account"], mon(f["month"])) for f in files if f["kind"] == "RETURN"}
    every = {a for a, _ in have} or {""}
    out = set()
    for m in months:
        m = mon(m)
        accounts = {f["account"] for f in files if f["kind"] == "ORDER" and mon(f["month"]) == m} or every
        if any((a, m) not in have or (a, add_months(m, 1)) not in have for a in accounts):
            out.add(m)
    return out


def mark_returns_not_known(unknown: dict, files: list[dict], months: set, lg: list) -> dict:
    gap = returns_not_known(files, months)
    for k in RETURN_KEYS:
        unknown[k] = set(unknown.get(k, set())) | gap
    if gap:
        lg.append(["Not known: Returns", "-", month_names(gap), "-", "-", None, None,
                   "shown as -: the return report of these months or of the month after them is not in PORTAL REPORTS, and "
                   "returns / RTO come from the return sheet only; the brand / category tables still hold these months' lines"])
    return unknown


def month_names(months) -> str:
    return ", ".join(f"{m:%b-%y}" for m in sorted(months))


def no_payment_months(raw: pl.DataFrame, paid: str, below: float = 0.01) -> set:
    """Order months with (almost) no payment on their sold lines: their payment is not known, not pending."""
    sold = raw.filter(pl.col("FINAL STATUS").is_in(["Delivered", "Customer Return"]) & pl.col("ORDER MONTH").is_not_null())
    if not sold.height:
        return set()
    has = present(sold[paid]).cast(pl.Float64)
    share = sold.select("ORDER MONTH", has=has).group_by("ORDER MONTH").agg(pl.col("has").mean())
    return set(share.filter(pl.col("has") < below)["ORDER MONTH"].to_list())


def mark_no_payment(raw: pl.DataFrame, months: set) -> pl.DataFrame:
    hit = pl.col("ORDER MONTH").is_in(list(months)) & (pl.col("PAYMENT STATUS") == "Payment Pending")
    return raw.with_columns(pl.when(hit).then(pl.lit("No Payment Report")).otherwise(pl.col("PAYMENT STATUS")).alias("PAYMENT STATUS"))


def earn_more_months(months: list) -> tuple[dict | None, str]:
    """(Flipkart's Earn More figures per order month, why not). A month the portal has no data for is not in the table."""
    from ..return_analysis.sources import flipkart_client
    try:
        client = flipkart_client()
        rows = {}
        for month in months:
            first = mon(month)
            end = (add_months(first, 1) - timedelta(days=1)).date()
            got = client.earn_more(first.date(), end)
            if got["gross_units"] > 0:
                rows[first] = got
        return dict(sorted(rows.items())), ""
    except Exception as exc:  # noqa: BLE001 - the workbook does not depend on it; it is named in the INPUT LOG
        log.warning("Flipkart Earn More not read: %s", exc)
        return None, str(exc)[:120]


def _blank_return(c: str, dtype) -> pl.Expr:
    """A return field of the rest of a line split by quantity: "" for the texts the old code blanked, else empty."""
    if c in ("REASON", "SUB REASON", "RETURN TYPE SOURCE"):
        return pl.lit("")
    return pl.lit(None, dtype=dtype)


def split_part(raw: pl.DataFrame, part, status, money: set, return_cols: list[str]) -> tuple[pl.DataFrame, int]:
    """Count by quantity: a line of which only some units were returned or cancelled becomes two rows of the same id, those
    units with `status` and the rest with the line's own. A rest whose status said returned is Delivered, without the return's
    details. Money is shared by quantity; the totals of QTY and money stay as they were (raises otherwise). (raw, lines split)
    part, status: a Series (or a list / one value) per row of raw."""
    x = raw.with_columns(_part=pl.Series(list(part), dtype=pl.Float64).fill_null(0).fill_nan(0),
                         _status=pl.Series(list(status) if not isinstance(status, str) else [status] * raw.height, dtype=pl.Utf8))
    hit = (pl.col("_part") > 0) & (pl.col("_part") < pl.col("QTY"))
    n = int(x.select(hit.sum()).item())
    if not n:
        return raw, 0
    cols = [c for c in money if c in raw.columns]
    share = pl.col("_part") / pl.col("QTY")
    h = x.filter(hit)
    done = h.with_columns(*[(num_or_null(c) * share).alias(c) for c in cols],
                          pl.col("_part").alias("QTY"), pl.col("_status").alias("FINAL STATUS"))
    rest = h.with_columns(*[(num_or_null(c) * (1 - share)).alias(c) for c in cols], (pl.col("QTY") - pl.col("_part")).alias("QTY"))
    gone = pl.col("FINAL STATUS").is_in(["Customer Return", "RTO", "Return Type Pending"])
    rest = rest.with_columns(*[pl.when(gone).then(_blank_return(c, rest.schema[c])).otherwise(pl.col(c)).alias(c)
                               for c in return_cols if c in rest.columns],
                             pl.when(gone).then(pl.lit("Delivered")).otherwise(pl.col("FINAL STATUS")).alias("FINAL STATUS"))
    out = (pl.concat([x.filter(~hit), done, rest], how="vertical_relaxed").drop("_part", "_status")
             .sort("ORDER DATE", nulls_last=True, maintain_order=True))
    for c in ["QTY", *cols]:
        before, after = raw.select(num(pl.col(c)).sum()).item(), out.select(num(pl.col(c)).sum()).item()
        if abs(before - after) > 0.01:
            raise RuntimeError(f"split by quantity changed the total of {c}: {before} to {after}")
    return out, n


def num_or_null(c: str) -> pl.Expr:
    """A money column as numbers, empty stays empty (pandas' to_numeric(errors="coerce"))."""
    return pl.col(c).cast(pl.Float64, strict=False)


def _master_by_final_sku(master: pl.DataFrame, channel: pl.Expr) -> pl.DataFrame:
    """The master rows of a channel by FINAL SKU (stripped, upper case; the first row of a SKU)."""
    return (master.filter(channel.fill_null(False))
                  .with_columns(_k=pl.col("FINAL SKU").cast(pl.Utf8).fill_null("nan").str.strip_chars().str.to_uppercase())
                  .unique("_k", keep="first", maintain_order=True)
                  .select("_k", *[pl.col(c).alias(f"_m.{c}") for c in ["MY SKU", "FINAL MY SKU", "DESIGN-NO", "Brand"]]))


def _with_oms_status(raw: pl.DataFrame, id_col: str, lines: pl.DataFrame) -> tuple[pl.DataFrame, pl.Series, set]:
    found, used = oms.match(raw, id_col, lines)
    text, final = oms.status_of(raw, found, lines)
    return raw.with_columns(text.alias("OMS STATUS")), final, used


def flipkart_with_oms(raw: pl.DataFrame, lines: pl.DataFrame, master: pl.DataFrame, cats: dict, no_orders: set) -> tuple[pl.DataFrame, int]:
    """OMSGuru's status on Flipkart's lines, and its lines the reports do not have in months with no Orders report (most
    RTO and some cancelled items never reach the Sales Report or a monthly file). (raw, lines added)"""
    raw = raw.with_columns(pl.lit("").alias("OMS STATUS"))
    if not lines.height:
        return raw, 0
    raw, final, used = _with_oms_status(raw, "ORDER ID", lines)
    settled = (raw["RETURN TYPE SOURCE"] == "Returns report").fill_null(False)
    after = oms.corrected(raw["FINAL STATUS"], final, settled)
    changed = ((after != raw["FINAL STATUS"]).fill_null(True) & after.is_in(["Customer Return", "RTO"])).fill_null(False)
    raw = raw.with_columns(pl.when(changed).then(pl.lit("OMSGuru")).otherwise(pl.col("RETURN TYPE SOURCE")).alias("RETURN TYPE SOURCE"),
                           after.alias("FINAL STATUS"))
    extra = (lines.filter(~pl.col("_i").is_in(list(used))).with_columns(month=pl.col("DAY").dt.truncate("1mo"))
                  .filter(pl.col("month").is_in(list(no_orders))))
    if not extra.height:
        return raw, 0
    fm = _master_by_final_sku(master, pl.col("Channel Name").str.to_uppercase() == "FLIPKART")
    token = (pl.col("SKU").str.split("-").list.get(1, null_on_oob=True).str.to_uppercase()
               .replace_strict(flipkart.CATEGORY_WORDS, default=None, return_dtype=pl.Utf8))
    design = pl.col("_m.DESIGN-NO")
    cat = design.replace_strict(cats, default=None, return_dtype=pl.Utf8) if cats else pl.lit(None, dtype=pl.Utf8)
    # returns / RTO only from the return sheet (owner, 17 Nov 2026); these lines have no order item id to look up there:
    # OMSGuru's "returned" is not taken (RTO -> Cancelled: never reached the buyer; a return -> Delivered)
    final_new = pl.col("FINAL").replace({"RTO": "Cancelled", "Customer Return": "Delivered"})
    new = (extra.join(fm, left_on="SKU", right_on="_k", how="left", maintain_order="left").select(
        pl.col("DAY").alias("ORDER DATE"), pl.col("month").alias("ORDER MONTH"), pl.col("ORDER").alias("ORDER ID"),
        pl.lit("OMSGuru").alias("SOURCE"), pl.col("STATUS").alias("OMS STATUS"), "SKU", pl.col("SKU").alias("FINAL SKU"),
        "QTY", pl.col("VALUE").alias("SALE VALUE"), pl.col("STATUS").alias("PORTAL ORDER STATUS"),
        final_new.alias("FINAL STATUS"), pl.lit("").alias("RETURN TYPE SOURCE"),
        pl.col("_m.MY SKU").alias("MY SKU"), pl.col("_m.FINAL MY SKU").alias("FINAL MY SKU"), design.alias("DESIGN-NO"),
        pl.col("_m.Brand").fill_null("Not Mapped").alias("BRAND"),
        pl.coalesce(cat, token, pl.lit("Not Mapped")).alias("CATEGORY"),
        pl.when(final_new.is_in(["Delivered", "Customer Return"])).then(pl.lit("Payment Pending")).otherwise(pl.lit("Not Applicable"))
          .alias("PAYMENT STATUS"),
        pl.lit("").alias("REASON")))
    out = (pl.concat([raw, new], how="diagonal_relaxed")
             .sort(["ORDER DATE", "ORDER ITEM ID"], nulls_last=True, maintain_order=True))
    return out, new.height


def ajio_with_oms(raw: pl.DataFrame, lines: pl.DataFrame, master: pl.DataFrame | None = None, cats: dict | None = None) -> tuple[pl.DataFrame, int]:
    """OMSGuru's status (channels Ajio and Ajio Api) on AJIO's lines, and its lines of days no report reaches.
    (raw, lines whose final status it changed)"""
    raw = raw.with_columns(pl.lit("").alias("OMS STATUS"))
    if not lines.height:
        return raw, 0
    raw, final, used = _with_oms_status(raw, "SELLER ORDER NO", lines)
    has_return = (raw["RETURN TYPE"].is_not_null() & raw["FINAL STATUS"].is_in(["Customer Return", "RTO"])).fill_null(False)
    after = oms.corrected(raw["FINAL STATUS"], final, has_return)
    changed = int((after != raw["FINAL STATUS"]).fill_null(True).sum())
    raw = raw.with_columns(after.alias("FINAL STATUS"))
    days = raw["ORDER DATE"].drop_nulls().unique().to_list()
    extra = lines.filter(~pl.col("_i").is_in(list(used)) & ~pl.col("DAY").is_in(days).fill_null(False))
    if extra.height and master is not None:
        am = _master_by_final_sku(master, pl.col("Channel Name").str.to_uppercase().str.starts_with("AJIO"))
        design = pl.col("_m.DESIGN-NO")
        cat = design.replace_strict(cats, default=None, return_dtype=pl.Utf8) if cats else pl.lit(None, dtype=pl.Utf8)
        new = (extra.join(am, left_on="SKU", right_on="_k", how="left", maintain_order="left").select(
            pl.col("DAY").alias("ORDER DATE"), pl.col("DAY").dt.truncate("1mo").alias("ORDER MONTH"),
            pl.lit("OMSGuru").alias("SOURCE"), pl.col("STATUS").alias("OMS STATUS"), pl.col("ORDER").alias("SELLER ORDER NO"),
            pl.col("SKU").alias("SELLER SKU"), pl.col("SKU").alias("FINAL SKU"), "QTY", pl.col("VALUE").alias("INVOICE VALUE"),
            pl.col("STATUS").alias("PORTAL ORDER STATUS"), pl.col("FINAL").alias("FINAL STATUS"), pl.lit("").alias("REASON"),
            pl.lit("Payment Pending").alias("PAYMENT STATUS"),
            pl.col("_m.MY SKU").alias("MY SKU"), pl.col("_m.FINAL MY SKU").alias("FINAL MY SKU"), design.alias("DESIGN-NO"),
            pl.col("_m.Brand").fill_null("Not Mapped").alias("BRAND"), pl.coalesce(cat, pl.lit("Not Mapped")).alias("CATEGORY")))
        raw = pl.concat([raw, new], how="diagonal_relaxed").sort("ORDER DATE", nulls_last=True, maintain_order=True)
    return raw, changed


def _count(raw: pl.DataFrame, expr: pl.Expr) -> int:
    return int(raw.select(expr.fill_null(False).sum()).item())


def build_flipkart(files: list[dict], master: pl.DataFrame, cats: dict, first: date, *, include_earn_more: bool = True) -> tuple:
    paths = lambda k: [f["path"] for f in files if f["kind"] == k]  # noqa: E731
    months_of = lambda *kinds: {mon(f["month"]) for f in files if f["kind"] in kinds}  # noqa: E731
    o, r, s = flipkart.read_orders(paths("ORDER")), flipkart.read_returns(paths("RETURN")), flipkart.read_settled(paths("PAYMENT"))
    tax = flipkart.read_sales(paths("SALES"))
    monthly = flipkart.read_monthly([(f["path"], mon(f["month"])) for f in files if f["kind"] == "MONTHLY"])
    # a monthly file is the payment only of a month with no Settled Transactions file: nothing counts twice
    by_month_file = flipkart.monthly_settled(monthly, months_of("PAYMENT"))
    s = pl.concat([x for x in (s, by_month_file) if x.height], how="diagonal_relaxed") if by_month_file.height else s
    if not o.height and not tax.height:
        raise RuntimeError("no Flipkart order or sales report in PORTAL REPORTS")
    if not o.height:
        o = pl.DataFrame({"order_item_id": []}, schema={"order_item_id": pl.Utf8})
    raw = flipkart.raw_data(o, r, master, s, cats, tax, monthly)
    lines = oms.read(paths("OMSGURU"))
    no_orders = months_of("SALES", "MONTHLY") - months_of("ORDER")
    raw, added = flipkart_with_oms(raw, lines, master, cats, no_orders)
    # a month with no order, sales or monthly report is left out and named: stray items of it in other
    # months' files (a return or settlement event) are not that month's sale
    have, start = list(months_of("ORDER", "SALES", "MONTHLY")), mon(first)
    in_have = pl.col("ORDER MONTH").is_in(have).fill_null(False)
    late = (pl.col("ORDER MONTH") >= start).fill_null(False)
    lacking = raw.filter(~in_have & late)
    raw = raw.filter(in_have & late).with_columns(pl.col("QTY").cast(pl.Float64, strict=False).fill_null(1))
    is_ret = raw["FINAL STATUS"].is_in(["Customer Return", "RTO"]).fill_null(False)
    part = pl.select(pl.when(is_ret).then(flipkart.returned_units(raw, r)).otherwise(0.0)).to_series()
    raw, split = split_part(raw, part, raw["FINAL STATUS"], flipkart.MONEY, flipkart.RETURN_COLS)
    lg = log_rows(files, by_file(o, r, s, tax, monthly, lines),
                  {"ORDER": ("order_date", flipkart.pdt), "RETURN": ("return_approval_date", flipkart.pdt),
                   "PAYMENT": ("Payment Date", flipkart.pdt), "SALES": ("Order Date", flipkart.pdt),
                   "MONTHLY": ("order_date", flipkart.pdt), "OMSGURU": ("DAY", flipkart.pdt)})
    lg.append(["OMSGuru", "-", f"status on {_count(raw, pl.col('OMS STATUS').ne_missing('')):,} lines; {added:,} lines added in months with no Orders report", added, "-", None, None,
               "a return, RTO or cancellation it shows replaces Delivered, In Transit or Return Type Pending; a line the Returns report settled is not changed. FBF orders are not in OMSGuru"])
    unsettled = _count(raw, (pl.col("FINAL STATUS") == "Delivered") & ~present_expr("SALE VALUE"))
    lg.append(["Orders used", "-", "one row per order item", raw.height, "Order date", raw["ORDER DATE"].min(), raw["ORDER DATE"].max(),
               f"sale value = the Sales Report's Price before discount, else Settled Transactions' Sale Amount; {unsettled:,} delivered items have none; "
               f"{_count(raw, pl.col('SOURCE') == 'Sales report'):,} items from the Sales Report only (months without an Orders report), "
               f"{_count(raw, pl.col('SOURCE') == 'Monthly file'):,} from the owner's monthly files only"])
    lg.append(["Counted by quantity", "-", f"{split:,} lines returned in part", split, "-", None, None,
               "every count sums QTY; a line of which only some units came back is two rows of the same ORDER ITEM ID, money shared by quantity"])
    months = set(raw["ORDER MONTH"].drop_nulls().to_list())
    with_orders, with_sales = months_of("ORDER"), months_of("SALES")
    unknown = {"cq": months - with_orders - with_sales, "rq": set() if lines.height else months - with_orders - with_sales,
               "recv": no_payment_months(raw, "NET SETTLEMENT", 0.10)}     # a few stray settlements are not a month's payment
    mark_returns_not_known(unknown, files, months, lg)
    partly = no_payment_months(raw, "NET SETTLEMENT", 0.90) - unknown["recv"]
    raw = mark_no_payment(raw, unknown["recv"])
    if unknown["cq"]:
        lg.append(["Not known: Cancelled", "-", month_names(unknown["cq"]), "-", "-", None, None,
                   "shown as -: no Orders report and no Sales Report for these months"])
    if months & with_sales - with_orders:
        lg.append(["Cancelled from the Sales Report", "-", month_names(months & with_sales - with_orders), "-", "-", None, None,
                   "no Orders report: every month's Sales Report merged, by order date. An item never invoiced (cancelled before dispatch) is in no report, so Gross and Cancelled are low in these months; an item cancelled and invoiced again counts as sold"])
    if unknown["rq"]:
        lg.append(["Not known: RTO", "-", month_names(unknown["rq"]), "-", "-", None, None,
                   "shown as -: no Sales Report for these months and the monthly files hold only items with a settlement, so most RTO items are not in them. Net Sale and Customer Return are whole"])
    if unknown["recv"]:
        lg.append(["Not known: Payment", "-", month_names(unknown["recv"]), "-", "-", None, None, "shown as -: no payment file reaches these orders (a few stray settlements are in RAW DATA and the PAYMENT MATCH only)"])
    if partly:
        lg.append(["Payment only in part", "-", month_names(partly), "-", "-", None, None, "Net Received is low in these months: the payment files of the months after them are missing (files exist for May-25, Jun-25, Oct-25 on)"])
    if lacking.height:
        names = ", ".join(sorted({f"{m:%b-%y}" for m in lacking["ORDER MONTH"].drop_nulls().to_list()}))
        lg.append(["Months left out", "-", names, lacking.height, "Order date", None, None, "no order or sales report for these months yet"])
    lg.append(["SKU master", "-", "MasterSheet.xlsx (channel FLIPKART); category = Myntra's article type of the design",
               master.height, "-", None, None, ""])
    bank = flipkart.bank_paid([(f["path"], mon(f["month"])) for f in files if f["kind"] == "PAYMENT"],
                              [(f["path"], mon(f["month"])) for f in files if f["kind"] == "MONTHLY"])
    earn, why = earn_more_months(sorted(months)) if include_earn_more else (None, "not needed for return analysis")
    if why:
        lg.append(["Earn More not read", "-", why, "-", "-", None, None, "the EARN MORE sheet is left out; the other sheets are whole"])
    else:
        empty = months - set(earn)
        lg.append(["Earn More", "-", f"{len(earn)} months from Seller Hub", len(earn), "Order date", None, None,
                   "its Gross counts items never invoiced and its rupees run above the Sales Report's prices, so it is above RAW DATA; "
                   "its Cancellations hold RTO" + (f"; shown as -: {month_names(empty)} (the portal has no data)" if empty else "")])
    rep = flipkart.report(raw, s, lg, bank)
    rep.earn_more = earn
    rep.unknown = unknown
    pm = rep.pay_months
    if pm is not None and "Net Bank Paid" in pm.columns:
        total = lambda c: float(pm.select(pl.col(c).fill_nan(None).sum()).item() or 0.0)  # noqa: E731
        paid, orders, on_lines = total("Net Bank Paid"), total("Order Settlement"), float(raw.select(num(pl.col("NET SETTLEMENT")).sum()).item())
        rep.pay_match = [("Net bank paid, all payment months", paid),
                         ("Add back: non-order SPF, ads, storage (no order line)", orders - paid),
                         ("= Order money settled", orders),
                         ("Orders placed before the report starts, or not in it", on_lines - orders),
                         ("= NET SETTLEMENT in RAW DATA = Net Received in MONTH WISE", on_lines)]
    return rep


def present_expr(c: str) -> pl.Expr:
    """pandas' notna() of a column as an expression: not null and not NaN."""
    return pl.col(c).is_not_null() & ~pl.col(c).cast(pl.Float64, strict=False).is_nan().fill_null(False)


def build_ajio(files: list[dict], master: pl.DataFrame, cats: dict, first: date) -> tuple:
    paths = lambda k: [f["path"] for f in files if f["kind"] == k]  # noqa: E731
    o, r, p = ajio.read(paths("ORDER")), ajio.read(paths("RETURN")), ajio.read(paths("PAYMENT"))
    if not o.height:
        raise RuntimeError("no AJIO order report in PORTAL REPORTS")
    start = mon(first)
    monthly = ajio.read_monthly(paths("MONTHLY"))
    raw = ajio.raw_data(o, r, p, master, cats, monthly)
    raw = raw.filter((pl.col("ORDER MONTH") >= start).fill_null(False))
    lines = oms.read(paths("OMSGURU"))
    raw, changed = ajio_with_oms(raw, lines, master, cats)
    raw = raw.filter((pl.col("ORDER MONTH") >= start).fill_null(False))
    ledger_date = lambda e: e.cast(pl.Utf8).str.strip_chars().str.to_datetime("%d.%m.%Y", strict=False, time_unit="us")  # noqa: E731
    lg = log_rows(files, by_file(o, r, p, monthly, lines),
                  {"ORDER": ("Cust Order Date", ajio.padate), "RETURN": ("Return Created Date", ajio.padate),
                   "PAYMENT": ("DOCDATE", ledger_date), "MONTHLY": ("Cust Order Date", ajio.padate),
                   "OMSGURU": ("DAY", flipkart.pdt)})
    lg.append(["OMSGuru", "-", f"channels Ajio and Ajio Api: status on {_count(raw, pl.col('OMS STATUS').ne_missing('')):,} lines, final status changed on {changed:,}", lines.height, "-", None, None,
               "a return, RTO or cancellation it shows replaces Delivered or In Transit; a line the RTV report settled is not changed"])
    lg.append(["Orders used", "-", "one row per order line (Cust Order No + Seller SKU)", raw.height, "Order date",
               raw["ORDER DATE"].min(), raw["ORDER DATE"].max(), "sale value = Selling Price x qty; net settlement = SRM ledger G4 received + IC reversed"])
    if p.height:
        led = ajio.ledger(p)
        left = {dt: float(led.filter(pl.col("DT") == dt)["amt"].sum()) - float(raw.select(num(pl.col(col)).sum()).item())
                for dt, col in (("G4", "INVOICE PAID"), ("IC", "CREDIT NOTE DEBIT"))}
        if any(abs(v) >= 1 for v in left.values()):
            lg.append(["Ledger not on these orders", "-", f"G4 {left['G4']:,.0f}, IC {left['IC']:,.0f}", led.height, "-", None, None,
                       "in the ledger, but its order or return line is not in these reports: left out of NET SETTLEMENT"])
    from_file = raw.filter(pl.col("SOURCE") == "Monthly file")
    before_ledger = no_payment_months(raw, "INVOICE PAID")
    raw = ajio.file_payment(raw, r, before_ledger)
    # by quantity, after the payment (it maps a line's money by its key): cancelled units first, then returned ones
    raw = raw.with_columns(pl.col("QTY").cast(pl.Float64, strict=False).fill_null(1))
    money = ajio.MONEY - {"MRP", "SELLING PRICE"}
    not_cancelled = (raw["FINAL STATUS"] != "Cancelled").fill_null(True)
    cancel = pl.select(pl.when(not_cancelled).then(ajio.cancelled_units(raw, o)).otherwise(0.0)).to_series()
    raw, cancel_split = split_part(raw, cancel, "Cancelled", money, ajio.RETURN_COLS)
    is_ret = raw["FINAL STATUS"].is_in(["Customer Return", "RTO"]).fill_null(False)
    returned = pl.select(pl.when(is_ret).then(ajio.returned_units(raw, r)).otherwise(0.0)).to_series()
    raw, return_split = split_part(raw, returned, raw["FINAL STATUS"], money, ajio.RETURN_COLS)
    lg.append(["Counted by quantity", "-", f"{return_split:,} lines returned in part, {cancel_split:,} cancelled in part", return_split + cancel_split, "-", None, None,
               "every count sums QTY; a line of which only some units came back or were cancelled is two rows of the same order line, money shared by quantity"])
    from_oms = raw.filter(pl.col("SOURCE") == "OMSGuru")
    seen = raw.filter(pl.col("ORDER MONTH").is_not_null()).group_by("ORDER MONTH").agg(v=present_expr("SALE VALUE").any())
    no_value = set(seen.filter(~pl.col("v"))["ORDER MONTH"].to_list())
    month_set = lambda df: set(df["ORDER MONTH"].drop_nulls().to_list())  # noqa: E731
    unknown = {"cq": month_set(from_file) | month_set(from_oms), "recv": set(), "gv": no_value, "tv": no_value, "nv": no_value}
    mark_returns_not_known(unknown, files, month_set(raw), lg)
    if from_oms.height:
        lg.append(["Lines from OMSGuru", "-", f"{month_names(month_set(from_oms))}: days with no order report or monthly file", int(from_oms["QTY"].sum()), "-",
                   from_oms["ORDER DATE"].min(), from_oms["ORDER DATE"].max(), "order id, SKU, qty, status; no selling price, so a month with only these shows its values as -"])
    if from_file.height:
        lg.append(["Monthly files", "-", f"{from_file.height:,} order lines the order report does not have", from_file.height, "-", None, None, ""])
    stale = _count(raw, pl.col("STALE SHIPPED") & (pl.col("FINAL STATUS") == "Delivered"))
    if stale:
        lg.append(["Shipped, counted Delivered", "-", f"{stale:,} order lines", stale, "-", None, None,
                   f"Shipped in their report, over {ajio.SHIPPED_DAYS} days old, no return line since: a report's status is as old as its file"])
    if unknown["cq"]:
        lg.append(["Not known: Cancelled", "-", month_names(unknown["cq"]), "-", "-", None, None,
                   "shown as -: the monthly files and OMSGuru leave out most lines cancelled before shipping, so Gross Qty and Gross Value are low in these months"])
    if before_ledger:
        lg.append(["Payment as per monthly files", "-", month_names(before_ledger), "-", "-", None, None,
                   "the SRM ledger has no line before 28 Feb 2026: Invoice Value less FWD B2B Invoice Amt of returns, as the owner's monthly files work it out (their EXP sheets not taken off); what is due, not the bank"])
    charges = ajio.monthly_expenses([(f["path"], mon(f["month"])) for f in files if f["kind"] == "MONTHLY"])
    rep = ajio.report(raw, p, lg, ajio.file_payment_months(raw, r, before_ledger, charges))
    rep.unknown = unknown
    if rep.pay_months is not None and p.height:
        ledger_months = rep.pay_months.filter(present_expr("Bank Paid (KP)"))
        rep.pay_match = ajio.payment_match(raw, p, ledger_months)
    return rep


# ------------------------------------------------------------------ run
def upload(path: Path, portal: str) -> None:
    folder = agent_folder(FOLDER, create=True)
    folder.put(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    for name, meta in folder.children().items():
        if name.startswith(f"{portal} SALE RETURN ANALYSIS") and name != path.name:
            r = folder.http.patch(f"{API}/{meta['id']}", params={"supportsAllDrives": "true"}, json={"trashed": True}, timeout=60)
            folder._check(r, f"trash of {name}")
            log.info("Older %s moved to the trash", name)


def summary(rep, out: Path) -> str:
    raw = rep.raw
    q = lambda s: float(raw.filter(pl.col("FINAL STATUS") == s).select(num(pl.col("QTY")).sum()).item())  # noqa: E731
    gross = float(raw.select(num(pl.col("QTY")).sum()).item())
    net, ret, rto, canc = q("Delivered"), q("Customer Return"), q("RTO"), q("Cancelled")
    m0, m1 = raw["ORDER MONTH"].min(), raw["ORDER MONTH"].max()
    disp = gross - canc
    return (f"✅ <b>{rep.portal}</b> {m0:%b-%y} to {m1:%b-%y}: {int(gross):,} qty, net {net / gross:.1%}, "
            f"return {ret / (net + ret):.1%}, RTO {rto / disp:.1%}" + ("" if rep.settle else ", no payments yet")
            if gross and disp and (net + ret) else f"✅ <b>{rep.portal}</b>: {out.name}")


def myntra_orders_only(files: list[dict]) -> pl.DataFrame:
    """Myntra's order lines only (the category map of the other portals)."""
    frames = [read_any(f["path"]) for f in files if f["kind"] == "ORDER"]
    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def run(args) -> int:
    today = date.today()
    first = month_of(args.from_month)
    last = month_of(args.to_month) if args.to_month else (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    portals = [p.strip().upper() for p in (args.portals or "MYNTRA,FLIPKART,AJIO").split(",") if p.strip()]
    work = Path(args.work) if args.work else None          # None: the shared cache (report_cache)
    master = master_sheet(work)
    out_dir = output_dir("business_report")
    lines, failed, cats = ["📊 <b>Business reporting</b>", ""], [], {}
    others = [p for p in portals if p != "MYNTRA"]
    if "MYNTRA" in portals or others:          # Myntra first: its article types name the others' categories
        try:
            files = portal_files("MYNTRA", first, last, work)
            if "MYNTRA" in portals:
                missing = missing_myntra_reports(files, last)
                rep, orders = build_myntra(files, master, missing)
                done = finish(rep, out_dir, args)
                lines.append(summary(rep, done))
                if missing:
                    lines.append(f"⚠️ Figures low, reports missing: {telegram.esc('; '.join(missing))}")
            else:
                orders = myntra_orders_only(files)
            cats = category_map(orders, master)
        except Exception as exc:  # noqa: BLE001 - one portal never stops the others
            log.exception("MYNTRA business report failed")
            failed.append("MYNTRA")
            lines.append(f"❌ <b>MYNTRA</b>: {telegram.esc((str(exc).splitlines() or [type(exc).__name__])[0][:200])}")
    for portal in others:
        try:
            start = max(first, START.get(portal, first))
            files = portal_files(portal, start, last, work)
            rep = build_flipkart(files, master, cats, start) if portal == "FLIPKART" else build_ajio(files, master, cats, start)
            lines.append(summary(rep, finish(rep, out_dir, args, start)))
        except Exception as exc:  # noqa: BLE001
            log.exception("%s business report failed", portal)
            failed.append(portal)
            lines.append(f"❌ <b>{portal}</b>: {telegram.esc((str(exc).splitlines() or [type(exc).__name__])[0][:200])}")
    lines.append(f"\n<i>Drive AGENT WORK/{FOLDER}</i>" + (" (test run: not uploaded)" if args.no_upload else ""))
    text = "\n".join(lines)
    print(text) if args.no_telegram else telegram.send(text)
    if failed:
        raise RuntimeError(f"business report failed for {', '.join(failed)}")
    return 0


def finish(rep, out_dir: Path, args, first: date | None = None) -> Path:
    # a report of the first month also carries a few older orders (their events fell in it): not a month of the report
    rep.raw = rep.raw.filter((pl.col("ORDER MONTH") >= mon(first or month_of(args.from_month))).fill_null(False))
    m0, m1 = rep.raw["ORDER MONTH"].min(), rep.raw["ORDER MONTH"].max()
    out = out_dir / f"{rep.portal} SALE RETURN ANALYSIS {m0:%b-%y} TO {m1:%b-%y}".upper()
    out = out.with_name(out.name + ".xlsx")
    build(rep, out)
    if not args.no_upload:
        upload(out, rep.portal)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py business-report", description=__doc__.splitlines()[0])
    p.add_argument("--portals", default="", help="MYNTRA,FLIPKART,AJIO (default: all)")
    p.add_argument("--from", dest="from_month", default="2025-01", metavar="YYYY-MM", help="first order month (default 2025-01)")
    p.add_argument("--to", dest="to_month", default="", metavar="YYYY-MM", help="last order month (default: last month)")
    p.add_argument("--no-upload", action="store_true", help="build only, Drive not changed (test run)")
    p.add_argument("--work", default="", help="another folder for the local copies of the reports (default: the shared cache)")
    return run_bot("Business reporting", p, run, argv)
