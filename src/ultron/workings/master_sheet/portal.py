"""Resolve portal exports against the channel and listing identifiers used by the SKU master."""
import re
from pathlib import Path

import polars as pl

from .build import (CHANNELS, COLUMNS, HEADERS, KEY, MYNTRA_ACCOUNT, PORTAL_HEADERS,
                    _norm, _txt, family, strip_colour_from_sku)

CHANNEL, SKU, ID = KEY
SELLER_KEYS = ("channellistingskucode", "sellerskucode", "sellerskuid", "sellersku", "vendorskucode", "sku")
LISTING_IDS = {"MYNTRA": "skuid", "FLIPKART": "listingid", "NYKAA": "nykaaskucode",
               "AJIO": "jiocode", "AMAZON": "listingid", "SNAPDEAL": "supc"}


def listing_rows(frames, known):
    out, notes = [], []
    styles = {Path(n).stem.upper().removeprefix("MYNTRA-STYLE-"): f for n, f in frames
              if n.upper().startswith("MYNTRA-STYLE-") and "STYLE ID" in f.columns}
    families = {c.split()[0] for c in CHANNELS.values()}
    for name, frame in frames:
        source = re.split(r"[^A-Z]", name.upper())[0]
        if name.upper().startswith("MYNTRA-STYLE-"):
            continue
        cols = {_norm(c): c for c in frame.columns}
        key = next((cols[k] for k in SELLER_KEYS if k in cols), None)
        listing = cols.get(LISTING_IDS.get(source, "")) or cols.get("channellistingid")
        if source == "MEESHO" and {"styleid", "variation", "productid"} <= cols.keys():
            frame = frame.with_columns(
                pl.concat_str(_txt(cols["styleid"]), _txt(cols["variation"]), separator="-").alias("_seller"),
                pl.concat_str(_txt(cols["productid"]), _txt(cols["variation"]), separator="_").alias("_listing"))
            # Also apply colour stripping and size normalization to the constructed SKU
            frame = frame.with_columns(
                pl.col("_seller").map_elements(lambda s: strip_colour_from_sku(s), return_dtype=pl.Utf8).alias("_seller"))
            key, listing = "_seller", "_listing"
        if source == "SNAPDEAL":
            key = cols.get("skucode")
        if source not in families or not key:
            # Older files with unfamiliar headings can still be identified by their listing SKUs.
            best = (0, None, None)
            for (fam,), group in known.group_by(family(pl.col(CHANNEL))):
                if source in families and fam != source:
                    continue
                have = set(group[SKU].drop_nulls().str.to_uppercase())
                for col in ([key] if key else frame.columns):
                    hits = len(set(frame[col].cast(pl.String).drop_nulls().str.to_uppercase()) & have)
                    if hits > best[0]:
                        best = (hits, fam, col)
            if best[0] < max(5, frame.height * .2):
                notes.append(f"PORTAL SHEET {name}: no identifiable listing SKU")
                continue
            _, source, key = best
        channel = source
        pool = known.filter(family(pl.col(CHANNEL)) == source)
        if source == "MYNTRA":
            account = Path(name).stem.upper().split("-")[-1]
            channels = [c for c, a in MYNTRA_ACCOUNT.items() if a == account]
            if channels:
                channel, pool = channels[0], pool.filter(pl.col(CHANNEL).is_in(channels))
            if account in styles and "styleid" in cols:
                style = styles[account].rename({c: "STYLE " + c for c in styles[account].columns if c != "STYLE ID"})
                frame = frame.join(style, left_on=cols["styleid"], right_on="STYLE ID", how="left")
                cols.update({_norm(c): c for c in style.columns if c.startswith("STYLE ") and c in frame.columns})
        fields = {**{_norm(c): c for c in COLUMNS if c not in KEY}, **HEADERS, **PORTAL_HEADERS.get(source, {})}
        if source == "MYNTRA":
            fields["stylecolor"] = "COLOR"
        fields.update({"meeshoproductidentifier": "MEESHO PRODUCT IDENTIFIER"})
        raw = [pl.col(c).cast(pl.String).alias(f"{source} / {c}") for c in frame.columns if not c.startswith("_")]
        mapped = {target: cols[h] for h, target in fields.items() if h in cols}
        pid = _txt(listing) if listing else pl.lit(None, pl.String)
        rows = frame.select(_txt(key).alias("_sku"), pid.alias("_id"), *raw,
                            *(_txt(c).alias(t) for t, c in mapped.items())).filter(
                                pl.col("_sku").is_not_null() | pl.col("_id").is_not_null())
        rows = rows.with_columns(pl.col("_sku").str.to_uppercase().alias("_upper"))
        multiple = rows.group_by("_upper").agg(pl.col("_id").drop_nulls().n_unique().alias("_count")).filter(
            pl.col("_count") > 1).select("_upper")
        for col, ref, tag in [(ID, "_id", "id"), (SKU, "_upper", "sku")]:
            norm = pl.col(col) if col == ID else pl.col(col).str.to_uppercase()
            candidates = pool.with_columns(norm.alias(ref)).drop_nulls(ref)
            candidates = candidates.filter((pl.col(CHANNEL) == channel) |
                                           ~(pl.col(CHANNEL) == channel).any().over(ref))
            lookup = candidates.group_by(ref).agg(
                *(pl.col(k).first().alias(f"_{tag}{i}") for i, k in enumerate(KEY)), pl.len().alias("_n")
            ).filter(pl.col("_n") == 1).drop("_n")
            if tag == "sku":
                lookup = lookup.join(multiple, on="_upper", how="anti")
            rows = rows.join(lookup, on=ref, how="left")
        # A seller may reuse a SKU for a different listing. Distinct known
        # listing ids identify distinct rows even if only one appears today.
        conflict = (pl.col("_id") != pl.col("_sku2")).fill_null(False)
        rows = rows.with_columns(pl.when(~conflict).then(pl.col(f"_sku{i}")).alias(f"_sku{i}") for i in range(3))
        resolved = rows.select(*(
            pl.coalesce(f"_id{i}", f"_sku{i}", fallback).alias(k)
            for i, (k, fallback) in enumerate(zip(KEY, [pl.lit(channel), pl.col("_sku"), pl.col("_id")]))),
            *(c for c in rows.columns if not c.startswith("_")))
        # Multiple warehouses can report the same listing in one export. Keep the
        # source values together, in file order, when a source column varies.
        raw_cols = [c for c in resolved.columns if " / " in c]
        summary = [pl.when(pl.col(c).drop_nulls().n_unique() > 1)
                   .then(pl.col(c).fill_null("").str.join("\n"))
                   .otherwise(pl.col(c).drop_nulls().first()).alias(c) for c in raw_cols]
        out.append(resolved.group_by(KEY, maintain_order=True).agg(
            *summary, *(pl.when(pl.col(c).drop_nulls().n_unique() == 1).then(pl.col(c).drop_nulls().first()).alias(c) for c in mapped)))
        notes.append(f"PORTAL SHEET {name}: {source}, {rows.height:,} listing rows")
    if not out:
        return None, notes
    data = pl.concat(out, how="diagonal_relaxed")
    return data.group_by(KEY, maintain_order=True).agg(pl.exclude(KEY).drop_nulls().last()), notes
