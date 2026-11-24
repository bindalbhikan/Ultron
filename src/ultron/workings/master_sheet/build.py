"""MasterData from OMSGuru's channel listings (owner, 24 Nov 2026).

One row per channel listing OMSGuru has (Channel Listings > Download Mapped Channel Listings), keyed on
(Channel Name, Channel Listing SKU Code, Channel Listing Id):

* a listing already on the sheet keeps every value the owner or an earlier run gave it; only the OMSGuru SKU
  (Product SkuCode (Reference Only)) and the portal ids a source gives today are refreshed, and an empty Brand is
  filled from OMSGuru;
* a new listing gets its columns worked out: SIZE SKU = OMSGuru's SKU, MY SKU = SIZE SKU without its size,
  MASTER SKU / MASTER STYLE CODE from the owner's "Master Sku" sheet (else SIZE SKU / MY SKU), DESIGN-NO / COLOR
  / LAUNCH DATE / PORTAL LISTING DATE from the other rows of the same style (DESIGN-NO else "Fabric Code",
  LAUNCH DATE first from "Launch Date & Size Count");
* portal ids, the portal's own file first, then the value on the sheet, then OMSGuru: Myntra style id / SKU code
  from each account's Myntra listing report (seller SKU code = the listing SKU), Flipkart FSN from the Flipkart
  listing file (else OMSGuru "Extra Param"), Amazon ASIN (OMSGuru; Amazon: "Extra Data", Amazon DF: the listing
  id, Amazon Smart: the ASIN of the same listing SKU on Amazon), Meesho product id (OMSGuru "Extra Key"), AJIO
  JIOCODE = the listing id's first 9 digits + "_" + the colour (as AJIO writes it: lower case, no spaces);
* DESIGN-NO / COLOR / LAUNCH DATE / PORTAL LISTING DATE are copied from the same style only when all its rows
  agree (12% of the styles have more than one colour);
* a listing OMSGuru no longer has moves to REMOVED LISTINGS (owner: kept so old orders still map), with the day
  it went; one that comes back moves back.

Nothing is guessed: a value no source gives stays empty.
"""
from __future__ import annotations

from datetime import date

import polars as pl

# OMSGuru channel id -> MasterData channel name (checked against the owner's sheet, 24 Nov 2026)
CHANNELS = {"39078": "MYNTRA PPMP", "45111": "MYNTRA", "49234": "MYNTRA FMCC", "47460": "MYNTRA DBCC",
            "64106": "MYNTRA EXIM", "37863": "FLIPKART", "57285": "AJIO API", "34958": "AJIO", "37864": "MEESHO",
            "37862": "AMAZON", "41766": "AMAZON SMART", "39049": "AMAZON DF", "43200": "LIMEROAD",
            "46428": "SNAPDEAL", "57692": "NYKAA", "63052": "COCOBLU"}
# Myntra channel -> the account whose listing report has its style ids
MYNTRA_ACCOUNT = {"MYNTRA PPMP": "MAIN", "MYNTRA": "MAIN", "MYNTRA FMCC": "FMCC", "MYNTRA DBCC": "DBCC",
                  "MYNTRA EXIM": "EXIM"}
COLUMNS = ["Channel Listing SKU Code", "Channel Listing Id", "Channel Name", "Brand", "Product SkuCode (Reference Only)",
           "MY SKU", "SIZE SKU", "MASTER SKU", "MASTER STYLE CODE", "DESIGN-NO", "LAUNCH DATE", "PORTAL LISTING DATE",
           "MYNTRA STYLE ID", "MYNTRA SKU CODE", "FLIPKART FSN", "MEESHO PRODUCT ID", "MEESHO CATALOG ID",
           "MEESHO PRODUCT IDENTIFIER", "AMAZON ASIN", "AJIO JIOCODE", "COLOR"]
KEY = ["Channel Name", "Channel Listing SKU Code", "Channel Listing Id"]
IDS = ["MYNTRA STYLE ID", "MYNTRA SKU CODE", "FLIPKART FSN", "MEESHO PRODUCT ID", "AMAZON ASIN"]
REMOVED_ON = "REMOVED ON"
OMS_SKU = "Product SkuCode (Reference Only)"


def _txt(col: str) -> pl.Expr:
    """A text column trimmed, an empty text as null (OMSGuru writes '' for nothing, dates as 'yyyy-mm-dd)."""
    c = pl.col(col).cast(pl.Utf8).str.strip_chars().str.strip_chars("'")
    return pl.when(c == "").then(None).otherwise(c)


def channel_of(cid: str, name: str) -> str:
    """MasterData channel name of an OMSGuru channel; a channel not in CHANNELS by its OMSGuru name."""
    return CHANNELS.get(str(cid).strip()) or str(name).split(" - ", 1)[-1].strip().upper()


def from_omsguru(export: pl.DataFrame) -> pl.DataFrame:
    """The export (read_text_csv) as MasterData's OMSGuru columns plus the ids it carries, one row per KEY."""
    ch = [channel_of(c, n) for c, n in zip(export["Channel ID"].to_list(), export["Channel Name"].to_list())]
    df = export.with_columns(pl.Series("Channel Name", ch, dtype=pl.Utf8)).select(
        _txt("Channel Listing SKU Code").alias("Channel Listing SKU Code"),
        _txt("Channel Listing Id").alias("Channel Listing Id"),
        pl.col("Channel Name"),
        _txt("Product Brand").alias("_brand"),
        _txt("Product SkuCode").str.to_uppercase().alias("_oms_sku"),
        _txt("Extra Data").alias("_extra_data"), _txt("Extra Key").alias("_extra_key"),
        _txt("Extra Param").alias("_extra_param"))
    df = df.filter(pl.col("Channel Listing SKU Code").is_not_null()).unique(KEY, keep="first", maintain_order=True)
    ch = pl.col("Channel Name")
    return df.with_columns(
        pl.when(ch == "FLIPKART").then(pl.col("_extra_param")).alias("_fsn"),
        pl.when(ch == "AMAZON").then(pl.col("_extra_data"))
          .when(ch == "AMAZON DF").then(pl.col("Channel Listing Id")).alias("_asin"),
        pl.when(ch == "MEESHO").then(pl.col("_extra_key")).alias("_meesho"))


def myntra_ids(reports: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """(account, seller sku code) -> style id, sku code, from each account's Myntra listing report."""
    frames = [r.select(pl.lit(acc).alias("_account"), _txt("seller sku code").alias("Channel Listing SKU Code"),
                       _txt("style id").alias("_style"), _txt("sku code").alias("_sku_code"))
              for acc, r in reports.items() if r.height and {"seller sku code", "style id", "sku code"} <= set(r.columns)]
    if not frames:
        return pl.DataFrame(schema={"_account": pl.Utf8, "Channel Listing SKU Code": pl.Utf8, "_style": pl.Utf8,
                                    "_sku_code": pl.Utf8})
    return pl.concat(frames).drop_nulls("Channel Listing SKU Code").unique(["_account", "Channel Listing SKU Code"],
                                                                            keep="first", maintain_order=True)


def flipkart_ids(listing_file: pl.DataFrame | None) -> pl.DataFrame:
    """Seller SKU -> FSN from the Flipkart listing file (flipkart-listing-file, Seller Hub's own listings)."""
    if listing_file is None or not {"Seller SKU Id", "Flipkart Serial Number"} <= set(listing_file.columns):
        return pl.DataFrame(schema={"Channel Listing SKU Code": pl.Utf8, "_fk_fsn": pl.Utf8})
    return (listing_file.select(_txt("Seller SKU Id").alias("Channel Listing SKU Code"),
                                _txt("Flipkart Serial Number").alias("_fk_fsn"))
                        .drop_nulls().unique("Channel Listing SKU Code", keep="first", maintain_order=True))


def _mode_by(df: pl.DataFrame, key: str, col: str) -> pl.DataFrame:
    """key -> col, only for a key whose rows all have the same value (a style with two colours gives none)."""
    return (df.filter(pl.col(key).is_not_null() & pl.col(col).is_not_null())
              .group_by(key, maintain_order=True).agg(pl.col(col).unique().alias("_v"))
              .filter(pl.col("_v").list.len() == 1)
              .select(key, pl.col("_v").list.first().alias(f"_m_{col}")))


def _lookup(sheet: pl.DataFrame, key: str, col: str, alias: str, as_key: str) -> pl.DataFrame:
    if sheet is None or not sheet.height or key not in sheet.columns or col not in sheet.columns:
        return pl.DataFrame(schema={as_key: pl.Utf8, alias: pl.Utf8})
    return (sheet.select(_txt(key).alias(as_key), _txt(col).alias(alias)).drop_nulls(as_key)
                 .unique(as_key, keep="first", maintain_order=True))


def rebuild(old: pl.DataFrame, removed: pl.DataFrame, oms: pl.DataFrame, sheets: dict[str, pl.DataFrame],
            myntra: pl.DataFrame | None, today: date,
            flipkart: pl.DataFrame | None = None) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """(MasterData, REMOVED LISTINGS, counts). old / removed: the sheets as text (read_excel_text); oms:
    from_omsguru(); sheets: the owner's "Master Sku", "Fabric Code", "Launch Date & Size Count"; myntra: myntra_ids()
    or None when the Myntra reports could not be read (the ids then stay as they were); flipkart: flipkart_ids().
    An id: the portal's own file first, then the value on the sheet, then OMSGuru's (OMSGuru's FSN was the wrong
    one on 358 of the 377 rows where the two differed, 24 Nov 2026)."""
    cols = [c for c in (old.columns if old.width else COLUMNS)]
    cols += [c for c in COLUMNS if c not in cols]
    old = old.with_columns(pl.lit(None, pl.Utf8).alias(c) for c in cols if c not in old.columns).select(cols)
    removed = (removed if removed is not None and removed.width else pl.DataFrame(schema={c: pl.Utf8 for c in cols}))
    removed = removed.with_columns(pl.lit(None, pl.Utf8).alias(c) for c in cols + [REMOVED_ON] if c not in removed.columns)
    old_all = pl.concat([old.with_columns(pl.lit(None, pl.Utf8).alias(REMOVED_ON)).select(cols + [REMOVED_ON]),
                         removed.select(cols + [REMOVED_ON])], how="vertical_relaxed")
    old_all = old_all.with_columns(_txt(c).alias(c) for c in KEY).unique(KEY, keep="first", maintain_order=True)

    joined = oms.join(old_all, on=KEY, how="left")
    is_new = pl.col("MY SKU").is_null() & pl.col("SIZE SKU").is_null() & pl.col("MASTER SKU").is_null()
    joined = joined.with_columns(is_new.alias("_new"))

    # columns of a new listing, from its OMSGuru SKU and the owner's sheets
    size = pl.coalesce("_oms_sku", "Channel Listing SKU Code")
    joined = joined.with_columns(
        pl.when("_new").then(size).otherwise(pl.col("SIZE SKU")).alias("SIZE SKU"))
    joined = joined.with_columns(
        pl.when(pl.col("_new")).then(pl.col("SIZE SKU").str.replace(r"-[^-]+$", "")).otherwise(pl.col("MY SKU")).alias("MY SKU"))
    master_sku = _lookup(sheets.get("Master Sku"), "SIZE SKU", "MASTER SKU", "_ms", "SIZE SKU").join(
        _lookup(sheets.get("Master Sku"), "SIZE SKU", "MASTER STYLE CODE", "_msc", "SIZE SKU"), on="SIZE SKU", how="left")
    joined = joined.join(master_sku, on="SIZE SKU", how="left").with_columns(
        pl.when("_new").then(pl.coalesce("_ms", "SIZE SKU")).otherwise(pl.col("MASTER SKU")).alias("MASTER SKU"),
        pl.when("_new").then(pl.coalesce("_msc", "MY SKU")).otherwise(pl.col("MASTER STYLE CODE")).alias("MASTER STYLE CODE"))

    style = "MASTER STYLE CODE"
    known = old_all.filter(pl.col(style).is_not_null())
    fabric = _lookup(sheets.get("Fabric Code"), "SKU", "FABRCI CODE", "_fabric", style)
    launch = _lookup(sheets.get("Launch Date & Size Count"), "SKU", "DATE", "_launch", style)
    joined = (joined.join(_mode_by(known, style, "DESIGN-NO"), on=style, how="left")
                    .join(_mode_by(known, style, "COLOR"), on=style, how="left")
                    .join(_mode_by(known, style, "LAUNCH DATE"), on=style, how="left")
                    .join(fabric, on=style, how="left").join(launch, on=style, how="left"))
    listing_date = (known.with_columns(pl.concat_str("Channel Name", style, separator="|").alias("_cs"))
                    .pipe(_mode_by, "_cs", "PORTAL LISTING DATE"))
    joined = joined.with_columns(pl.concat_str("Channel Name", style, separator="|").alias("_cs")).join(
        listing_date, on="_cs", how="left")
    # Brand by the listing SKU's prefix (FSH- Fashfun, LEA- LEIA ...), as the sheet's rows of that prefix all have it;
    # OMSGuru's own brand field holds codes ("FSH") or nothing, so only last
    prefix = pl.col("Channel Listing SKU Code").str.extract(r"^([A-Za-z]+)-", 1).str.to_uppercase()
    brands = _mode_by(known.with_columns(prefix.alias("_prefix")), "_prefix", "Brand")
    joined = joined.with_columns(prefix.alias("_prefix")).join(brands, on="_prefix", how="left")
    fill = {"DESIGN-NO": pl.coalesce("_m_DESIGN-NO", "_fabric"), "COLOR": pl.col("_m_COLOR"),
            "LAUNCH DATE": pl.coalesce("_launch", "_m_LAUNCH DATE"), "PORTAL LISTING DATE": pl.col("_m_PORTAL LISTING DATE"),
            OMS_SKU: pl.col("_oms_sku"), "Brand": pl.coalesce("_m_Brand", "_brand")}
    joined = joined.with_columns(
        pl.when(pl.col("_new") | pl.col(c).is_null()).then(pl.coalesce(c, e) if c not in (OMS_SKU,) else e)
          .otherwise(pl.col(c)).alias(c) for c, e in fill.items())
    # OMSGuru's SKU is a reference: always today's
    joined = joined.with_columns(pl.coalesce("_oms_sku", OMS_SKU).alias(OMS_SKU))

    # portal ids: the portal's file, then the sheet, then OMSGuru
    joined = joined.join(flipkart_ids(flipkart), on="Channel Listing SKU Code", how="left").with_columns(
        pl.when(pl.col("Channel Name") == "FLIPKART").then(pl.coalesce("_fk_fsn", "FLIPKART FSN", "_fsn"))
          .otherwise(pl.col("FLIPKART FSN")).alias("FLIPKART FSN"),
        pl.coalesce("MEESHO PRODUCT ID", "_meesho").alias("MEESHO PRODUCT ID"),
        pl.coalesce("AMAZON ASIN", "_asin").alias("AMAZON ASIN"))
    amazon = (joined.filter((pl.col("Channel Name") == "AMAZON") & pl.col("AMAZON ASIN").is_not_null())
                    .unique("Channel Listing SKU Code", keep="first").select("Channel Listing SKU Code",
                                                                              pl.col("AMAZON ASIN").alias("_amz")))
    joined = joined.join(amazon, on="Channel Listing SKU Code", how="left").with_columns(
        pl.when(pl.col("Channel Name") == "AMAZON SMART").then(pl.coalesce("AMAZON ASIN", "_amz"))
          .otherwise(pl.col("AMAZON ASIN")).alias("AMAZON ASIN"))
    if myntra is not None:
        joined = (joined.with_columns(pl.col("Channel Name").replace_strict(MYNTRA_ACCOUNT, default=None,
                                                                             return_dtype=pl.Utf8).alias("_account"))
                        .join(myntra, on=["_account", "Channel Listing SKU Code"], how="left")
                        .with_columns(pl.coalesce("_style", "MYNTRA STYLE ID").alias("MYNTRA STYLE ID"),
                                      pl.coalesce("_sku_code", "MYNTRA SKU CODE").alias("MYNTRA SKU CODE")))
    colour = pl.col("COLOR").str.to_lowercase().str.replace_all(r"\s+", "")
    jio = pl.col("Channel Listing Id").str.slice(0, 9) + "_" + colour
    joined = joined.with_columns(
        pl.when(pl.col("Channel Name").is_in(["AJIO", "AJIO API"]) & pl.col("AJIO JIOCODE").is_null()
                & pl.col("Channel Listing Id").str.contains(r"^\d{12}$") & pl.col("COLOR").is_not_null())
          .then(jio).otherwise(pl.col("AJIO JIOCODE")).alias("AJIO JIOCODE"))

    data = joined.select(cols)
    gone = old_all.join(oms.select(KEY), on=KEY, how="anti").with_columns(
        pl.coalesce(REMOVED_ON, pl.lit(today.isoformat())).alias(REMOVED_ON)).select(cols + [REMOVED_ON])
    came_back = joined.filter(pl.col(REMOVED_ON).is_not_null()).height
    counts = {"listings": data.height, "new": joined.filter("_new").height,
              "kept": joined.filter(~pl.col("_new")).height - came_back, "back": came_back,
              "removed_today": gone.filter(pl.col(REMOVED_ON) == today.isoformat()).height, "removed_total": gone.height,
              "no_design": data.filter(pl.col("DESIGN-NO").is_null()).height,
              "new_no_design": joined.filter(pl.col("_new") & pl.col("DESIGN-NO").is_null()).height,
              "channels": dict(data.group_by("Channel Name").len().sort("Channel Name").iter_rows())}
    return data, gone, counts
