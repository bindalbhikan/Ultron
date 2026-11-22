"""Dashboard numbers of a return analysis: per portal (and Myntra combined / all portals) the sale
and return quantities, the return % by month, and the top return reasons, brands, categories
and states. Built from the same rows the reports are built from, so they always agree. Polars;
a top list is "biggest first, equal values A to Z"."""
from __future__ import annotations

from datetime import datetime

import polars as pl

TOP = 8


def _rate(sold, returned) -> float:
    return round(float(returned) / float(sold) * 100, 2) if sold else 0.0


def _labels(df: pl.DataFrame, column: str, aliases: dict | None = None) -> pl.Series:
    """One spelling per value: the same name in other cases / aliases (FashFun, FASHFUN CLOTHING)
    shows as its most common spelling (of equally common ones the smallest), as the combined reports do."""
    t = df.select(pl.col(column).cast(pl.Utf8).fill_null("-").str.strip_chars().alias("v"))
    t = t.with_columns(k=pl.col("v").str.to_lowercase().replace(aliases or {}))
    best = t.group_by("k").agg(pl.col("v").mode().sort().first().alias("b"))
    return t.join(best, on="k", how="left", maintain_order="left")["b"]


def _returned(df: pl.DataFrame) -> pl.Expr:
    return pl.when(pl.col("ORDER STATUS") == "Return").then(pl.col("QTY")).otherwise(0)


def _split(df: pl.DataFrame, column: str, top: int = TOP, min_sold: int = 20) -> list[dict]:
    """Sale qty, return qty and % per value of `column`, biggest sellers first."""
    if column not in df.columns or not df.height:
        return []
    from .engine import BRAND_ALIASES
    labels = _labels(df, column, BRAND_ALIASES if column == "BRAND" else None)
    g = (df.select(labels.alias("name"), pl.col("QTY"), _returned(df).alias("r"))
           .group_by("name").agg(pl.col("QTY").sum(), pl.col("r").sum())
           .filter(pl.col("QTY") >= min_sold).sort("name").sort("QTY", descending=True, maintain_order=True).head(top))
    return [{"name": k, "sold": int(q), "returned": int(r), "rate": _rate(q, r)} for k, q, r in g.iter_rows()]


def _reason(text) -> str:
    """AJIO / Flipkart reason codes read like Myntra's: Does_Not_Look_Good_On_Me -> Does not look
    good on me, FIT_NOT_AS_EXPECTED -> Fit not as expected."""
    t = str(text).strip() if text is not None else ""
    if not t or t.lower() in ("nan", "none", "-"):
        return "Not given"
    if "_" in t or t.isupper():
        t = t.replace("_", " ").strip().lower()
        t = t[:1].upper() + t[1:]
    return t


def _reasons(df: pl.DataFrame, top: int = TOP) -> list[dict]:
    if "RETURN/EXCHANGE REASON" not in df.columns:
        return []
    ret = df.filter(pl.col("ORDER STATUS") == "Return")
    if not ret.height:
        return []
    names = [_reason(r) for r in ret["RETURN/EXCHANGE REASON"].to_list()]
    g = (pl.DataFrame({"name": names, "q": ret["QTY"]}).group_by("name").agg(pl.col("q").sum())
           .sort("name").sort("q", descending=True, maintain_order=True))
    total = int(g["q"].sum())
    return [{"name": k[:60], "qty": int(v), "share": _rate(total, v)} for k, v in g.head(top).iter_rows()]


def _by_month(df: pl.DataFrame) -> list[dict]:
    if "MONTH" not in df.columns or not df.height:
        return []
    out = []
    g = df.filter(pl.col("MONTH").is_not_null()).group_by("MONTH").agg(pl.col("QTY").sum().alias("s"), _returned(df).sum().alias("r"))
    for m, sold, returned in g.iter_rows():
        try:
            key = datetime.strptime(m, "%m-%Y").strftime("%Y-%m")
        except (ValueError, TypeError):
            continue
        out.append({"month": key, "sold": int(sold), "returned": int(returned), "rate": _rate(sold, returned)})
    return sorted(out, key=lambda r: r["month"])


def portal_block(df: pl.DataFrame) -> dict:
    sold = int(df["QTY"].sum())
    returned = int(df.filter(pl.col("ORDER STATUS") == "Return")["QTY"].sum())
    return {"sold": sold, "returned": returned, "rate": _rate(sold, returned),
            "months": _by_month(df), "reasons": _reasons(df), "brands": _split(df, "BRAND"),
            "categories": _split(df, "CATEGORY"), "states": _split(df, "STATE")}


def details(frames: dict[str, pl.DataFrame]) -> dict[str, dict]:
    """Portal name -> block, plus MYNTRA COMBINED and ALL PORTAL when there is more than one."""
    frames = {k: v for k, v in frames.items() if v is not None and v.height}
    out = {}
    for name, df in frames.items():
        try:
            out[name] = portal_block(df)
        except Exception:  # noqa: BLE001 - one odd frame must not cost the others
            continue
    myntra = [df for k, df in frames.items() if k.startswith("MYNTRA")]
    if len(myntra) > 1:
        out["MYNTRA COMBINED"] = portal_block(pl.concat(myntra, how="diagonal_relaxed"))
    if len(frames) > 1:
        out["ALL PORTAL"] = portal_block(pl.concat(list(frames.values()), how="diagonal_relaxed"))
    return out
