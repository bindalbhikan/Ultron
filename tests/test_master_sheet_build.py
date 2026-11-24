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
    data, gone, _, counts = build.rebuild(old, None, oms, {}, None, TODAY)
    rows = {r["Channel Listing SKU Code"]: r for r in data.to_dicts()}
    kept, new = rows["FSH-DRESS-A-1-L"], rows["FSH-DRESS-A-1-M"]
    assert kept["FLIPKART FSN"] == "FSN_SHEET"                 # the sheet's id before OMSGuru's
    assert kept["DESIGN-NO"] == "D-1" and kept["Brand"] == "Fashfun"
    assert new["SIZE SKU"] == "DRESS-A-1-M" and new["MY SKU"] == "DRESS-A-1" and new["MASTER STYLE CODE"] == "DRESS-A-1"
    assert new["DESIGN-NO"] == "D-1" and new["COLOR"] == "Red"   # from the same style
    assert new["Brand"] is None                                 # only a portal sheet names a brand, not OMSGuru's "FSH"
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
    data, gone, _, counts = build.rebuild(_old([]), removed, build.from_omsguru(export), {}, None, TODAY, listing_file)
    assert data["FLIPKART FSN"].to_list() == ["FSN_PORTAL"]
    assert gone.height == 0 and counts["back"] == 1


def test_same_style_value_only_when_all_rows_agree():
    export = _export([("37863", "X - Flipkart", "FSH-TOP-B-1-M", "LST9", "TOP-B-1-M", "", "", "", "")])
    old = _old([{"Channel Listing SKU Code": f"FSH-TOP-B-1-{s}", "Channel Listing Id": f"L{s}", "Channel Name": "FLIPKART",
                 "MY SKU": "TOP-B-1", "SIZE SKU": f"TOP-B-1-{s}", "MASTER SKU": f"TOP-B-1-{s}",
                 "MASTER STYLE CODE": "TOP-B-1", "COLOR": c} for s, c in (("S", "Red"), ("L", "Blue"))])
    data, _, _, _ = build.rebuild(old, None, build.from_omsguru(export), {}, None, TODAY)
    assert data["COLOR"].to_list() == [None]                    # two colours on the style: no guess


def _sheet_rows(n=6, prefix="FSH", brand="Fashfun", channel="AJIO"):
    """n rows of a brand whose listing SKU is its code + the SKU, as the owner's sheet has them."""
    return [{"Channel Listing SKU Code": f"{prefix}-DRESS-Q-1-{i}", "Channel Listing Id": f"{prefix}{i}",
             "Channel Name": channel, "Brand": brand, "MY SKU": "DRESS-Q-1", "SIZE SKU": f"DRESS-Q-1-{i}",
             "MASTER SKU": f"DRESS-Q-1-{i}", "MASTER STYLE CODE": "DRESS-Q-1"} for i in range(n)]


def test_brand_only_from_the_portal_sheet():
    export = _export([
        ("37864", "X - Meesho", "FSH-DRESS-Q-1-9", "M9", "DRESS-Q-1-9", "FSH", "", "", ""),          # new, no portal
        ("37863", "X - Flipkart", "SY-HD-1-M", "LSTSY", "HD-1-M", "", "", "", ""),                   # Shopsy on sheet
        ("34958", "X - Ajio", "FSH-DRESS-Q-1-0", "FSH0", "DRESS-Q-1-0", "", "", "", ""),             # right: kept
        ("64106", "X - MYNTRA EXIM", "TOP-CU-A33-L", "E1", "TOP-CU-A33-L", "FSH", "", "", ""),       # report: Chemistry
    ]).with_columns(pl.Series("Channel Listing Title", ["Fashfun Dress", "", "Murcia Women Dress", "Fashfun Top"]))
    old = _old(_sheet_rows() + [
        {"Channel Listing SKU Code": "SY-HD-1-M", "Channel Listing Id": "LSTSY", "Channel Name": "FLIPKART",
         "Brand": "Shopsy", "MY SKU": "HD-1", "SIZE SKU": "HD-1-M", "MASTER SKU": "HD-1-M", "MASTER STYLE CODE": "HD-1"},
        {"Channel Listing SKU Code": "TOP-CU-A33-L", "Channel Listing Id": "E1", "Channel Name": "MYNTRA EXIM",
         "Brand": "Fashfun", "MY SKU": "TOP-CU-A33", "SIZE SKU": "TOP-CU-A33-L", "MASTER SKU": "TOP-CU-A33-L",
         "MASTER STYLE CODE": "TOP-CU-A33"}])
    myntra = build.myntra_ids({"EXIM": pl.DataFrame({"seller sku code": ["TOP-CU-A33-L"], "style id": ["48506126"],
                                                      "sku code": ["X1"], "brand": ["Chemistry"]})})
    data, _, _, _ = build.rebuild(old, None, build.from_omsguru(export), {}, myntra, TODAY)
    brand = dict(zip(data["Channel Listing SKU Code"], data["Brand"]))
    assert brand["TOP-CU-A33-L"] == "Chemistry"              # Myntra's report wins over the sheet's "Fashfun"
    assert brand["FSH-DRESS-Q-1-9"] is None                  # no portal sheet: not from OMSGuru, title or prefix
    assert brand["SY-HD-1-M"] is None                        # Shopsy is no brand, and no portal sheet names one
    assert brand["FSH-DRESS-Q-1-0"] == "Fashfun"             # a right brand on the sheet stays


def test_portal_file_found_by_its_skus_and_need_data_names_the_file():
    rows = [("37864", "X - Meesho", f"FSH-DRESS-Q-1-{i}", f"M{i}", f"DRESS-Q-1-{i}", "", "", "", "") for i in range(6)]
    rows += [("37862", "X - Amazon", "FSH-DRESS-Q-1-0", "A0", "DRESS-Q-1-0", "", "", "", "")]   # same SKU on Amazon
    oms = build.from_omsguru(_export(rows))
    # Meesho's own file as it downloads: its headers, the SKU column found by its values
    meesho_file = pl.DataFrame({"Seller SKU ID": [f"fsh-dress-q-1-{i}" for i in range(6)],
                                "Brand Name": ["Fashfun"] * 6, "Catalog ID": ["C77"] * 6, "Style": ["x"] * 6})
    given, notes = build.given_rows([("meesho.csv", meesho_file)], oms)
    assert "MEESHO" in notes[0] and given["_family"].unique().to_list() == ["MEESHO"]
    data, _, _, _ = build.rebuild(_old([]), None, oms, {}, None, TODAY, None, given)
    meesho = data.filter(pl.col("Channel Name") == "MEESHO")
    assert meesho["Brand"].unique().to_list() == ["Fashfun"] and meesho["MEESHO CATALOG ID"].unique().to_list() == ["C77"]
    assert data.filter(pl.col("Channel Name") == "AMAZON")["Brand"].to_list() == [None]   # Meesho's file: Meesho rows only
    need = build.need_data(data)
    assert need.columns == build.NEED_COLUMNS
    by = {r["CHANNEL"]: r for r in need.to_dicts()}
    assert by["MEESHO"]["FILE NEEDED"].startswith("Meesho") and "MEESHO PRODUCT ID 6" in by["MEESHO"]["MISSING"]
    assert "Brand" not in by["MEESHO"]["MISSING"] and by["AMAZON"]["LISTINGS MISSING DATA"] == 1


def test_portal_listing_missing_in_omsguru_is_unmapped():
    export = _export([("34958", "X - Ajio", "FSH-DRESS-Q-1-0", "FSH0", "DRESS-Q-1-0", "", "", "", "")])
    listing_file = pl.DataFrame({"Seller SKU Id": ["FSH-DRESS-Q-1-7", "DRESS-VW-1-L"],
                                 "Flipkart Serial Number": ["FSN7", "FSN8"], "Listing ID": ["LST7", "LST8"],
                                 "Brand": ["Fashfun", "Serein"], "Title": ["", ""]})
    _, _, loose, counts = build.rebuild(_old(_sheet_rows()), None, build.from_omsguru(export), {}, None, TODAY,
                                        listing_file)
    rows = {r["Channel Listing SKU Code"]: r for r in loose.to_dicts()}
    assert counts["unmapped"] == 2 and set(loose.columns) >= set(build.COLUMNS)
    assert rows["FSH-DRESS-Q-1-7"]["SIZE SKU"] == "DRESS-Q-1-7"     # the brand code taken off
    assert rows["DRESS-VW-1-L"]["SIZE SKU"] == "DRESS-VW-1-L"       # DRESS- is part of the SKU
    assert rows["FSH-DRESS-Q-1-7"]["FLIPKART FSN"] == "FSN7" and rows["DRESS-VW-1-L"]["Brand"] == "Serein"
