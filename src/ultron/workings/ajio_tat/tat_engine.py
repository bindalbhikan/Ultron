"""
AJIO Order Dispatch TAT engine  (10:10 rule)

Rule: orders received from yesterday 10:00 AM to today 10:00 AM must be
processed AND dispatched (picked up by courier) the same day (today).
  -> order time <  10:00  => due date = order date
  -> order time >= 10:00  => due date = order date + 1

Ported from the original main.py script. The rules are unchanged; the differences are:
  * inputs arrive as tables (scraped from OMSGuru, tracked live) instead of
    the latest files in ./input
  * the master carries an extra "Order ID" column (AJIO channel order id) so an
    order that is not invoiced yet can be stored and later replaced by its
    invoiced row
  * write_excel() is kept for the optional local .xlsx copy of the master

Tables are Polars (docs/libraries/06-polars.md); the xlsx is written by xlsxwriter.
"""
import re
from datetime import datetime, time

import polars as pl

from ..core.tables import pclean_id

CUTOFF = time(10, 0)          # 10:10 rule cut-off
SKIP_SUNDAY = False           # True => if due date falls on Sunday, push to Monday
# AJIO Promise Ship Date (mail of 3 Aug 2026; in OMSGuru from 29 Jul 2026): the order must be
# picked up by the courier's pickup time on the due date, not by 23:59. Orders before
# PSD_FROM keep 23:59:59; a courier not listed here also keeps 23:59:59.
PSD_FROM = datetime(2026, 7, 29)
PICKUP_TIME = {"XPRESSBEES": time(12, 0), "BLUEDART": time(12, 0),
               "SHADOWFAX": time(12, 30), "DELHIVERY": time(12, 30)}
END_OF_DAY = time(23, 59, 59)

OMS_DATE_FMT = "%B %d, %Y %I:%M:%S %p"
PENDING_PREFIX = "PENDING-"   # key used for orders that have no invoice number yet

# Courier event statuses that mean the parcel was physically picked up.
PICKUP_STATUSES = {
    "shipment picked up", "pickdone", "picked up", "pickup done", "picked",
}
# Events that happen BEFORE pickup (ignored when falling back to first movement).
PRE_PICKUP = re.compile(
    r"data received|manifest|pickup employee|out for pick|pickup has been|"
    r"pickup re-scheduled|auto pickup|p/u|pending|registered|order cancelled|pickup scheduled|"
    r"shipment created|outforpickup|notpicked|rtoconfirmed|marked rto",   # Ekart (Flipkart): still with us; RTO before any movement = never picked
    re.I,
)
# Courier scans that mean a pickup was booked / an agent is on the way (pickup attempt).
PICKUP_ATTEMPT = r"pickup employee|out for pick|pickup has been|auto pickup|pickup scheduled|outforpickup"
# Ekart's pickup scan carries the hub after it ("PickupReceived - Motavarachahub_STV_PL")
PICKUP_SCAN = r"^(?:pickupreceived|pickup from seller)\b"

# An order processed (RTS) today at or after this time is picked up by the courier tomorrow:
# its Pickup Status is "Next Day Pickup", not "Pending Pickup". Next run it becomes
# "Pending Pickup" again if still not picked.
NEXT_DAY_PICKUP = "Next Day Pickup"
NEXT_DAY_AFTER = time(12, 0)
OPEN_PICKUP = ("Pending Pickup", NEXT_DAY_PICKUP)
CANCEL_ITEM_STATUSES = re.compile(r"cancel", re.I)
# OMSGuru item statuses that mean the courier took the parcel. Old orders (a rebuild from months
# back) have no courier history left and OMSGuru logs no pickup event, so these say "picked".
PICKED_ITEM_STATUSES = re.compile(r"in transit|delivered|return|rto|rtv", re.I)
# Courier summary statuses meaning the parcel has not left the warehouse yet.
# PICKUP_FAILED: the courier came but did not take it. RETURN_PENDING: a scan with
# return wording before pickup. Neither means the parcel left the warehouse.
NOT_PICKED_COURIER_STATUSES = {"UNKNOWN", "NOT_FOUND", "PENDING", "OUT_FOR_PICKUP", "PICKUP_FAILED",
                               "RETURN_PENDING", "nan", "None", ""}

REPORT_COLS = ["Invoice No", "Order ID", "Cust Order No", "AWB", "Courier", "Order Time",
               "Dispatch Deadline", "Processed Time", "RTS Time", "Pickup Attempt Time", "Pickup Time",
               "Process Status", "Pickup Status", "TAT Result", "OMS Item Status",
               "Courier Status", "Label Printed", "ERP Label Time", "ERP Label By", "Pickup Ticket", "Last Updated"]
# Raw fields kept in the master (_data sheet) so statuses can be recomputed every run.
DATA_COLS = ["Invoice No", "Order ID", "Cust Order No", "AWB", "Courier", "Order Time",
             "Dispatch Deadline", "Processed Time", "RTS Time", "RTS Exact", "Pickup Attempt Time", "Pickup Time",
             "OMS Item Status", "Courier Status", "ERP Label Time", "ERP Label By", "Pickup Ticket", "Last Updated"]
TIME_COLS = ["Order Time", "Dispatch Deadline", "Processed Time", "RTS Time",
             "Pickup Attempt Time", "Pickup Time", "ERP Label Time", "Last Updated"]
STATUS_COLS = ["Process Status", "Pickup Status", "TAT Result"]
TEXT_COLS = [c for c in DATA_COLS if c not in TIME_COLS and c != "RTS Exact"]
SCHEMA = {c: (pl.Datetime("us") if c in TIME_COLS else pl.Boolean if c == "RTS Exact" else pl.Utf8) for c in DATA_COLS}


def _ci(pattern) -> str:
    """A Python regex (re.I) as a Polars one."""
    return "(?i)" + (pattern.pattern if hasattr(pattern, "pattern") else pattern)


def parse_oms(e: pl.Expr) -> pl.Expr:
    return e.cast(pl.Utf8).str.strip_chars().str.to_datetime(OMS_DATE_FMT, strict=False, time_unit="us")


def parse_when(e: pl.Expr) -> pl.Expr:
    """A time as the master or a sheet keeps it (ISO "YYYY-MM-DD HH:MM:SS[.ffffff]", "YYYY-MM-DDTHH:MM:SS" or a day);
    an empty or unreadable cell is empty."""
    s = e.cast(pl.Utf8).str.strip_chars().str.replace("T", " ", literal=True)
    return pl.coalesce(s.str.to_datetime("%Y-%m-%d %H:%M:%S%.f", strict=False, time_unit="us"),
                       s.str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False, time_unit="us"),
                       s.str.to_datetime("%Y-%m-%d %H:%M", strict=False, time_unit="us"),
                       s.str.to_date("%Y-%m-%d", strict=False).cast(pl.Datetime("us")))


def as_time(e: pl.Expr, dtype) -> pl.Expr:
    """A column as datetimes, whether it came typed or as text."""
    return e.cast(pl.Datetime("us")) if dtype.is_temporal() else parse_when(e)


def deadline(order: pl.Expr, courier: pl.Expr) -> pl.Expr:
    """Due date (10:10 rule) at the courier's pickup time, or 23:59:59 before PSD_FROM."""
    day = order.dt.truncate("1d")
    due = pl.when(order.dt.time() < CUTOFF).then(day).otherwise(day.dt.offset_by("1d"))
    if SKIP_SUNDAY:
        due = pl.when(due.dt.weekday() == 7).then(due.dt.offset_by("1d")).otherwise(due)
    pick = (courier.cast(pl.Utf8).fill_null("None").str.strip_chars().str.to_uppercase()
                   .replace_strict(PICKUP_TIME, default=END_OF_DAY, return_dtype=pl.Time))
    at = pl.when(order >= PSD_FROM).then(pick).otherwise(pl.lit(END_OF_DAY))
    return due.dt.combine(at)


def dispatch_deadlines(df: pl.DataFrame) -> pl.Series:
    """Dispatch Deadline for every row, so old master rows follow the current rule too."""
    return df.select(deadline(pl.col("Order Time"), pl.col("Courier")).alias("Dispatch Deadline"))["Dispatch Deadline"]


def awb_of(e: pl.Expr) -> pl.Expr:
    return e.cast(pl.Utf8).fill_null("nan").str.extract(r"^\s*([A-Za-z0-9]+)", 1).fill_null("")


SUMM_COLS = ["AWB", "PARTNER", "STATUS", "STATUS_RAW", "CURRENT_LOCATION", "LAST_UPDATE", "DELIVERED_ON"]
EV_COLS = ["AWB", "SEQ", "TIMESTAMP", "STATUS", "LOCATION"]


def prepare_tracking(summary_rows, event_rows):
    """Same shape the original main.py got from the tracking_*.xlsx Summary + Events sheets."""
    summ = pl.DataFrame([dict(zip(SUMM_COLS, r)) if not isinstance(r, dict) else r for r in summary_rows],
                        schema={c: pl.Utf8 for c in SUMM_COLS}, strict=False)
    ev = pl.DataFrame([dict(zip(EV_COLS, r)) if not isinstance(r, dict) else r for r in event_rows],
                      schema={"AWB": pl.Utf8, "SEQ": pl.Int64, "TIMESTAMP": pl.Utf8, "STATUS": pl.Utf8, "LOCATION": pl.Utf8},
                      strict=False)
    ev = (ev.with_columns(parse_when(pl.col("TIMESTAMP")).alias("ts")).filter(pl.col("ts").is_not_null())
            .sort(["AWB", "ts", "SEQ"], maintain_order=True))
    return summ, ev


def pickup_times(ev: pl.DataFrame) -> pl.DataFrame:
    """AWB -> Pickup Time, Pickup Event, Pickup Source, Pickup Attempt Time (first pickup scan, else the first
    movement after a history that starts before pickup)."""
    cols = {"AWB": pl.Utf8, "Pickup Time": pl.Datetime("us"), "Pickup Event": pl.Utf8, "Pickup Source": pl.Utf8,
            "Pickup Attempt Time": pl.Datetime("us")}
    if not ev.height:
        return pl.DataFrame(schema=cols)
    st = pl.col("STATUS").cast(pl.Utf8).fill_null("nan").str.strip_chars()
    exact = st.str.to_lowercase().is_in(sorted(PICKUP_STATUSES)) | st.str.contains(_ci(PICKUP_SCAN))
    attempt = st.str.contains(_ci(PICKUP_ATTEMPT))
    pre = st.str.contains(_ci(PRE_PICKUP))
    e = ev.with_columns(_exact=exact, _attempt=attempt, _pre=pre,
                        _x=pl.col("ts").filter(exact).first().over("AWB"))
    g = e.group_by("AWB", maintain_order=True).agg(
        pl.col("_x").first().alias("x_ts"), pl.col("STATUS").filter(pl.col("_exact")).first().alias("x_ev"),
        pl.col("ts").filter(pl.col("_attempt") & (pl.col("ts") <= pl.col("_x"))).first().alias("a_before"),
        pl.col("ts").filter(pl.col("_attempt")).first().alias("a_any"),
        pl.col("_pre").first().alias("starts_pre"),
        pl.col("ts").filter(~pl.col("_pre")).first().alias("m_ts"), pl.col("STATUS").filter(~pl.col("_pre")).first().alias("m_ev"))
    has_x, has_m = pl.col("x_ts").is_not_null(), pl.col("m_ts").is_not_null()
    return g.select(
        "AWB",
        pl.when(has_x).then("x_ts").when(pl.col("starts_pre") & has_m).then("m_ts").alias("Pickup Time"),
        pl.when(has_x).then("x_ev").when(pl.col("starts_pre") & has_m).then("m_ev").otherwise(pl.lit("")).alias("Pickup Event"),
        pl.when(has_x).then(pl.lit("Pickup scan")).when(~pl.col("starts_pre")).then(pl.lit("No pickup data (courier history missing)"))
          .when(has_m).then(pl.lit("First movement scan")).otherwise(pl.lit("No pickup scan")).alias("Pickup Source"),
        pl.when(has_x).then("a_before").otherwise("a_any").alias("Pickup Attempt Time"))


def _first(c: str) -> pl.Expr:
    """pandas' groupby first: the first value that is not empty."""
    return pl.col(c).drop_nulls().first()


def _joined(c: str) -> pl.Expr:
    """The distinct values of a group in order, ", " between ("nan" for an empty one, as the old report wrote it)."""
    return pl.col(c).cast(pl.Utf8).fill_null("nan").unique(maintain_order=True).str.join(", ")


def build_report(o: pl.DataFrame, hist: pl.DataFrame, summ: pl.DataFrame, ev: pl.DataFrame, now: datetime | None = None):
    """One master row per order (invoice + AWB) from OMSGuru's lines, its history and the courier tracking; (rows, as of)."""
    now = now or datetime.now()
    o = o.with_columns(awb_of(pl.col("AWB / Shipment Tracker")).alias("AWB"))
    agg = o.group_by("Input Identifier", "AWB", maintain_order=True).agg(
        _first("Internal Order ID").alias("internal_id"), _first("Channel Order ID").alias("channel_order"),
        _joined("Item Status").alias("item_status"), _first("Order Date").alias("order_date"),
        _first("Invoice Date").alias("invoice_date"), _first("Dispatch Log").alias("dispatch_log"),
        _first("Shipping Company").alias("courier"))
    first_ts = lambda status: (hist.filter(pl.col("Status") == status).group_by("Internal Order ID")  # noqa: E731
                                   .agg(pl.col("ts").min()).rename({"Internal Order ID": "internal_id"}))
    agg = (agg.join(first_ts("Processing").rename({"ts": "hist_proc"}), on="internal_id", how="left", maintain_order="left")
              .join(first_ts("Ready to ship").rename({"ts": "hist_rts"}), on="internal_id", how="left", maintain_order="left")
              .with_columns(parse_oms(pl.col("order_date")).alias("Order Time"), parse_oms(pl.col("invoice_date")).alias("Invoice Time")))
    # Processed time: history 'Processing' else Invoice generation time
    # Ready to ship: history 'Ready to ship' else Dispatch Log date (date only); blank -> invoice time (label printed on invoicing)
    dlog = parse_when(pl.col("dispatch_log").cast(pl.Utf8).fill_null("nan").str.slice(0, 10))
    rts = pl.coalesce("hist_rts", dlog)
    source = (pl.when(pl.col("hist_rts").is_not_null()).then(pl.lit("Status History"))
                .when(dlog.is_not_null()).then(pl.lit("Dispatch Log (date only)"))
                .when(pl.col("Invoice Time").is_not_null()).then(pl.lit("Invoice Date")).otherwise(pl.lit("Not available")))
    agg = agg.with_columns(pl.coalesce("hist_proc", "Invoice Time").alias("Processed Time"),
                           pl.coalesce(rts, "Invoice Time").alias("RTS Time"), source.alias("RTS Source"))
    courier_status = (summ.select("AWB", pl.col("STATUS").alias("Courier Status")).unique("AWB", keep="first", maintain_order=True)
                      if summ.height else pl.DataFrame(schema={"AWB": pl.Utf8, "Courier Status": pl.Utf8}))
    agg = (agg.join(pickup_times(ev), on="AWB", how="left", maintain_order="left")
              .join(courier_status, on="AWB", how="left", maintain_order="left"))
    out = agg.select(
        pl.col("Input Identifier").cast(pl.Utf8).alias("Invoice No"), pl.col("channel_order").cast(pl.Utf8).alias("Order ID"),
        pl.lit(None, dtype=pl.Utf8).alias("Cust Order No"), "AWB", pl.col("courier").cast(pl.Utf8).alias("Courier"),
        "Order Time", deadline(pl.col("Order Time"), pl.col("courier")).alias("Dispatch Deadline"), "Processed Time", "RTS Time",
        pl.when(pl.col("RTS Time").is_null()).then(None).otherwise(pl.col("RTS Source") != "Dispatch Log (date only)").alias("RTS Exact"),
        "Pickup Attempt Time", "Pickup Time", pl.col("item_status").alias("OMS Item Status"), "Courier Status",
        pl.lit(None, dtype=pl.Datetime("us")).alias("ERP Label Time"), pl.lit(None, dtype=pl.Utf8).alias("ERP Label By"),
        pl.lit(None, dtype=pl.Utf8).alias("Pickup Ticket"),
        pl.lit(datetime.combine(now.date(), time())).cast(pl.Datetime("us")).alias("Last Updated"))
    as_of = ev["ts"].max() if ev.height else now
    return out.cast(SCHEMA), as_of


def _id(e: pl.Expr) -> pl.Expr:
    t = e.cast(pl.Utf8)
    return pclean_id(pl.when(t.is_in(["nan", "None", "", "NaT"])).then(None).otherwise(t))


def normalize_master(m: pl.DataFrame | None) -> pl.DataFrame:
    """A master loaded from Sheets / xlsx (text or typed) in DATA_COLS with proper types; rows without an invoice out."""
    if m is None or not m.width:
        return pl.DataFrame(schema=SCHEMA)
    cols = []
    for c in DATA_COLS:
        e = pl.col(c) if c in m.columns else pl.lit(None, dtype=pl.Utf8)
        dtype = m.schema[c] if c in m.columns else pl.Utf8
        if c in TIME_COLS:
            cols.append(as_time(e, dtype).alias(c))
        elif c in ("Invoice No", "Order ID", "Cust Order No", "AWB", "Pickup Ticket"):
            cols.append(_id(e).alias(c))
        elif c == "RTS Exact":
            t = e.cast(pl.Utf8).str.strip_chars()
            cols.append(pl.when(t.is_null() | (t == "")).then(None).otherwise(t.str.to_uppercase().is_in(["TRUE", "1", "YES"])).alias(c))
        else:
            cols.append(e.cast(pl.Utf8).alias(c))
    return m.select(cols).filter(pl.col("Invoice No").is_not_null())


def merge_master(old: pl.DataFrame, new: pl.DataFrame):
    """New data wins; a blank in the new data never erases an old value.
    Orders missing from today's input stay in the master untouched.
    A PENDING-<order id> row is dropped once that order shows up with an invoice."""
    old, new = old.cast(SCHEMA).select(DATA_COLS), new.cast(SCHEMA).select(DATA_COLS)
    old = old.unique("Invoice No", keep="last", maintain_order=True)
    new = new.unique("Invoice No", keep="last", maintain_order=True)
    keys = set(old["Invoice No"].to_list()), set(new["Invoice No"].to_list())
    both = keys[0] & keys[1]
    j = new.join(old, on="Invoice No", how="full", coalesce=True, suffix="_old")
    rts_from_old = pl.col("RTS Time").is_null() & pl.col("RTS Time_old").is_not_null() & pl.col("_in_new")
    merged = (j.with_columns(pl.col("Invoice No").is_in(list(keys[1])).alias("_in_new"))
               .with_columns(*[pl.coalesce(c, f"{c}_old").alias(c) for c in DATA_COLS if c not in ("Invoice No", "RTS Exact")],
                             pl.when(rts_from_old).then(pl.col("RTS Exact_old")).otherwise(pl.coalesce("RTS Exact", "RTS Exact_old"))
                               .alias("RTS Exact"))
               .select(DATA_COLS).sort("Invoice No"))          # pandas' combine_first: the keys in order
    pending = pl.col("Invoice No").str.starts_with(PENDING_PREFIX)
    invoiced = set(merged.filter(~pending)["Order ID"].drop_nulls().to_list())
    stale = merged.filter(pending & pl.col("Invoice No").str.slice(len(PENDING_PREFIX)).is_in(sorted(invoiced)))
    merged = merged.filter(~pl.col("Invoice No").is_in(stale["Invoice No"].to_list()))
    # one row per AJIO order: if an order id still shows up twice, keep the invoiced / newest row
    ranked = (merged.with_row_index("_i").filter(pl.col("Order ID").is_not_null() & ~pl.col("Order ID").is_in(["", "nan", "None"]))
                    .with_columns(pending.alias("_pending"))
                    .sort(["_pending", "Last Updated"], descending=[False, True], nulls_last=True, maintain_order=True))
    drop = ranked.filter(pl.int_range(pl.len()).over("Order ID") > 0)["_i"].to_list()
    out = merged.with_row_index("_i").filter(~pl.col("_i").is_in(drop)).drop("_i")
    stats = {"new": len(keys[1] - keys[0]), "updated": len(both), "kept (not in input)": len(keys[0] - keys[1]),
             "pending rows replaced by invoice": stale.height, "duplicates removed": len(drop)}
    return out, stats


def apply_tracking(m: pl.DataFrame, summ: pl.DataFrame, ev: pl.DataFrame) -> pl.DataFrame:
    """Fill pickup scans / courier status from this run's tracking into master rows,
    including orders whose OMS page was not re-read. Known pickup times are never changed."""
    if not m.height or not summ.height:
        return m
    awb = pl.col("AWB").cast(pl.Utf8).fill_null("nan")
    pk = pickup_times(ev).unique("AWB", keep="first", maintain_order=True).select(
        pl.col("AWB").alias("_a"), pl.col("Pickup Time").alias("_pt"), pl.col("Pickup Attempt Time").alias("_pa"))
    st = summ.unique("AWB", keep="first", maintain_order=True).select(pl.col("AWB").alias("_a"), pl.col("STATUS").cast(pl.Utf8).alias("_st"))
    known = pl.col("_st").is_not_null() & ~pl.col("_st").is_in(["UNKNOWN", "NOT_FOUND", "", "nan"])
    return (m.with_columns(awb.alias("_a")).join(pk, on="_a", how="left", maintain_order="left").join(st, on="_a", how="left", maintain_order="left")
             .with_columns(pl.coalesce("Pickup Time", "_pt").alias("Pickup Time"), pl.coalesce("Pickup Attempt Time", "_pa").alias("Pickup Attempt Time"),
                           pl.when(known).then(pl.col("_st")).otherwise(pl.col("Courier Status")).alias("Courier Status"))
             .drop("_a", "_pt", "_pa", "_st"))


def needs_oms_refresh() -> pl.Expr:
    """True for orders whose OMS data can still change: not invoiced, not processed, or not picked up."""
    return (pl.col("Invoice No").cast(pl.Utf8).fill_null("nan").str.starts_with(PENDING_PREFIX)
            | pl.col("RTS Time").is_null() | pl.col("Pickup Status").is_in(list(OPEN_PICKUP)).fill_null(False))


def ready_time() -> pl.Expr:
    """When the parcel was ready for the courier: RTS time if it has a clock time,
    else the processed (invoice) time. Dispatch Log RTS values are date-only."""
    exact = pl.col("RTS Exact").fill_null(False)
    return pl.when(pl.col("RTS Time").is_not_null() & exact).then(pl.col("RTS Time")).otherwise(pl.col("Processed Time"))


def apply_status(df: pl.DataFrame, as_of: datetime) -> pl.DataFrame:
    dl = pl.col("Dispatch Deadline")
    today = datetime.combine(as_of.date(), time())
    # processing is due by the END of the due date (10:10 rule); only the pickup is due by the
    # courier's pickup time (Promise Ship Date). Until 29 Oct 2026 processing was held to the
    # pickup time too: an order after 10 AM processed the next afternoon read "Late".
    due = dl.dt.truncate("1d").dt.offset_by("23h59m59s")
    rts, pick = pl.col("RTS Time"), pl.col("Pickup Time")
    on_time = lambda cond: pl.when(cond.fill_null(False)).then(pl.lit("On Time")).otherwise(pl.lit("Late"))  # noqa: E731
    process = (pl.when(rts.is_null() & pick.is_null()).then(pl.lit("Not Processed"))
                 .when(rts.is_null()).then(on_time(pick <= due)).otherwise(on_time(rts <= due)))
    item, courier = pl.col("OMS Item Status").cast(pl.Utf8).fill_null(""), pl.col("Courier Status").cast(pl.Utf8)
    ready = ready_time()
    pickup = (pl.when(pick.is_not_null()).then(on_time(pick <= dl))
                .when(item.str.contains(_ci(CANCEL_ITEM_STATUSES)) | (courier == "CANCELLED").fill_null(False)).then(pl.lit("Cancelled"))
                .when(~courier.fill_null("None").is_in(sorted(NOT_PICKED_COURIER_STATUSES)) | item.str.contains(_ci(PICKED_ITEM_STATUSES)))
                .then(pl.lit("Picked (Time N/A)"))
                # processed in today's second half: the courier collects it on tomorrow's pickup
                .when((ready.dt.truncate("1d") == today).fill_null(False) & (ready.dt.time() >= NEXT_DAY_AFTER).fill_null(False))
                .then(pl.lit(NEXT_DAY_PICKUP)).otherwise(pl.lit("Pending Pickup")))
    df = df.with_columns(process.alias("Process Status"), pickup.alias("Pickup Status"))
    p, k = pl.col("Process Status"), pl.col("Pickup Status")
    result = (pl.when(k == "Cancelled").then(pl.lit("CANCELLED"))
                .when(k.is_in(list(OPEN_PICKUP)) & (pl.lit(as_of) <= dl).fill_null(False)).then(pl.lit("PENDING"))
                .when((p != "On Time") | k.is_in(["Late", *OPEN_PICKUP])).then(pl.lit("NOT CORRECT"))
                .when(k == "Picked (Time N/A)").then(pl.lit("CHECK")).otherwise(pl.lit("CORRECT")))
    label = pl.col("ERP Label Time").is_not_null() if "ERP Label Time" in df.columns else pl.lit(False)
    return (df.with_columns(result.alias("TAT Result"), pl.when(label).then(pl.lit("YES")).otherwise(pl.lit("NO")).alias("Label Printed"))
              .sort("Order Time", nulls_last=True, maintain_order=True))


def apply_erp_labels(df: pl.DataFrame, labels: dict) -> tuple[pl.DataFrame, int]:
    """ERP shipping-label prints into the master: labels = {AWB: (print time, printed by)}.
    A label time already in the master is kept (the first print counts)."""
    lab = pl.DataFrame({"_a": list(labels), "_t": [v[0] for v in labels.values()], "_b": [v[1] for v in labels.values()]},
                       schema={"_a": pl.Utf8, "_t": pl.Utf8, "_b": pl.Utf8}, strict=False)
    lab = lab.with_columns(parse_when(pl.col("_t")).alias("_t"))
    j = (df.with_columns(pl.col("AWB").cast(pl.Utf8).fill_null("nan").str.strip_chars().str.to_uppercase().alias("_a"))
           .join(lab, on="_a", how="left", maintain_order="left"))
    todo = pl.col("ERP Label Time").is_null() & pl.col("_b").is_not_null()
    n = int(j.select(todo.sum()).item())
    out = j.with_columns(pl.when(todo).then(pl.col("_t")).otherwise(pl.col("ERP Label Time")).alias("ERP Label Time"),
                         pl.when(todo).then(pl.col("_b")).otherwise(pl.col("ERP Label By")).alias("ERP Label By")).drop("_a", "_t", "_b")
    return out, n


# ----------------------------------------------------------------- summaries

TAT_RESULTS = ["CORRECT", "NOT CORRECT", "CHECK", "PENDING", "CANCELLED"]
PROCESS_RESULTS = ["On Time", "Late", "Not Processed"]
PICKUP_RESULTS = ["On Time", "Late", "Pending Pickup", NEXT_DAY_PICKUP, "Picked (Time N/A)", "Cancelled"]


def pct(a, b):
    return a / b if b else 0.0


def _counts(df: pl.DataFrame, col: str) -> dict:
    return dict(df.group_by(col).len().iter_rows()) if df.height else {}


def summarize(df: pl.DataFrame) -> dict:
    """Counts used by the Sheet Summary tab and the Telegram message."""
    res, proc, pick = _counts(df, "TAT Result"), _counts(df, "Process Status"), _counts(df, "Pickup Status")
    couriers = []
    by = df.with_columns(pl.col("Courier").fill_null("UNKNOWN").alias("_c"))
    for courier in sorted(by["_c"].unique().to_list()) if df.height else []:
        pk = _counts(by.filter(pl.col("_c") == courier), "Pickup Status")
        on, late, pend = pk.get("On Time", 0), pk.get("Late", 0), pk.get("Pending Pickup", 0)
        couriers.append({"Courier": courier, "Orders": by.filter(pl.col("_c") == courier).height, "Pickup On Time": on,
                         "Pickup Late": late, "Pending Pickup": pend,
                         "Picked (Time N/A)": pk.get("Picked (Time N/A)", 0),
                         "On Time %": pct(on, on + late + pend)})
    return {
        "total": df.height,
        "tat": {k: int(res.get(k, 0)) for k in TAT_RESULTS},
        "process": {k: int(proc.get(k, 0)) for k in PROCESS_RESULTS},
        "pickup": {k: int(pick.get(k, 0)) for k in PICKUP_RESULTS},
        "tat_pct": pct(res.get("CORRECT", 0), res.get("CORRECT", 0) + res.get("NOT CORRECT", 0)),
        "pickup_pct": pct(pick.get("On Time", 0),
                          pick.get("On Time", 0) + pick.get("Late", 0) + pick.get("Pending Pickup", 0)),
        "couriers": couriers,
    }


# ------------------------------------------------------------ local xlsx copy

FILLS = {"On Time": "#C6EFCE", "CORRECT": "#C6EFCE",
         "Late": "#FFC7CE", "Pending Pickup": "#FFC7CE", "Not Processed": "#FFC7CE", "NOT CORRECT": "#FFC7CE",
         "Picked (Time N/A)": "#FFEB9C", "CHECK": "#FFEB9C", "Pending": "#FFEB9C", "PENDING": "#FFEB9C",
         NEXT_DAY_PICKUP: "#FFEB9C",
         "Cancelled": "#E7E6E6", "CANCELLED": "#E7E6E6", "YES": "#C6EFCE", "NO": "#FFC7CE"}
WIDTHS = {"Invoice No": 11, "Order ID": 13, "AWB": 18, "Courier": 12, "Process Status": 14,
          "Pickup Status": 13, "TAT Result": 14}
CLOCK_COLS = ["Order Time", "Dispatch Deadline", "Processed Time", "RTS Time", "Pickup Attempt Time", "Pickup Time",
              "ERP Label Time"]


def _write(ws, i, j, v, f=None):
    if v is None or v == "" or (isinstance(v, float) and v != v):     # an empty text is an empty cell
        if f is not None:
            ws.write_blank(i, j, None, f)
    elif isinstance(v, bool):
        ws.write_boolean(i, j, v, f)
    elif isinstance(v, datetime):
        ws.write_datetime(i, j, v, f)
    elif isinstance(v, (int, float)):
        ws.write_number(i, j, v, f)
    else:
        ws.write_string(i, j, str(v), f)


def write_excel(data: pl.DataFrame, path, source_note, as_of, title=None, rule=None):
    """The master as an xlsx (xlsxwriter): Summary, TAT Report, Late Orders, and the hidden _data (DATA_COLS, read back
    by the next run) and _meta (as of)."""
    import xlsxwriter
    from xlsxwriter.utility import xl_col_to_name
    report = data.select([pl.col(c) if c in data.columns else pl.lit(None).alias(c) for c in REPORT_COLS])
    exact = data["RTS Exact"].fill_null(True).to_list() if "RTS Exact" in data.columns else [True] * data.height
    late_mask = (report["TAT Result"] == "NOT CORRECT").fill_null(False)
    wb = xlsxwriter.Workbook(str(path), {"strings_to_numbers": False, "strings_to_formulas": False, "strings_to_urls": False})
    font = {"font_name": "Arial", "font_size": 10}
    head = wb.add_format({**font, "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "pattern": 1,
                          "text_wrap": True, "valign": "vcenter", "align": "center"})
    plain, clock = wb.add_format(font), wb.add_format({**font, "num_format": "DD-MMM-YY hh:mm AM/PM"})
    day, pct_f = wb.add_format({**font, "num_format": "DD-MMM-YY"}), wb.add_format({**font, "num_format": "0.0%"})
    raw_when = wb.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
    fills = {t: wb.add_format({"bg_color": c, "pattern": 1}) for t, c in FILLS.items()}

    summary_ws = wb.add_worksheet("Summary")
    for name, part, rts_exact in (("TAT Report", report, exact),
                                  ("Late Orders", report.filter(late_mask), [e for e, m in zip(exact, late_mask.to_list()) if m])):
        ws = wb.add_worksheet(name)
        col = {c: j for j, c in enumerate(REPORT_COLS)}
        for j, c in enumerate(REPORT_COLS):
            ws.write_string(0, j, c, head)
            ws.set_column(j, j, WIDTHS.get(c, 20))
        for i, (row, is_exact) in enumerate(zip(part.iter_rows(), rts_exact), start=1):
            for j, v in enumerate(row):
                c = REPORT_COLS[j]
                f = (day if c == "Last Updated" or (c == "RTS Time" and not is_exact) else clock if c in CLOCK_COLS else plain)
                _write(ws, i, j, v, f)
        ws.set_row(0, 30)
        ws.freeze_panes(1, 1)
        ws.autofilter(0, 0, max(part.height, 1), len(REPORT_COLS) - 1)
        for c in STATUS_COLS + ["Label Printed"]:
            letter = xl_col_to_name(col[c])
            rng = f"{letter}2:{letter}{max(part.height + 1, 2)}"
            for text, fill in fills.items():
                ws.conditional_format(rng, {"type": "cell", "criteria": "==", "value": f'"{text}"', "format": fill})

    ws = wb.add_worksheet("_data")
    cols = [c for c in DATA_COLS if c in data.columns] or DATA_COLS
    for j, c in enumerate(cols):
        ws.write_string(0, j, c)
    for i, row in enumerate(data.select(cols).iter_rows() if data.width else [], start=1):
        for j, v in enumerate(row):
            _write(ws, i, j, v, raw_when if isinstance(v, datetime) else None)
    ws.hide()
    ws = wb.add_worksheet("_meta")
    ws.write_string(0, 0, "as_of")
    if as_of is not None:
        _write(ws, 1, 0, as_of, raw_when)
    ws.hide()

    big = wb.add_format({"font_name": "Arial", "font_size": 14, "bold": True})
    for r, row in enumerate(summary_rows(summarize(data), as_of, source_note, title, rule)):
        for j, v in enumerate(row):
            f = big if (r, j) == (0, 0) else pct_f if isinstance(v, float) and 0 <= v <= 1 and j > 0 else plain
            if v == "" or v is None:
                continue
            _write(summary_ws, r, j, v, f)
    for j, w in enumerate((18, 10, 16, 10, 16, 10, 12)):
        summary_ws.set_column(j, j, w)
    summary_ws.activate()
    wb.close()


def summary_rows(s, as_of, source_note, title=None, rule=None):
    """The Summary tab as a plain grid (shared by the Sheet and the xlsx); title / rule: another
    portal's (Flipkart TAT)."""
    rows = [
        [title or "AJIO Dispatch TAT Summary"],
        [rule or "Rule (10:10): order before 10 AM -> dispatch same day; 10 AM or later -> next day. By the courier "
         "pickup time (XB / BlueDart 12:00 PM, Shadowfax / Delhivery 12:30 PM) from 29 Jul 2026, 11:59 PM before."],
        [f"Tracking as of {as_of:%d-%b-%Y %I:%M %p}  |  {source_note}" if as_of is not None
         else f"Tracking time not known  |  {source_note}"],
        [],
        ["TAT Result", "Orders", "Process", "Orders", "Pickup", "Orders"],
    ]
    for i in range(max(len(TAT_RESULTS), len(PICKUP_RESULTS))):
        row = []
        for lst, counts in ((TAT_RESULTS, s["tat"]), (PROCESS_RESULTS, s["process"]),
                            (PICKUP_RESULTS, s["pickup"])):
            row += [lst[i], counts[lst[i]]] if i < len(lst) else ["", ""]
        rows.append(row)
    rows += [
        [],
        ["Total", s["total"]],
        ["TAT %", s["tat_pct"], "Pickup On Time %", s["pickup_pct"]],
        [],
        ["Courier", "Orders", "Pickup On Time", "Pickup Late", "Pending Pickup", "Picked (Time N/A)", "On Time %"],
    ]
    for c in s["couriers"]:
        rows.append([c["Courier"], c["Orders"], c["Pickup On Time"], c["Pickup Late"],
                     c["Pending Pickup"], c["Picked (Time N/A)"], c["On Time %"]])
    rows += [[], ["Picked (Time N/A) / CHECK = courier shows shipment moved or delivered but has no pickup scan "
                  "(Shadowfax, Delhivery). RTS shown as date only = time not available in OMS."],
             [f"{NEXT_DAY_PICKUP} = processed today after {NEXT_DAY_AFTER:%I:%M %p}, courier collects it "
              "tomorrow; not counted as Pending Pickup."]]
    return rows
