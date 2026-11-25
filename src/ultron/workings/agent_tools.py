"""Bindal's own Ultron tools (agent.toml [chat] / [watch] tools): read-only checks on the logins
the workings use, and the SKU master (AGENT WORK/MASTER SHEET/MasterSheet.xlsx, core/master_sheet.py), the one
place the agent looks up a SKU, style, design, brand or portal id (owner, 25 Nov 2026)."""
from __future__ import annotations

import re
from pathlib import Path

from ultron.core.llm import tool

from .core.config import env
from .portals import myntra


@tool
def myntra_login_status() -> str:
    """Whether the Myntra partner-portal logins saved on the worker (accounts MAIN, DBCC, FMCC) still
    work: logged in or out, which seller account each is for, when it was saved and when its cookies
    run out. Read-only: it only asks the portal one question per account."""
    lines = []
    for account, partner in myntra.ACCOUNTS.items():
        text = myntra.from_worker(env, account)
        if not text:
            lines.append(f"{account}: no login saved on the worker")
            continue
        try:
            session = myntra.parse_session(text)
            portal = myntra.MyntraPortal(session)
            portal.check()
            got = portal.partner_id()
        except myntra.SessionExpired as exc:
            lines.append(f"{account}: LOGGED OUT ({exc})")
            continue
        except Exception as exc:  # noqa: BLE001 - the model reads it
            lines.append(f"{account}: could not check ({type(exc).__name__}: {str(exc)[:150]})")
            continue
        ends, saved = session.expires(), session.saved_at
        who = "the right account" if got == partner else f"partner {got}, expected {partner}"
        lines.append(f"{account}: logged in ({who})"
                     + (f", saved {saved:%d %b %Y %H:%M}" if saved else "")
                     + (f", cookies run out {ends:%d %b %Y %H:%M}" if ends else ", cookie expiry unknown"))
    lines.append("A logged-out account needs a new login: python scripts/myntra/myntra_session.py on the owner's PC.")
    return "\n".join(lines)


_master: dict = {}
# the MasterSheet columns a code can be in (any of them is looked up)
ID_COLUMNS = ["Channel Listing SKU Code", "Channel Listing Id", "Product SkuCode (Reference Only)", "MY SKU", "SIZE SKU",
              "MASTER SKU", "MASTER STYLE CODE", "DESIGN-NO", "MYNTRA STYLE ID", "MYNTRA SKU CODE", "FLIPKART FSN",
              "MEESHO PRODUCT ID", "MEESHO CATALOG ID", "MEESHO PRODUCT IDENTIFIER", "AMAZON ASIN", "AJIO JIOCODE"]
SHOW = ["Channel Name", "Channel Listing SKU Code", "Brand", "MASTER SKU", "MASTER STYLE CODE", "MY SKU", "SIZE SKU",
        "DESIGN-NO", "COLOR", "LAUNCH DATE", "MYNTRA STYLE ID", "FLIPKART FSN", "AMAZON ASIN", "AJIO JIOCODE",
        "MEESHO PRODUCT ID", "REMOVED ON"]


def _master_frame():
    """MasterData + UNMAPPED + REMOVED LISTINGS (core/master_sheet.read), from the local copy while it is Drive's file."""
    from ultron.core.paths import output_root

    from .core import master_sheet as ms
    path = ms.download(output_root() / "cache" / "master_sheet")
    stamp = (str(path), Path(path).stat().st_mtime)
    if _master.get("stamp") != stamp:
        _master.update(stamp=stamp, frame=ms.read(path))
    return _master["frame"]


def _table(df) -> str:
    import polars as pl
    with pl.Config(tbl_rows=40, tbl_cols=20, fmt_str_lengths=40, tbl_width_chars=250):
        return str(df)


@tool
def sku_lookup(code: str) -> str:
    """Look up a SKU, style or product in the SKU master (MasterSheet, the one SKU master every working uses): the
    channel listings that carry it with their brand, MASTER SKU, MASTER STYLE CODE, design no, colour, launch date and
    portal ids (Myntra style id, Flipkart FSN, Amazon ASIN, AJIO JIOCODE, Meesho id). A row with REMOVED ON is a
    listing OMSGuru no longer has. Use this before any other source for SKU / style / brand / design questions.

    Args:
        code: any code as the owner gave it: listing SKU, OMSGuru SKU, MY SKU, MASTER SKU, style code, design no,
            Myntra style id, FSN, ASIN, JIOCODE or Meesho id (part of a code also works).
    """
    import polars as pl
    try:
        df = _master_frame()
    except Exception as exc:  # noqa: BLE001 - the model reads it
        return f"MasterSheet could not be read ({type(exc).__name__}: {str(exc)[:200]})"
    want = code.strip().upper()
    if not want:
        return "Give a code to look up."
    cols = [c for c in ID_COLUMNS if c in df.columns]
    text = [pl.col(c).cast(pl.Utf8).str.strip_chars().str.to_uppercase() for c in cols]
    hit = df.filter(pl.any_horizontal([t == want for t in text]))
    how = "exact"
    if hit.is_empty():
        hit = df.filter(pl.any_horizontal([t.str.contains(re.escape(want)) for t in text]))
        how = "contains"
    if hit.is_empty():
        return f"{code!r} is not in the MasterSheet (MASTER DATA, UNMAPPED and REMOVED LISTINGS searched)."
    shown = hit.select([c for c in SHOW if c in hit.columns]).head(40)
    shown = shown.select([c for c in shown.columns if shown[c].null_count() < shown.height])   # empty ids left out
    return (f"MasterSheet: {hit.height} listing(s) match {code!r} ({how})"
            + (", first 40 shown" if hit.height > 40 else "") + "\n" + _table(shown))


@tool
def master_sheet_query(sql: str) -> str:
    """Any other question on the SKU master (MasterSheet), as one read-only SQL query over the table `master`, one row
    per channel listing. Columns: "Channel Name" (MYNTRA, MYNTRA PPMP, MYNTRA DBCC, MYNTRA FMCC, MYNTRA EXIM, FLIPKART,
    AJIO API, MEESHO, AMAZON ...), "Channel Listing SKU Code", "Channel Listing Id", Brand,
    "Product SkuCode (Reference Only)" (OMSGuru SKU), "MY SKU", "SIZE SKU", "MASTER SKU", "MASTER STYLE CODE",
    "DESIGN-NO", "LAUNCH DATE", "PORTAL LISTING DATE", "MYNTRA STYLE ID", "MYNTRA SKU CODE", "FLIPKART FSN",
    "MEESHO PRODUCT ID", "MEESHO CATALOG ID", "AMAZON ASIN", "AJIO JIOCODE", COLOR, "REMOVED ON" (set: no longer in
    OMSGuru). All columns are text. Up to 50 rows come back.

    Args:
        sql: e.g. SELECT Brand, COUNT(DISTINCT "MASTER STYLE CODE") AS styles FROM master WHERE "REMOVED ON" IS NULL GROUP BY Brand
    """
    import polars as pl
    if not re.match(r"^\s*(select|with)\b", sql, re.I) or ";" in sql.strip().rstrip(";"):
        return "Error: one SELECT query only."
    try:
        df = _master_frame()
    except Exception as exc:  # noqa: BLE001 - the model reads it
        return f"MasterSheet could not be read ({type(exc).__name__}: {str(exc)[:200]})"
    if "REMOVED ON" not in df.columns:
        df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias("REMOVED ON"))
    try:
        out = pl.SQLContext(master=df, eager=True).execute(sql.strip().rstrip(";")).head(50)
    except Exception as exc:  # noqa: BLE001 - the model reads the error and fixes its query
        return f"Error: {type(exc).__name__}: {str(exc)[:300]}"
    return _table(out)


TOOLS = [myntra_login_status, sku_lookup, master_sheet_query]
