"""master-sheet (owner, 24 Nov 2026): MasterData = OMSGuru's listings, old values kept, new rows worked out,
dropped listings moved to REMOVED LISTINGS, a portal file's id before the sheet's before OMSGuru's."""
from datetime import date

import polars as pl

from ultron.workings.master_sheet import build

TODAY = date(2026, 11, 24)


def _export(rows):
    cols = ["Channel ID", "Channel Name", "Channel Listing SKU Code", "Channel Listing Id", "Product SkuCode",
            "Product Brand", "Extra Data", "Extra Key", "Extra Param"]
    return pl.DataFrame([dict(zip(cols, r)) for r in rows], schema={c: pl.Utf8 for c in cols})


def _old(rows):
    return pl.DataFrame([{**dict.fromkeys(build.COLUMNS), **r} for r in rows], schema={c: pl.Utf8 for c in build.COLUMNS})


def test_rebuild_keeps_derives_and_removes():
    export = _export([
        ("37863", "X - Flipkart", "FSH-DRESS-A-1-L", "LST1", "DRESS-A-1-L", "", "", "", "FSN_OMS"),       # kept
        ("37863", "X - Flipkart", "FSH-DRESS-A-1-M", "LST2", "DRESS-A-1-M", "FSH", "", "", "FSN_NEW"),    # new
        ("39049", "X - Amazon DF", "B0ASIN", "B0ASIN", "DRESS-A-1-S", "", "", "", ""),                    # new
    ])
    old = _old([
        {"Channel Listing SKU Code": "FSH-DRESS-A-1-L", "Channel Listing Id": "LST1", "Channel Name": "FLIPKART",
         "Brand": "Fashfun", "MY SKU": "DRESS-A-1", "SIZE SKU": "DRESS-A-1-L", "MASTER SKU": "DRESS-A-1-L",
         "MASTER STYLE CODE": "DRESS-A-1", "DESIGN-NO": "D-1", "COLOR": "Red", "FLIPKART FSN": "FSN_SHEET"},
        {"Channel Listing SKU Code": "OLD-1", "Channel Listing Id": "9", "Channel Name": "MEESHO", "MY SKU": "Z",
         "SIZE SKU": "Z-L", "MASTER SKU": "Z-L", "MASTER STYLE CODE": "Z"},
    ])
    oms = build.from_omsguru(export)
    data, gone, counts = build.rebuild(old, None, oms, {}, None, TODAY)
    rows = {r["Channel Listing SKU Code"]: r for r in data.to_dicts()}
    kept, new = rows["FSH-DRESS-A-1-L"], rows["FSH-DRESS-A-1-M"]
    assert kept["FLIPKART FSN"] == "FSN_SHEET"                 # the sheet's id before OMSGuru's
    assert kept["DESIGN-NO"] == "D-1" and kept["Brand"] == "Fashfun"
    assert new["SIZE SKU"] == "DRESS-A-1-M" and new["MY SKU"] == "DRESS-A-1" and new["MASTER STYLE CODE"] == "DRESS-A-1"
    assert new["DESIGN-NO"] == "D-1" and new["COLOR"] == "Red"   # from the same style
    assert new["Brand"] == "Fashfun"                            # by the listing SKU prefix, not OMSGuru's "FSH"
    assert new["FLIPKART FSN"] == "FSN_NEW"                     # nothing on the sheet: OMSGuru's
    assert rows["B0ASIN"]["AMAZON ASIN"] == "B0ASIN" and rows["B0ASIN"]["Channel Name"] == "AMAZON DF"
    assert gone["Channel Listing SKU Code"].to_list() == ["OLD-1"] and gone[build.REMOVED_ON][0] == "2026-11-24"
    assert counts["new"] == 2 and counts["removed_today"] == 1


def test_portal_file_wins_and_removed_rows_come_back():
    export = _export([("37863", "X - Flipkart", "FSH-DRESS-A-1-L", "LST1", "DRESS-A-1-L", "", "", "", "FSN_OMS")])
    removed = _old([{"Channel Listing SKU Code": "FSH-DRESS-A-1-L", "Channel Listing Id": "LST1",
                     "Channel Name": "FLIPKART", "MY SKU": "DRESS-A-1", "SIZE SKU": "DRESS-A-1-L",
                     "MASTER SKU": "DRESS-A-1-L", "MASTER STYLE CODE": "DRESS-A-1", "FLIPKART FSN": "FSN_SHEET"}]
                   ).with_columns(pl.lit("2026-11-20").alias(build.REMOVED_ON))
    listing_file = pl.DataFrame({"Seller SKU Id": ["FSH-DRESS-A-1-L"], "Flipkart Serial Number": ["FSN_PORTAL"]})
    data, gone, counts = build.rebuild(_old([]), removed, build.from_omsguru(export), {}, None, TODAY, listing_file)
    assert data["FLIPKART FSN"].to_list() == ["FSN_PORTAL"]
    assert gone.height == 0 and counts["back"] == 1


def test_same_style_value_only_when_all_rows_agree():
    export = _export([("37863", "X - Flipkart", "FSH-TOP-B-1-M", "LST9", "TOP-B-1-M", "", "", "", "")])
    old = _old([{"Channel Listing SKU Code": f"FSH-TOP-B-1-{s}", "Channel Listing Id": f"L{s}", "Channel Name": "FLIPKART",
                 "MY SKU": "TOP-B-1", "SIZE SKU": f"TOP-B-1-{s}", "MASTER SKU": f"TOP-B-1-{s}",
                 "MASTER STYLE CODE": "TOP-B-1", "COLOR": c} for s, c in (("S", "Red"), ("L", "Blue"))])
    data, _, _ = build.rebuild(old, None, build.from_omsguru(export), {}, None, TODAY)
    assert data["COLOR"].to_list() == [None]                    # two colours on the style: no guess
