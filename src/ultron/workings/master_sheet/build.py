"""MasterData from OMSGuru's channel listings (owner, 24 Nov 2026).

One row per channel listing OMSGuru has (Channel Listings > Download Mapped Channel Listings), keyed on
(Channel Name, Channel Listing SKU Code, Channel Listing Id):

* a listing already on the sheet keeps every value the owner or an earlier run gave it; only the OMSGuru SKU
  (Product SkuCode (Reference Only)) follows OMSGuru, and a blank is filled;
* a new listing gets its columns worked out (derive()): SIZE SKU = OMSGuru's SKU (a listing missing from OMSGuru: its
  listing SKU without the brand code, FSH-DRESS-A-1-L -> DRESS-A-1-L), MY SKU = SIZE SKU without its size,
  MASTER SKU / MASTER STYLE CODE from the owner's "Master Sku" sheet (else SIZE SKU / MY SKU), DESIGN-NO / COLOR /
  LAUNCH DATE / PORTAL LISTING DATE from the other rows of the same style only when they all agree (12% of the
  styles have more than one colour; DESIGN-NO else "Fabric Code", LAUNCH DATE first from "Launch Date & Size Count");
* Brand: a wrong one (a SKU brand code like "FSH", or "Shopsy", a Flipkart marketplace; owner, 24 Nov 2026) or a
  blank one is set from, in order: the portal's file (Myntra listing report, Flipkart listing file), the listing
  title's first words (OMSGuru "Channel Listing Title"; agreed with the owner's Brand on 99% of the rows),
  the same listing SKU on another channel, the brand nearly every row of the listing SKU's prefix has (FSH-
  Fashfun); else blank. A right Brand already on the sheet is never changed;
* portal ids, the portal's own file first, then the value on the sheet, then OMSGuru: Myntra style id / SKU code
  from each account's Myntra listing report (seller SKU code = the listing SKU), Flipkart FSN from the Flipkart
  listing file (else OMSGuru "Extra Param"; OMSGuru's was wrong on 358 of 377 rows where they differed), Amazon
  ASIN (OMSGuru; Amazon: "Extra Data", Amazon DF: the listing id, Amazon Smart: the ASIN of the same listing SKU on
  Amazon), Meesho product id (OMSGuru "Extra Key"), AJIO JIOCODE = the listing id's first 9 digits + "_" + the
  colour (as AJIO writes it: lower case, no spaces);
* a listing OMSGuru no longer has moves to REMOVED LISTINGS (owner: kept so old orders still map), with the day it
  went; one that comes back moves back;
* UNMAPPED LISTINGS (owner, 24 Nov 2026): a listing in a portal's own listing file (Myntra listing reports,
  Flipkart listing file) that OMSGuru does not have, in MasterData's columns.

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
# Myntra channel -> the account whose listing report has its style ids; a listing only in an account's report goes
# to UNMAPPED LISTINGS under the first channel of that account
MYNTRA_ACCOUNT = {"MYNTRA PPMP": "MAIN", "MYNTRA": "MAIN", "MYNTRA FMCC": "FMCC", "MYNTRA DBCC": "DBCC",
                  "MYNTRA EXIM": "EXIM"}
COLUMNS = ["Channel Listing SKU Code", "Channel Listing Id", "Channel Name", "Brand", "Product SkuCode (Reference Only)",
           "MY SKU", "SIZE SKU", "MASTER SKU", "MASTER STYLE CODE", "DESIGN-NO", "LAUNCH DATE", "PORTAL LISTING DATE",
           "MYNTRA STYLE ID", "MYNTRA SKU CODE", "FLIPKART FSN", "MEESHO PRODUCT ID", "MEESHO CATALOG ID",
           "MEESHO PRODUCT IDENTIFIER", "AMAZON ASIN", "AJIO JIOCODE", "COLOR"]
KEY = ["Channel Name", "Channel Listing SKU Code", "Channel Listing Id"]
REMOVED_ON = "REMOVED ON"
OMS_SKU = "Product SkuCode (Reference Only)"
NOT_BRANDS = {"SHOPSY"}             # a marketplace, not a brand (owner, 24 Nov 2026)
TITLE_ALIASES = {"fashfun clothing": "fashfun"}      # AJIO titles: "FASHFUN CLOTHING : Women ..."
PREFIX = r"^([A-Za-z]+)-"
# the extra columns a source frame for derive() may carry (null when it has none)
SOURCE = {"_oms_sku": pl.Utf8, "_brand": pl.Utf8, "_title": pl.Utf8, "_fsn": pl.Utf8, "_asin": pl.Utf8,
          "_meesho": pl.Utf8}


def _txt(col: str) -> pl.Expr:
    """A text column trimmed, an empty text as null (OMSGuru writes '' for nothing, dates as 'yyyy-mm-dd)."""
    c = pl.col(col).cast(pl.Utf8).str.strip_chars().str.strip_chars("'")
    return pl.when(c == "").then(None).otherwise(c)


def channel_of(cid: str, name: str) -> str:
    """MasterData channel name of an OMSGuru channel; a channel not in CHANNELS by its OMSGuru name."""
    return CHANNELS.get(str(cid).strip()) or str(name).split(" - ", 1)[-1].strip().upper()


def from_omsguru(export: pl.DataFrame) -> pl.DataFrame:
    """The export (read_text_csv) as MasterData's OMSGuru columns plus what derive() uses, one row per KEY."""
    ch = [channel_of(c, n) for c, n in zip(export["Channel ID"].to_list(), export["Channel Name"].to_list())]
    title = _txt("Channel Listing Title") if "Channel Listing Title" in export.columns else pl.lit(None, pl.Utf8)
    df = export.with_columns(pl.Series("Channel Name", ch, dtype=pl.Utf8)).select(
        _txt("Channel Listing SKU Code").alias("Channel Listing SKU Code"),
        _txt("Channel Listing Id").alias("Channel Listing Id"),
        pl.col("Channel Name"),
        _txt("Product Brand").alias("_brand"), title.alias("_title"),
        _txt("Product SkuCode").str.to_uppercase().alias("_oms_sku"),
        _txt("Extra Data").alias("_extra_data"), _txt("Extra Key").alias("_extra_key"),
        _txt("Extra Param").alias("_extra_param"))
    df = df.filter(pl.col("Channel Listing SKU Code").is_not_null()).unique(KEY, keep="first", maintain_order=True)
    ch = pl.col("Channel Name")
    return df.with_columns(
        pl.when(ch == "FLIPKART").then(pl.col("_extra_param")).alias("_fsn"),
        pl.when(ch == "AMAZON").then(pl.col("_extra_data"))
          .when(ch == "AMAZON DF").then(pl.col("Channel Listing Id")).alias("_asin"),
        pl.when(ch == "MEESHO").then(pl.col("_extra_key")).alias("_meesho")
    ).drop("_extra_data", "_extra_key", "_extra_param")


def myntra_ids(reports: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """(account, seller sku code) -> style id, sku code, sku id, brand, from each account's Myntra listing report."""
    need = {"seller sku code", "style id", "sku code"}
    frames = [r.select(pl.lit(acc).alias("_account"), _txt("seller sku code").alias("Channel Listing SKU Code"),
                       _txt("style id").alias("_style"), _txt("sku code").alias("_sku_code"),
                       (_txt("sku id") if "sku id" in r.columns else pl.lit(None, pl.Utf8)).alias("_sku_id"),
                       (_txt("brand") if "brand" in r.columns else pl.lit(None, pl.Utf8)).alias("_mbrand"))
              for acc, r in reports.items() if r.height and need <= set(r.columns)]
    if not frames:
        return pl.DataFrame(schema={"_account": pl.Utf8, "Channel Listing SKU Code": pl.Utf8, "_style": pl.Utf8,
                                    "_sku_code": pl.Utf8, "_sku_id": pl.Utf8, "_mbrand": pl.Utf8})
    return pl.concat(frames).drop_nulls("Channel Listing SKU Code").unique(["_account", "Channel Listing SKU Code"],
                                                                            keep="first", maintain_order=True)


def flipkart_ids(listing_file: pl.DataFrame | None) -> pl.DataFrame:
    """Seller SKU -> FSN, listing id, brand, title from the Flipkart listing file (Seller Hub's own listings)."""
    schema = {"Channel Listing SKU Code": pl.Utf8, "_fk_fsn": pl.Utf8, "_fk_listing": pl.Utf8, "_fk_brand": pl.Utf8,
              "_fk_title": pl.Utf8}
    if listing_file is None or not {"Seller SKU Id", "Flipkart Serial Number"} <= set(listing_file.columns):
        return pl.DataFrame(schema=schema)
    col = lambda c: _txt(c) if c in listing_file.columns else pl.lit(None, pl.Utf8)  # noqa: E731
    return (listing_file.select(_txt("Seller SKU Id").alias("Channel Listing SKU Code"),
                                col("Flipkart Serial Number").alias("_fk_fsn"), col("Listing ID").alias("_fk_listing"),
                                col("Brand").alias("_fk_brand"), col("Title").alias("_fk_title"))
                        .drop_nulls("Channel Listing SKU Code")
                        .unique("Channel Listing SKU Code", keep="first", maintain_order=True))


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


class Context:
    """What derive() looks things up in: the sheet's rows (MasterData + REMOVED LISTINGS), the owner's sheets and
    the portal files, worked out once."""

    def __init__(self, old_all: pl.DataFrame, sheets: dict[str, pl.DataFrame], myntra: pl.DataFrame | None,
                 flipkart: pl.DataFrame | None):
        style = "MASTER STYLE CODE"
        self.myntra, self.flipkart = myntra, flipkart_ids(flipkart)
        # brand codes: listing SKU prefixes the sheet drops to get the SKU (FSH-DRESS-A-1-L -> DRESS-A-1-L) on at least
        # 90% of their rows; DRESS- / COORD- are part of the SKU, not codes
        pre = old_all.select(pl.col("Channel Listing SKU Code").str.extract(PREFIX, 1).str.to_uppercase().alias("p"),
                             (pl.col("Channel Listing SKU Code").str.replace(PREFIX, "").str.to_uppercase()
                              == pl.col("SIZE SKU").str.to_uppercase()).fill_null(False).alias("drop")).drop_nulls("p")
        self.brand_codes = set(pre.group_by("p").agg(pl.col("drop").mean().alias("s"), pl.len().alias("n"))
                               .filter((pl.col("s") >= 0.9) & (pl.col("n") >= 5))["p"].to_list())
        # what a Brand cell must not be: a prefix whose rows mostly carry another brand (FSH rows: Fashfun), so a
        # brand that is also a prefix (LEIA- rows: LEIA) stays a brand; and NOT_BRANDS
        top = (old_all.select(pl.col("Channel Listing SKU Code").str.extract(PREFIX, 1).str.to_uppercase().alias("p"),
                              "Brand").drop_nulls()
               .filter(~pl.col("Brand").str.to_uppercase().is_in(sorted(NOT_BRANDS)))
               .group_by("p", "Brand").len().sort("len", descending=True).unique("p", keep="first"))
        self.codes = {p for p, b in zip(top["p"], top["Brand"]) if b.upper() != p} | NOT_BRANDS
        valid = old_all.filter(self.is_brand(pl.col("Brand")))
        self.brands = sorted({b for b in valid["Brand"].to_list()}, key=len, reverse=True)
        known = old_all.filter(pl.col(style).is_not_null())
        ms = sheets.get("Master Sku")
        self.master_sku = _lookup(ms, "SIZE SKU", "MASTER SKU", "_ms", "SIZE SKU").join(
            _lookup(ms, "SIZE SKU", "MASTER STYLE CODE", "_msc", "SIZE SKU"), on="SIZE SKU", how="left")
        self.style = (_mode_by(known, style, "DESIGN-NO").join(_mode_by(known, style, "COLOR"), on=style, how="full",
                                                                 coalesce=True)
                      .join(_mode_by(known, style, "LAUNCH DATE"), on=style, how="full", coalesce=True)
                      .join(_lookup(sheets.get("Fabric Code"), "SKU", "FABRCI CODE", "_fabric", style), on=style,
                            how="full", coalesce=True)
                      .join(_lookup(sheets.get("Launch Date & Size Count"), "SKU", "DATE", "_launch", style), on=style,
                            how="full", coalesce=True))
        self.listing_date = _mode_by(known.with_columns(pl.concat_str("Channel Name", style, separator="|").alias("_cs")),
                                     "_cs", "PORTAL LISTING DATE")
        self.same_sku_brand = _mode_by(valid, "Channel Listing SKU Code", "Brand").rename({"_m_Brand": "_sku_brand"})
        # a prefix's brand when at least 95% of its rows with a right brand have it
        by_prefix = (valid.with_columns(pl.col("Channel Listing SKU Code").str.extract(PREFIX, 1).str.to_uppercase()
                                        .alias("_prefix")).drop_nulls("_prefix")
                     .group_by("_prefix", "Brand").len())
        self.prefix_brand = (by_prefix.with_columns((pl.col("len") / pl.col("len").sum().over("_prefix")).alias("_s"))
                             .filter(pl.col("_s") >= 0.95).select("_prefix", pl.col("Brand").alias("_prefix_brand")))

    def is_brand(self, e: pl.Expr) -> pl.Expr:
        return e.is_not_null() & ~e.str.to_uppercase().is_in(sorted(self.codes))

    def title_brand(self, titles: list) -> list:
        out = []
        for t in titles:
            t = (t or "").lower()
            for alias, name in TITLE_ALIASES.items():
                t = t.replace(alias, name)
            out.append(next((b for b in self.brands if t.startswith(b.lower())), None))
        return out


def derive(df: pl.DataFrame, ctx: Context, cols: list[str]) -> pl.DataFrame:
    """df: KEY + the sheet's columns (null for a new listing) + SOURCE columns -> MasterData's columns filled."""
    df = df.with_columns(pl.lit(None, t).alias(c) for c, t in SOURCE.items() if c not in df.columns)
    df = df.with_columns(pl.lit(None, pl.Utf8).alias(c) for c in cols if c not in df.columns)
    is_new = pl.col("MY SKU").is_null() & pl.col("SIZE SKU").is_null() & pl.col("MASTER SKU").is_null()
    df = df.with_columns(is_new.alias("_new"))
    style = "MASTER STYLE CODE"

    df = df.with_columns(pl.when("_new").then(pl.coalesce("_oms_sku", "Channel Listing SKU Code"))
                           .otherwise(pl.col("SIZE SKU")).alias("SIZE SKU"))
    df = df.with_columns(pl.when("_new").then(pl.col("SIZE SKU").str.replace(r"-[^-]+$", "")).otherwise(pl.col("MY SKU"))
                           .alias("MY SKU"))
    df = df.join(ctx.master_sku, on="SIZE SKU", how="left").with_columns(
        pl.when("_new").then(pl.coalesce("_ms", "SIZE SKU")).otherwise(pl.col("MASTER SKU")).alias("MASTER SKU"),
        pl.when("_new").then(pl.coalesce("_msc", "MY SKU")).otherwise(pl.col(style)).alias(style))
    df = (df.join(ctx.style, on=style, how="left")
            .with_columns(pl.concat_str("Channel Name", style, separator="|").alias("_cs"))
            .join(ctx.listing_date, on="_cs", how="left"))
    fill = {"DESIGN-NO": pl.coalesce("_m_DESIGN-NO", "_fabric"), "COLOR": pl.col("_m_COLOR"),
            "LAUNCH DATE": pl.coalesce("_launch", "_m_LAUNCH DATE"), "PORTAL LISTING DATE": pl.col("_m_PORTAL LISTING DATE")}
    df = df.with_columns(pl.coalesce(c, e).alias(c) for c, e in fill.items())
    df = df.with_columns(pl.coalesce("_oms_sku", OMS_SKU).alias(OMS_SKU))

    # portal files
    df = df.join(ctx.flipkart, on="Channel Listing SKU Code", how="left")
    df = df.with_columns(pl.col("Channel Name").replace_strict(MYNTRA_ACCOUNT, default=None, return_dtype=pl.Utf8)
                         .alias("_account"))
    if ctx.myntra is not None:
        df = df.join(ctx.myntra, on=["_account", "Channel Listing SKU Code"], how="left")
    else:
        df = df.with_columns(pl.lit(None, pl.Utf8).alias(c) for c in ("_style", "_sku_code", "_sku_id", "_mbrand"))
    myntra_row, flipkart_row = pl.col("_account").is_not_null(), pl.col("Channel Name") == "FLIPKART"

    # Brand: a right one stays; else portal file, title, same listing SKU elsewhere, the prefix's brand
    df = (df.with_columns(pl.Series("_tbrand", ctx.title_brand(df["_title"].to_list()), dtype=pl.Utf8),
                          pl.Series("_fk_tbrand", ctx.title_brand(df["_fk_title"].to_list()), dtype=pl.Utf8),
                          pl.col("Channel Listing SKU Code").str.extract(PREFIX, 1).str.to_uppercase().alias("_prefix"))
            .join(ctx.same_sku_brand, on="Channel Listing SKU Code", how="left")
            .join(ctx.prefix_brand, on="_prefix", how="left"))
    right = lambda c: pl.when(ctx.is_brand(pl.col(c))).then(pl.col(c))  # noqa: E731
    portal_brand = pl.when(myntra_row).then(right("_mbrand")).when(flipkart_row).then(
        pl.coalesce(right("_fk_brand"), pl.col("_fk_tbrand")))
    df = df.with_columns(pl.when(ctx.is_brand(pl.col("Brand"))).then(pl.col("Brand"))
                           .otherwise(pl.coalesce(portal_brand, "_tbrand", "_sku_brand", "_prefix_brand"))
                           .alias("Brand"))

    # ids: the portal's file, then the sheet, then OMSGuru
    df = df.with_columns(
        pl.when(flipkart_row).then(pl.coalesce("_fk_fsn", "FLIPKART FSN", "_fsn")).otherwise(pl.col("FLIPKART FSN"))
          .alias("FLIPKART FSN"),
        pl.when(myntra_row).then(pl.coalesce("_style", "MYNTRA STYLE ID")).otherwise(pl.col("MYNTRA STYLE ID"))
          .alias("MYNTRA STYLE ID"),
        pl.when(myntra_row).then(pl.coalesce("_sku_code", "MYNTRA SKU CODE")).otherwise(pl.col("MYNTRA SKU CODE"))
          .alias("MYNTRA SKU CODE"),
        pl.coalesce("MEESHO PRODUCT ID", "_meesho").alias("MEESHO PRODUCT ID"),
        pl.coalesce("AMAZON ASIN", "_asin").alias("AMAZON ASIN"))
    amazon = (df.filter((pl.col("Channel Name") == "AMAZON") & pl.col("AMAZON ASIN").is_not_null())
                .unique("Channel Listing SKU Code", keep="first")
                .select("Channel Listing SKU Code", pl.col("AMAZON ASIN").alias("_amz")))
    df = df.join(amazon, on="Channel Listing SKU Code", how="left").with_columns(
        pl.when(pl.col("Channel Name") == "AMAZON SMART").then(pl.coalesce("AMAZON ASIN", "_amz"))
          .otherwise(pl.col("AMAZON ASIN")).alias("AMAZON ASIN"))
    colour = pl.col("COLOR").str.to_lowercase().str.replace_all(r"\s+", "")
    df = df.with_columns(
        pl.when(pl.col("Channel Name").is_in(["AJIO", "AJIO API"]) & pl.col("AJIO JIOCODE").is_null()
                & pl.col("Channel Listing Id").str.contains(r"^\d{12}$") & pl.col("COLOR").is_not_null())
          .then(pl.col("Channel Listing Id").str.slice(0, 9) + "_" + colour)
          .otherwise(pl.col("AJIO JIOCODE")).alias("AJIO JIOCODE"))
    return df


def unmapped(oms: pl.DataFrame, ctx: Context, old_all: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    """Listings in the portals' own files that OMSGuru does not have, as MasterData rows (owner, 24 Nov 2026)."""
    frames = []
    if ctx.myntra is not None and ctx.myntra.height:
        channel_of_account = {}
        for ch, acc in MYNTRA_ACCOUNT.items():
            channel_of_account.setdefault(acc, ch)
        have = oms.with_columns(pl.col("Channel Name").replace_strict(MYNTRA_ACCOUNT, default=None,
                                                                      return_dtype=pl.Utf8).alias("_account")
                                ).drop_nulls("_account").select("_account", "Channel Listing SKU Code").unique()
        miss = ctx.myntra.join(have, on=["_account", "Channel Listing SKU Code"], how="anti")
        frames.append(miss.select("Channel Listing SKU Code", pl.col("_sku_id").alias("Channel Listing Id"),
                                  pl.col("_account").replace_strict(channel_of_account, default=None,
                                                                    return_dtype=pl.Utf8).alias("Channel Name")))
    if ctx.flipkart.height:
        have = oms.filter(pl.col("Channel Name") == "FLIPKART").select("Channel Listing SKU Code").unique()
        miss = ctx.flipkart.join(have, on="Channel Listing SKU Code", how="anti")
        frames.append(miss.select("Channel Listing SKU Code", pl.col("_fk_listing").alias("Channel Listing Id"),
                                  pl.lit("FLIPKART").alias("Channel Name")))
    if not frames:
        return pl.DataFrame(schema={c: pl.Utf8 for c in cols})
    rows = pl.concat(frames).unique(KEY, keep="first", maintain_order=True)
    # a listing the sheet already knows (any channel) keeps its SKU columns; else its SKU without the brand code
    sku_cols = ["MY SKU", "SIZE SKU", "MASTER SKU", "MASTER STYLE CODE"]
    known = old_all.drop_nulls("SIZE SKU").unique("Channel Listing SKU Code", keep="first").select(
        "Channel Listing SKU Code", *sku_cols)
    rows = rows.join(known, on="Channel Listing SKU Code", how="left")
    code = pl.col("Channel Listing SKU Code").str.extract(PREFIX, 1).str.to_uppercase()
    bare = pl.when(code.is_in(sorted(ctx.brand_codes))).then(
        pl.col("Channel Listing SKU Code").str.replace(PREFIX, "")).otherwise(pl.col("Channel Listing SKU Code"))
    rows = rows.with_columns(bare.str.to_uppercase().alias("_oms_sku"))
    return derive(rows, ctx, cols).select(cols)


def rebuild(old: pl.DataFrame, removed: pl.DataFrame | None, oms: pl.DataFrame, sheets: dict[str, pl.DataFrame],
            myntra: pl.DataFrame | None, today: date,
            flipkart: pl.DataFrame | None = None) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, dict]:
    """(MasterData, REMOVED LISTINGS, UNMAPPED LISTINGS, counts). old / removed: the sheets as text
    (read_excel_text); oms: from_omsguru(); sheets: the owner's "Master Sku", "Fabric Code", "Launch Date & Size
    Count"; myntra: myntra_ids() or None when the Myntra reports could not be read (the ids then stay as they were);
    flipkart: the Flipkart listing file (read_excel_text) or None."""
    cols = [c for c in (old.columns if old.width else COLUMNS)]
    cols += [c for c in COLUMNS if c not in cols]
    old = old.with_columns(pl.lit(None, pl.Utf8).alias(c) for c in cols if c not in old.columns).select(cols)
    removed = removed if removed is not None and removed.width else pl.DataFrame(schema={c: pl.Utf8 for c in cols})
    removed = removed.with_columns(pl.lit(None, pl.Utf8).alias(c) for c in cols + [REMOVED_ON] if c not in removed.columns)
    old_all = pl.concat([old.with_columns(pl.lit(None, pl.Utf8).alias(REMOVED_ON)).select(cols + [REMOVED_ON]),
                         removed.select(cols + [REMOVED_ON])], how="vertical_relaxed")
    old_all = old_all.with_columns(_txt(c).alias(c) for c in KEY).unique(KEY, keep="first", maintain_order=True)
    ctx = Context(old_all, sheets, myntra, flipkart)

    joined = derive(oms.join(old_all, on=KEY, how="left"), ctx, cols)
    data = joined.select(cols)
    gone = old_all.join(oms.select(KEY), on=KEY, how="anti").with_columns(
        pl.coalesce(REMOVED_ON, pl.lit(today.isoformat())).alias(REMOVED_ON)).select(cols + [REMOVED_ON])
    loose = unmapped(oms, ctx, old_all, cols)
    came_back = joined.filter(pl.col(REMOVED_ON).is_not_null()).height
    counts = {"listings": data.height, "new": joined.filter("_new").height,
              "kept": joined.filter(~pl.col("_new")).height - came_back, "back": came_back,
              "removed_today": gone.filter(pl.col(REMOVED_ON) == today.isoformat()).height, "removed_total": gone.height,
              "unmapped": loose.height, "no_brand": data.filter(pl.col("Brand").is_null()).height,
              "no_design": data.filter(pl.col("DESIGN-NO").is_null()).height,
              "new_no_design": joined.filter(pl.col("_new") & pl.col("DESIGN-NO").is_null()).height,
              "channels": dict(data.group_by("Channel Name").len().sort("Channel Name").iter_rows())}
    return data, gone, loose, counts
