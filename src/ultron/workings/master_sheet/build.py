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
* Brand comes from portal data, including AJIO inventory filenames, then existing brands and supported SKU patterns.
* portal ids, the portal's own file first, then the value on the sheet, then OMSGuru: Myntra style id / SKU code
  from each account's Myntra listing report (seller SKU code = the listing SKU), Flipkart FSN from the Flipkart
  listing file (else OMSGuru "Extra Param"; OMSGuru's was wrong on 358 of 377 rows where they differed), Amazon
  ASIN (OMSGuru; Amazon: "Extra Data", Amazon DF: the listing id, Amazon Smart: the ASIN of the same listing SKU on
  Amazon), Meesho product id (OMSGuru "Extra Key"), AJIO JIOCODE = the listing id's first 9 digits + "_" + the
  colour (as AJIO writes it: lower case, no spaces);
* MASTER DATA retains historical listings and includes portal-only listings.
  REMARK contains UNMAPPED for a listing missing from the full OMSGuru export.

Inferred brands are marked and recalculated on each run.
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
NOT_BRANDS = {"SHOPSY", "NULL", "N/A", "NONE", "NAN"}             # a marketplace, not a brand (owner, 24 Nov 2026)
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
        # a portal's brand spelt as the sheet spells it (Flipkart's "FashFun" -> "Fashfun")
        spell = valid.group_by(pl.col("Brand").str.to_lowercase().alias("_low"), "Brand").len().sort(
            "len", descending=True).unique("_low", keep="first")
        self.spelling = dict(zip(spell["_low"].to_list(), spell["Brand"].to_list()))
        known = old_all.filter(pl.col(style).is_not_null())
        ms = sheets.get("MASTER SKU")
        self.master_sku = _lookup(ms, "SIZE SKU", "MASTER SKU", "_ms", "SIZE SKU").join(
            _lookup(ms, "SIZE SKU", "MASTER STYLE CODE", "_msc", "SIZE SKU"), on="SIZE SKU", how="left")
        self.style = (_mode_by(known, style, "DESIGN-NO").join(_mode_by(known, style, "COLOR"), on=style, how="full",
                                                                 coalesce=True)
                      .join(_mode_by(known, style, "LAUNCH DATE"), on=style, how="full", coalesce=True)
                      .join(_lookup(sheets.get("FABRIC CODE"), "SKU", "FABRCI CODE", "_fabric", style), on=style,
                            how="full", coalesce=True)
                      .join(_lookup(sheets.get("LAUNCH DATE & SIZE COUNT"), "SKU", "DATE", "_launch", style), on=style,
                            how="full", coalesce=True))
        self.listing_date = _mode_by(known.with_columns(pl.concat_str("Channel Name", style, separator="|").alias("_cs")),
                                     "_cs", "PORTAL LISTING DATE")

    def is_brand(self, e: pl.Expr) -> pl.Expr:
        return e.is_not_null() & ~e.str.to_uppercase().is_in(sorted(self.codes))

    def spelt(self, e: pl.Expr) -> pl.Expr:
        return pl.coalesce(e.str.to_lowercase().replace_strict(self.spelling, default=None, return_dtype=pl.Utf8), e)


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

    # Brand: the portal's sheet; else the sheet's own when it is a brand (not "FSH" / "Shopsy"); else blank
    portal_brand = pl.when(myntra_row).then(pl.col("_mbrand")).when(flipkart_row).then(pl.col("_fk_brand"))
    kept = pl.when(~pl.col("_new") & ctx.is_brand(pl.col("Brand"))).then(pl.col("Brand"))
    df = df.with_columns(pl.coalesce(ctx.spelt(portal_brand), kept).alias("Brand"))

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


def family(e: pl.Expr) -> pl.Expr:
    """A channel's portal: its name's first word (AMAZON SMART -> AMAZON, AJIO API -> AJIO, MYNTRA PPMP -> MYNTRA)."""
    return e.str.to_uppercase().str.extract(r"^([A-Z]+)", 1)


# A portal file's columns (headers without case, spaces or signs) -> MASTER DATA's; an id only for its own portal
HEADERS = {"brand": "Brand", "brandname": "Brand", "color": "COLOR", "colour": "COLOR", "primarycolor": "COLOR",
           "primarycolour": "COLOR"}
PORTAL_HEADERS = {"AMAZON": {"asin": "AMAZON ASIN", "asin1": "AMAZON ASIN"},
                  "FLIPKART": {"fsn": "FLIPKART FSN", "flipkartserialnumber": "FLIPKART FSN"},
                  "AJIO": {"jiocode": "AJIO JIOCODE"},
                  "MYNTRA": {"styleid": "MYNTRA STYLE ID", "skucode": "MYNTRA SKU CODE"},
                  "MEESHO": {"productid": "MEESHO PRODUCT ID", "catalogid": "MEESHO CATALOG ID",
                             "productidentifier": "MEESHO PRODUCT IDENTIFIER"}}


def _norm(h: str) -> str:
    return "".join(ch for ch in str(h).lower() if ch.isalnum())


def given_rows(frames: list[tuple[str, pl.DataFrame]], listings: pl.DataFrame) -> tuple[pl.DataFrame | None, list[str]]:
    from .portal import listing_rows
    return listing_rows(frames, listings.select(KEY).unique())


def infer_brands(data: pl.DataFrame) -> pl.DataFrame:
    """Fill blanks from independent branded listings. Reuse no guesses as training evidence."""
    sku = pl.col("Channel Listing SKU Code").str.to_uppercase()
    frame = data.with_columns(
        sku.str.replace(r"[-_](?:XXXS|XXS|XS|S|M|L|XL|XXL|XXXL|[2-9]XL)$", "").alias("_listing_style"),
        sku.str.extract(r"^([A-Z]{2,})[-_]", 1).alias("_prefix"))
    frame = frame.with_columns(pl.when(~pl.col("Brand").str.to_uppercase().is_in(sorted(NOT_BRANDS)))
                               .then(pl.col("Brand")).alias("Brand"))
    known = frame.filter(pl.col("Brand").is_not_null())
    guesses = []
    for keys, minimum, shared in [
        (["Channel Name", "_listing_style"], 1, False),
        (["Channel Name", "MASTER STYLE CODE"], 1, False),
        (["_listing_style"], 2, True),
        (["Channel Name", "_prefix"], 5, False),
    ]:
        lookup = known.group_by(keys).agg(
            pl.col("Brand").first().alias("_candidate"),
            pl.col("Brand").str.to_uppercase().n_unique().alias("_brands"),
            pl.col("Channel Name").n_unique().alias("_channels"),
            pl.col("MASTER STYLE CODE").drop_nulls().n_unique().alias("_styles"),
        ).filter(pl.col("_brands") == 1)
        if shared:
            lookup = lookup.filter(pl.col("_channels") >= minimum)
        elif minimum > 1:
            lookup = lookup.filter((pl.col("_styles") >= minimum) &
                                   ~pl.col("_prefix").is_in(["DRESS", "TOP", "COORD", "KURTI", "SHIRT", "NYK", "SY"]))
        name = f"_guess{len(guesses)}"
        frame = frame.join(lookup.select(*keys, pl.col("_candidate").alias(name)), on=keys, how="left")
        guesses.append(name)
    agree = pl.concat_list(guesses).list.drop_nulls().list.unique()
    inferred = pl.when(pl.col("Brand").is_null() & (agree.list.len() == 1)).then(agree.list.first())
    return (frame.with_columns(inferred.alias("INFERRED BRAND"))
            .with_columns(pl.coalesce("Brand", "INFERRED BRAND").alias("Brand"))
            .drop("_listing_style", "_prefix", *guesses))


def apply_given(df: pl.DataFrame, given: pl.DataFrame | None, cols: list[str]) -> pl.DataFrame:
    """The owner's portal files over the worked-out values, on the rows of that portal with that listing SKU; an empty
    cell there changes nothing."""
    if given is None or not given.height:
        return df
    fill = [c for c in given.columns if c in cols and c not in KEY]
    updates = given.select(KEY + fill).rename({c: f"_g_{c}" for c in fill})
    out = df.join(updates, on=KEY, how="left", nulls_equal=True)
    return out.with_columns(pl.coalesce(f"_g_{c}", c).alias(c) for c in fill).drop(
        [f"_g_{c}" for c in fill])


# NEED DATA (owner, 24 Nov 2026: only the portal and the file it needs): per channel, the file that gives what is
# missing, the values a portal file gives (Brand, COLOR, the portal's ids)
PORTAL_FILE = {"MYNTRA": "Myntra listing report (Seller_Listings_Report)",
               "FLIPKART": "Flipkart listing file (Seller Hub, all listings)", "AJIO": "AJIO inventory file",
               "AMAZON": "Amazon listing / inventory report", "MEESHO": "Meesho inventory / catalog file"}
CHANNEL_IDS = {"MYNTRA": ["MYNTRA STYLE ID", "MYNTRA SKU CODE"], "FLIPKART": ["FLIPKART FSN"],
               "AMAZON": ["AMAZON ASIN"], "MEESHO": ["MEESHO PRODUCT ID", "MEESHO CATALOG ID"],
               "AJIO": ["AJIO JIOCODE"]}
FROM_PORTAL = ["Brand", "COLOR"]
NEED_COLUMNS = ["PORTAL", "CHANNEL", "FILE NEEDED", "LISTINGS MISSING DATA", "MISSING"]


def need_data(data: pl.DataFrame) -> pl.DataFrame:
    """One row per channel with listings missing a value a portal file gives: the portal, the file to drop in PORTAL
    SHEET, how many listings, and which values with their counts."""
    rows = []
    for (ch,), g in data.group_by("Channel Name", maintain_order=True):
        fam = str(ch).split(" ")[0].upper()
        cols = FROM_PORTAL + CHANNEL_IDS.get(fam, [])
        gaps = {c: g.filter(pl.col(c).is_null()).height for c in cols if c in g.columns}
        gaps = {c: n for c, n in gaps.items() if n}
        if not gaps:
            continue
        missing = g.filter(pl.any_horizontal(pl.col(c).is_null() for c in gaps)).height
        rows.append({"PORTAL": fam, "CHANNEL": ch,
                     "FILE NEEDED": PORTAL_FILE.get(fam, f"{fam.title()} listing / inventory file"),
                     "LISTINGS MISSING DATA": missing,
                     "MISSING": ", ".join(f"{c} {n:,}" for c, n in gaps.items())})
    return pl.DataFrame(rows, schema={c: (pl.Int64 if c == "LISTINGS MISSING DATA" else pl.Utf8) for c in NEED_COLUMNS}
                        ).sort(["PORTAL", "CHANNEL"])


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
            myntra: pl.DataFrame | None, today: date, flipkart: pl.DataFrame | None = None,
            given: pl.DataFrame | None = None) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, dict]:
    """(MasterData, REMOVED LISTINGS, UNMAPPED LISTINGS, counts). old / removed: the sheets as text
    (read_excel_text); oms: from_omsguru(), all exported channels; sheets: the owner's "Master Sku",
    "Fabric Code", "Launch Date & Size Count"; myntra: myntra_ids() or None when the Myntra reports could not be read
    (the ids then stay as they were); flipkart: the Flipkart listing file (read_excel_text) or None; given:
    given_rows() of the owner's PORTAL SHEET files, over everything else."""
    cols = [c for c in (old.columns if old.width else COLUMNS)]
    if removed is not None:
        cols += [c for c in removed.columns if c != REMOVED_ON]
    # MASTER DATA only keeps the standard columns + REMARK + INFERRED BRAND.
    # Portal-prefixed raw columns (containing " / ") are used only to update
    # standard columns via apply_given, not written as separate columns.
    standard = COLUMNS + ["REMARK", "INFERRED BRAND"]
    cols = list(dict.fromkeys([c for c in cols if c in standard or not (" / " in c)] + standard))
    # A portal-only SKU may acquire its first listing id in a later OMS export.
    # Complete a blank id only when that channel and SKU have one mapped id.
    filled = oms.group_by(KEY[:2]).agg(pl.col(KEY[2]).unique().alias("_ids")).filter(
        pl.col("_ids").list.len() == 1).select(*KEY[:2], pl.col("_ids").list.first().alias("_resolved"))
    def complete_id(frame: pl.DataFrame) -> pl.DataFrame:
        return frame.join(filled, on=KEY[:2], how="left").with_columns(
            pl.coalesce(KEY[2], "_resolved").alias(KEY[2])).drop("_resolved")

    old = complete_id(old)
    if given is not None:
        given = complete_id(given).group_by(KEY, maintain_order=True).agg(pl.exclude(KEY).drop_nulls().last())
    old = old.with_columns(pl.lit(None, pl.Utf8).alias(c) for c in cols if c not in old.columns).select(cols)
    removed = removed if removed is not None and removed.width else pl.DataFrame(schema={c: pl.Utf8 for c in cols})
    removed = removed.with_columns(pl.lit(None, pl.Utf8).alias(c) for c in cols + [REMOVED_ON] if c not in removed.columns)
    old_all = pl.concat([old.with_columns(pl.lit(None, pl.Utf8).alias(REMOVED_ON)).select(cols + [REMOVED_ON]),
                         removed.select(cols + [REMOVED_ON])], how="vertical_relaxed")
    old_all = old_all.with_columns(_txt(c).alias(c) for c in KEY).unique(KEY, keep="first", maintain_order=True)
    if "INFERRED BRAND" in old_all.columns:
        old_all = old_all.with_columns(
            pl.when(pl.col("Brand").eq_missing(pl.col("INFERRED BRAND"))).then(None)
            .otherwise(pl.col("Brand")).alias("Brand"), pl.lit(None, pl.String).alias("INFERRED BRAND"))
    ctx = Context(old_all, sheets, myntra, flipkart)
    known = pl.concat([oms.select(KEY), old_all.select(KEY)]).unique()
    portal = unmapped(known, ctx, old_all, COLUMNS)
    sources = [oms.with_columns(pl.lit(True).alias("_mapped")), portal.select(KEY)]
    if given is not None:
        sources.append(given.select(KEY))
    sources.append(old_all.select(KEY))
    keys = pl.concat(sources, how="diagonal_relaxed").unique(KEY, keep="first", maintain_order=True)
    base = keys.join(old_all.with_columns(pl.lit(True).alias("_known")), on=KEY, how="left", nulls_equal=True)
    # Only supply the derived SKU columns for genuinely new portal listings.
    additions = portal.select(KEY + ["SIZE SKU", "MY SKU", "MASTER SKU", "MASTER STYLE CODE"])
    base = base.update(additions, on=KEY, how="left", include_nulls=False)
    joined = apply_given(derive(base, ctx, cols), given, cols)
    remark = pl.col("REMARK").str.replace(r"(?:^| \| )UNMAPPED$", "").replace("", None)
    joined = joined.with_columns(pl.when(pl.col("_mapped").fill_null(False)).then(remark)
        .otherwise(pl.concat_str(remark, pl.lit("UNMAPPED"), separator=" | ", ignore_nulls=True)).alias("REMARK"))
    data = infer_brands(joined.select(cols))
    if data.height != keys.height or data.select(KEY).n_unique() != keys.height:
        raise ValueError("Listing keys changed during the MasterSheet rebuild")
    loose = data.filter(pl.col("REMARK").str.contains(r"(?:^| \| )UNMAPPED$"))
    gone = removed.select([c for c in removed.columns if " / " not in c])
    came_back = joined.filter(pl.col(REMOVED_ON).is_not_null() & pl.col("_mapped")).height
    counts = {"listings": data.height, "new": joined.filter(pl.col("_known").is_null()).height,
              "kept": joined.filter(pl.col("_known").is_not_null()).height - came_back, "back": came_back,
              "removed_today": 0, "removed_total": gone.height,
              "unmapped": loose.height, "no_brand": data.filter(pl.col("Brand").is_null()).height,
              "no_design": data.filter(pl.col("DESIGN-NO").is_null()).height,
              "new_no_design": joined.filter(pl.col("_new") & pl.col("DESIGN-NO").is_null()).height,
              "channels": dict(data.group_by("Channel Name").len().sort("Channel Name").iter_rows())}
    return data, gone, loose, counts
