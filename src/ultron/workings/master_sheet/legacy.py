"""Update MasterSheet.xlsx from the marketplace exports in ``input/``.

One job: refresh the master sheet in place.

    python update_master.py

What it does, in order:
  1. Reads the OMS channel-listing export from ``input/`` (loose .csv or zipped).
  2. Reads every marketplace export in the same folder, identifying each one by
     its own header row rather than its filename.
  3. Resolves each listing to a clean MY SKU / SIZE SKU and a brand, built only
     from the channel's own seller SKU -- the Seller SKU Code column in the
     listing files, or the seller SKU the OMS export carries in Channel Listing
     SKU Code. Colour never enters a SKU: it has its own COLOR column, so
     E-18-PINK-M is recorded as the SKU E-18-M.
  4. Adds the listings a marketplace lists but the OMS mapping has not caught up
     with. Everything a channel sells belongs in the master, so these rows are
     added too, with ``Product SkuCode`` left blank -- there is no OMS mapping
     code to record -- and their SKUs read from the listing file's seller SKU.
  5. Writes MasterSheet.xlsx: new listings appended, the resolved
     ``Product SkuCode (Reference Only)``, ``MY SKU`` and ``SIZE SKU`` columns
     re-synced on rows that are already there, blank portal-id cells filled,
     plus a ``Portal Combined`` sheet.
  6. Applies ``supporting/Final Sku Sheet.xlsx`` last. It is the authority
     for FINAL SKU and FINAL MY SKU: every master row whose SIZE SKU (or, for a
     size the sheet does not list, whose MY SKU) appears in it gets its FINAL
     SKU and FINAL MY SKU overwritten from the sheet, and nothing else in the
     run can change those values afterwards. Then ``supporting/Fabric
     Code.xlsx`` fills or corrects DESIGN-NO and ``supporting/Launch
     Dates.xlsx`` fills a blank LAUNCH DATE, both keyed by FINAL MY SKU (or
     MY SKU).
  7. Records the run in ``master.db`` (SQLite): every changed cell with its old
     and new value, every added row, the Final Sku Sheet as read, and the saved
     master. No backup .xlsx is written; ``--undo-last`` reverts the last run.

What it never touches:
  * The manually maintained FINAL SKU, FINAL MY SKU, DESIGN-NO and LAUNCH DATE
    columns, and every portal id or colour already recorded -- except that
    FINAL SKU and FINAL MY SKU always follow ``Final Sku Sheet.xlsx`` where it
    has an entry, DESIGN-NO follows ``Fabric Code.xlsx``, and a blank LAUNCH
    DATE is filled from ``Launch Dates.xlsx``. ``Product SkuCode (Reference
    Only)`` is always a copy of the OMS export's ``Product SkuCode``. Only
    ``MY SKU`` and ``SIZE SKU`` are re-synced on existing rows, and only when
    the fresh mapping actually has a value. The one exception is the colour rule: a colour word is dropped from
    FINAL SKU and FINAL MY SKU too, since no SKU carries a colour, and it is
    written into the COLOR column when that cell is still empty.
  * Rows that have dropped out of the OMS export; they are kept, not deleted.
  * ``Product SkuCode`` is reference-only. It is never a source for MY SKU,
    SIZE SKU or Brand: a listing whose only sized SKU lives in that column is
    parked instead of being mapped from it.

Listings with no sized SKU are parked in ``output/new_unmapped_listings.xlsx``
rather than added to the master.


Ported to the master-sheet working (owner, 26 Nov 2026: "ye old tool he same to same use kar lo"):
the logic is the owner's tool G:/My Drive/BINDAL EXPORTS/OMSGURU MAPPING/update_master.py line for line;
only its file reading goes through xlcompat.py (calamine). Writing the workbook (xlsxwriter), the rows it used to
park in output/new_unmapped_listings.xlsx, and the command line are pipeline.py's job now; master.db is gone (Drive
keeps the old versions).
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from xlsxwriter.utility import xl_col_to_name

from . import xlcompat as xlrd
from .xlcompat import load_workbook


def get_column_letter(index: int) -> str:
    return xl_col_to_name(index - 1)


# The tool's own folder layout; pipeline.py passes its paths instead.
ROOT = Path(__file__).resolve().parent

# ----------------------------------------- listing parsing and brand mapping

PORTAL_DIR = ROOT / "input"


OMS_NAME_HINT = "channel_listing_mapping"


CHANNEL_ENTITY_PREFIX = re.compile(r"^[A-Z][A-Z0-9 .&'-]*\s+-\s+")


SUPPORTED_PORTAL_SUFFIXES = {".csv", ".txt", ".xls", ".xlsx"}


AJIO_SHEET_NAME = "B2C InventoryView"


# AJIO's 12-digit JioCode is a 9-digit style code plus a 3-digit size index.
# The code the business works with is that style code joined to the colour:
# JioCode 700637745001 + colour "Pink" -> 700637745_pink.
AJIO_STYLE_DIGITS = 9


def ajio_style_code(jiocode: str, color: str) -> str:
    """Trim the JioCode to its style digits and merge the colour onto it."""
    digits = text(jiocode).strip()
    colour = "".join(text(color).split()).lower()
    if len(digits) < AJIO_STYLE_DIGITS or not digits.isdigit() or not colour:
        return ""
    return f"{digits[:AJIO_STYLE_DIGITS]}_{colour}"


PREFIXES = {
    "AAT", "AAY", "ANN", "BSD", "DB", "DBCC", "FAH", "FASH", "FH", "FSH", "FSHCC",
    "FWD", "FYR", "GTZ", "HN", "LA", "LEA", "LEIA", "LIA", "LIEA", "MF", "MR",
    "MTR", "MU", "MUR", "MURCC", "NEW", "NYK", "SER", "SERN", "SR", "FSH1",
}


CONDITIONAL_PREFIXES = {"FS", "SY"}


LETTER_SIZES = {
    "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL",
    "2XS", "3XS", "2XL", "3XL", "4XL", "5XL", "6XL", "7XL", "8XL", "9XL", "10XL",
}


NUMERIC_SIZES = {str(number) for number in range(20, 61)}


SIZES = LETTER_SIZES | NUMERIC_SIZES


# Colour words a channel likes to drop into its seller SKU. Colour has its own
# COLOR column, so it is never part of a SKU: E-18-PINK-M is the SKU E-18-M, and
# I-14-ROYAL-BLUE-M is I-14-M. These words are dropped wherever a SKU is parsed.
COLOUR_TOKENS = frozenset({
    "AQUA", "BEIGE", "BLACK", "BLUE", "BRONZE", "BROWN", "BURGUNDY",
    "CHARCOAL", "CLEAR", "COFFEE", "CORAL", "CREAM", "FUCHSIA", "GOLD",
    "GREEN", "GREY", "INDIGO", "KHAKI", "LAVENDER", "LIME", "MAGENTA",
    "MAROON", "MAUVE", "MULTI", "MUSTARD", "NAVY", "NUDE", "OFF", "OFFWHITE",
    "OLIVE", "ORANGE", "PEACH", "PINK", "PURPLE", "RED", "ROYAL", "RUST",
    "SEA", "SILVER", "TAN", "TAUPE", "TEAL", "TURQUOISE", "VIOLET", "WHITE",
    "WINE", "YELLOW",
})


def without_colour(value: str) -> str:
    """The SKU with its colour words dropped."""
    return "-".join(token for token in value.split("-") if token not in COLOUR_TOKENS)


TITLE_BRANDS = [
    ("routes by all about you", "Routes by All About You"),
    ("twenty dresses by nykaa fashion", "Twenty Dresses by Nykaa Fashion"),
    ("dressberry x fwd", "DressBerry X fwd"),
    ("masalli fashion", "Masalli Fashion"),
    ("all about you", "all about you"),
    ("here&now", "HERE&NOW"),
    ("metronaut", "METRONAUT"),
    ("dressberry", "DressBerry"),
    ("ann springs", "Ann Springs"),
    ("murcia", "Murcia"),
    ("baesd", "BAESD"),
    ("glitchez", "glitchez"),
    ("fashfun clothing", "Fashfun"),
    ("fashfun", "Fashfun"),
    ("serein", "Serein"),
    ("leia", "LEIA"),
]


SINGLE_SIZE_ALIASES = {
    "SMALL": "S", "MEDIUM": "M", "LARGE": "L", "XSMALL": "XS",
    "XLARGE": "XL", "XXLARGE": "XXL",
}


INVALID_CORE_WORDS = {"PARENT", "SKU", "OOS", "OUT", "STOCK"}


@dataclass(frozen=True)
class ParsedSku:
    normalized: str
    my_sku: str
    size: str
    removed_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class PortalRecord:
    portal: str
    source_file: str
    source_sheet: str
    source_row: int
    listing_id: str
    channel_sku: str
    seller_sku: str
    style_sku: str
    size: str
    candidate_raw: str
    candidate_source: str
    my_sku: str
    size_sku: str
    status: str
    keys: tuple[tuple[str, str], ...]


@dataclass
class MasterResult:
    original_row: int
    channel_sku: str
    listing_id: str
    channel: str
    product_reference: str
    brand: str = ""
    brand_source: str = ""
    brand_note: str = ""
    my_sku: str = ""
    size_sku: str = ""
    mapping_source: str = ""
    portal: str = ""
    reference_files: str = ""
    match_key: str = ""
    match_field: str = ""
    status: str = ""
    reference_check: str = ""
    problem_reason: str = ""
    conflict_candidates: str = ""
    available_size_skus: str = ""


def text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize_text(value) -> str:
    value = text(value)
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value).upper()
    value = (
        value.replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .replace("_", "-")
    )
    value = re.sub(r"\s+", "-", value)
    # Brackets are decoration a seller types around a note, never part of the
    # code: "E-18 (NEW)-XS" is the SKU E-18-NEW-XS.
    value = value.replace("*", "").replace("$", "").replace("(", "").replace(")", "")
    value = value.strip(" .,:;|/\\")
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def normalize_key(value) -> str:
    return normalize_text(value)


def normalize_size_suffix(tokens: list[str]) -> list[str]:
    if not tokens:
        return tokens
    if tokens[-1] in SINGLE_SIZE_ALIASES:
        tokens[-1] = SINGLE_SIZE_ALIASES[tokens[-1]]
    elif len(tokens) >= 2 and tokens[-2:] in (["X", "SMALL"], ["EXTRA", "SMALL"]):
        tokens[-2:] = ["XS"]
    elif len(tokens) >= 2 and tokens[-2:] in (["X", "LARGE"], ["EXTRA", "LARGE"]):
        tokens[-2:] = ["XL"]
    elif len(tokens) >= 2 and tokens[-2:] == ["XX", "LARGE"]:
        tokens[-2:] = ["XXL"]
    elif tokens[-1] == "FREESIZE":
        tokens[-1:] = ["FREE", "SIZE"]

    if len(tokens) >= 3 and tokens[-1] not in SIZES and tokens[-2:] != ["FREE", "SIZE"]:
        final = tokens[-1]
        for size in sorted(LETTER_SIZES, key=len, reverse=True):
            if final.endswith(size) and len(final) > len(size):
                stem = final[: -len(size)]
                if re.search(r"[A-Z]", stem) and re.search(r"\d", stem):
                    tokens[-1:] = [stem, size]
                    break
    return tokens


def collapse_repeated_tokens(tokens: list[str]) -> list[str]:
    """Drop a token that is immediately repeated: ZI-1-K21-K21 -> ZI-1-K21.

    A repeated *number* is left alone. LimeRoad really does sell SER-4-1,
    SER-4-4, SER-4-5 and SER-4-6, so the second 4 is a style number rather
    than a slip, and collapsing it would invent the family SER-4.
    """
    collapsed: list[str] = []
    for token in tokens:
        if collapsed and token == collapsed[-1] and not token.isdigit():
            continue
        collapsed.append(token)
    return collapsed


def parse_and_clean(value) -> ParsedSku | None:
    normalized = normalize_text(value)
    if not normalized:
        return None
    tokens = normalize_size_suffix(normalized.split("-"))
    # Colour is recorded in the COLOR column, so it never belongs in a SKU:
    # E-18-PINK-M reads as E-18-M. The colourless reading is tried first, and
    # the full one is only used as a fallback, for the rare style whose name is
    # itself a colour word and would otherwise parse away to nothing.
    colourless = [token for token in tokens if token not in COLOUR_TOKENS]
    if colourless != tokens:
        parsed = _parse_collapsed(colourless)
        if parsed:
            return parsed
    return _parse_collapsed(tokens)


def _parse_collapsed(tokens: list[str]) -> ParsedSku | None:
    collapsed = collapse_repeated_tokens(tokens)
    if collapsed != tokens:
        # A back-to-back repeat is a typing slip in the channel SKU, both in a
        # style code (FSH-ZI-1-K21-K21-L) and in a size (SER-KURTI-A-167-S-S).
        # Only accept the collapsed form when it still parses, so a genuine
        # repeat such as SER-4-4-L -- which would collapse to the invalid core
        # "4" -- keeps its original reading.
        parsed = _parse_tokens(collapsed)
        if parsed:
            return parsed
    return _parse_tokens(tokens)


def _parse_tokens(tokens: list[str]) -> ParsedSku | None:
    tokens = list(tokens)
    if len(tokens) >= 2 and tokens[-2:] == ["FREE", "SIZE"]:
        size = "FREE-SIZE"
        size_count = 2
    elif tokens and tokens[-1] in SIZES:
        size = tokens[-1]
        size_count = 1
    else:
        return None

    core = tokens[:-size_count]
    if len(tokens) < 3 or not core:
        return None
    if any(word in INVALID_CORE_WORDS for word in core):
        return None
    if all(token.isdigit() for token in core) or not any(re.search(r"[A-Z]", token) for token in core):
        return None

    removed: list[str] = []
    if len(tokens) >= size_count + 2 and tokens[0] == "M" and tokens[1] in PREFIXES:
        removed.append(tokens.pop(0))
    while len(tokens) > size_count + 1:
        first = tokens[0]
        if first in PREFIXES:
            if len(tokens) > 1 and tokens[1].isdigit():
                break
            removed.append(tokens.pop(0))
            continue
        if first in CONDITIONAL_PREFIXES and len(tokens) > 1 and tokens[1] != "1":
            removed.append(tokens.pop(0))
            continue
        break

    core = tokens[:-size_count]
    if not core or all(token.isdigit() for token in core):
        return None
    # Numeric garment sizes in this dataset belong to pant SKUs. Without this
    # guard, a style such as FSH-E-36 is misread as SKU E in size 36, although
    # 36 is actually part of the style code and the variant size is missing.
    if size in NUMERIC_SIZES and "PANT" not in core:
        return None
    return ParsedSku(
        normalized="-".join(tokens),
        my_sku="-".join(core),
        size=size,
        removed_prefixes=tuple(removed),
    )


def parse_variant_before_parent(value) -> ParsedSku | None:
    normalized = normalize_text(value)
    if not normalized:
        return None
    tokens = normalized.split("-")
    while tokens and tokens[-1] in {"PARENT", "SKU"}:
        tokens.pop()
    if not tokens or len(tokens) == len(normalized.split("-")):
        return None
    return parse_and_clean("-".join(tokens))


def parent_family_base(value) -> str:
    normalized = normalize_text(value)
    if not normalized:
        return ""
    tokens = normalized.split("-")
    while tokens and tokens[-1] in {"PARENT", "SKU", "P"}:
        tokens.pop()
    if len(tokens) >= 2 and tokens[0] == "M" and tokens[1] in PREFIXES:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[0] in PREFIXES and not tokens[1].isdigit():
        tokens.pop(0)
    return "-".join(tokens)


def first_candidate(options: list[tuple[str, str]]) -> tuple[str, str, ParsedSku | None]:
    for source, raw in options:
        parsed = parse_and_clean(raw)
        if parsed:
            return raw, source, parsed
    return "", "", None


def unique_keys(pairs: list[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    seen = set()
    result = []
    for key_type, raw in pairs:
        key = normalize_key(raw)
        if key in SIZES or key in {"FREE-SIZE", "PARENT", "SKU"}:
            continue
        if key and (key_type, key) not in seen:
            seen.add((key_type, key))
            result.append((key_type, key))
    return tuple(result)


def make_record(
    portal: str,
    path: Path,
    sheet: str,
    source_row: int,
    listing_id,
    channel_sku,
    seller_sku,
    style_sku,
    size,
    candidates: list[tuple[str, str]],
    key_pairs: list[tuple[str, str]],
) -> PortalRecord:
    listing_id = text(listing_id)
    channel_sku = text(channel_sku)
    seller_sku = text(seller_sku)
    style_sku = text(style_sku)
    size = text(size)
    candidate_raw, candidate_source, parsed = first_candidate(candidates)
    keys = unique_keys(key_pairs + ([('CLEAN_SIZE_SKU', parsed.normalized)] if parsed else []))
    return PortalRecord(
        portal=portal,
        source_file=path.name,
        source_sheet=sheet,
        source_row=source_row,
        listing_id=listing_id,
        channel_sku=channel_sku,
        seller_sku=seller_sku,
        style_sku=style_sku,
        size=size,
        candidate_raw=text(candidate_raw),
        candidate_source=candidate_source,
        my_sku=parsed.my_sku if parsed else "",
        size_sku=parsed.normalized if parsed else "",
        status="USABLE" if parsed else "NO_USABLE_SKU",
        keys=keys,
    )


def load_myntra_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for source_row, raw_row in enumerate(reader, start=2):
            row = {text(k).casefold(): text(v) for k, v in raw_row.items()}
            seller = row.get("seller sku code", "")
            size = row.get("size", "")
            van = row.get("van", "")
            yield make_record(
                "MYNTRA", path, "CSV", source_row,
                row.get("sku id", ""), row.get("sku code", ""), seller, van, size,
                [
                    ("seller sku code", seller),
                    ("van", van),
                    ("van + size", f"{van}-{size}" if van and size else ""),
                ],
                [
                    ("SELLER_SKU", seller),
                    ("SKU_ID", row.get("sku id", "")),
                    ("SKU_CODE", row.get("sku code", "")),
                    ("VAN", van if parse_and_clean(van) else ""),
                ],
            )


def load_amazon_txt(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for source_row, raw_row in enumerate(reader, start=2):
            row = {text(k).casefold(): text(v) for k, v in raw_row.items()}
            seller = row.get("seller-sku", "")
            title = row.get("item-name", "")
            candidates = [("seller-sku", seller)]
            for index, segment in enumerate(re.findall(r"\(([^()]*)\)", title), start=1):
                candidates.append((f"item-name parentheses {index}", segment))
            yield make_record(
                "AMAZON", path, "TXT", source_row,
                row.get("listing-id", ""), row.get("asin1", "") or row.get("product-id", ""),
                seller, "", "", candidates,
                [
                    ("LISTING_ID", row.get("listing-id", "")),
                    ("SELLER_SKU", seller),
                    ("ASIN", row.get("asin1", "")),
                    ("PRODUCT_ID", row.get("product-id", "")),
                ],
            )


def load_jio_xlsx(path: Path):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[AJIO_SHEET_NAME]
    headers = [text(value) for value in next(ws.iter_rows(min_row=2, max_row=2, values_only=True))]
    for source_row, values in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        row = {headers[index].casefold(): text(value) for index, value in enumerate(values) if index < len(headers)}
        listing = row.get("jiocode", "")
        ean = row.get("ean", "")
        seller = row.get("seller sku", "")
        style = row.get("seller style code", "")
        size = row.get("size", "")
        yield make_record(
            "AJIO", path, ws.title, source_row, listing, ean, seller, style, size,
            [
                ("Seller SKU", seller),
                ("Seller Style Code + Size", f"{style}-{size}" if style and size else ""),
            ],
            [("JIO_CODE", listing), ("EAN", ean), ("SELLER_SKU", seller)],
        )
    wb.close()


def product_name_key(value) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", text(value).upper()).strip()


def load_meesho_xlsx(path: Path):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb["Inventory-Update-Data-Fill This"]
    headers = [text(value) for value in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
    source_rows = []
    for source_row, values in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        row = {headers[index].casefold(): text(value) for index, value in enumerate(values) if index < len(headers)}
        source_rows.append((source_row, row))
    wb.close()

    # Some Meesho exports replace Seller SKU with a numeric style id. When the
    # exact same product name occurs elsewhere with one unambiguous real style
    # family, use that source-derived family and the row's Variation size.
    name_to_family: dict[str, set[str]] = defaultdict(set)
    for _, row in source_rows:
        constructed = f"{row.get('style id', '')}-{row.get('variation', '')}"
        parsed = parse_and_clean(constructed)
        if parsed:
            name_to_family[product_name_key(row.get("product name", ""))].add(parsed.my_sku)

    for source_row, row in source_rows:
        catalog = row.get("catalog id", "")
        product = row.get("product id", "")
        style = row.get("style id", "")
        variation_id = row.get("variation id", "")
        size = row.get("variation", "")
        constructed = f"{style}-{size}" if style and size else ""
        candidates = [("Style ID + Variation", constructed)]
        direct = parse_and_clean(constructed)
        if not direct and style.isdigit():
            families = name_to_family.get(product_name_key(row.get("product name", "")), set())
            if len(families) == 1:
                family = next(iter(families))
                candidates.append(("Product Name exact family + Variation", f"{family}-{size}"))
        listing_key = f"{product}_{size}" if product and size else product
        channel_key = f"{catalog}_{size}" if catalog and size else catalog
        yield make_record(
            "MEESHO", path, ws.title, source_row, listing_key, channel_key,
            constructed, style, size,
            candidates,
            [
                ("PRODUCT_ID_SIZE", listing_key),
                ("CATALOG_ID_SIZE", channel_key),
                ("PRODUCT_ID_VARIATION_ID", f"{product}_{variation_id}" if product and variation_id else ""),
                ("CATALOG_ID_VARIATION_ID", f"{catalog}_{variation_id}" if catalog and variation_id else ""),
                ("CONSTRUCTED_SKU", constructed),
            ],
        )


def load_flipkart_xls(path: Path):
    wb = xlrd.open_workbook(path, on_demand=True)
    ws = wb.sheet_by_index(0)
    headers = [text(ws.cell_value(0, col)) for col in range(ws.ncols)]
    for row_idx in range(2, ws.nrows):
        row = {headers[col].casefold(): text(ws.cell_value(row_idx, col)) for col in range(ws.ncols)}
        seller = row.get("seller sku id", "")
        listing = row.get("listing id", "")
        serial = row.get("flipkart serial number", "")
        yield make_record(
            "FLIPKART", path, ws.name, row_idx + 1, listing, serial, seller, "", "",
            [("Seller SKU Id", seller)],
            [("LISTING_ID", listing), ("SELLER_SKU", seller), ("SERIAL_NUMBER", serial)],
        )
    wb.release_resources()


def first_sheet(workbook):
    """First worksheet, with a trustworthy column range.

    Some portal exports ship a bogus dimension record, which makes a read-only
    worksheet report a single column; resetting rebuilds it from the cells.
    """
    sheet = workbook.worksheets[0]
    if hasattr(sheet, "reset_dimensions"):
        sheet.reset_dimensions()
    return sheet


def load_nykaa_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for source_row, raw_row in enumerate(csv.DictReader(handle), start=2):
            row = {text(k).casefold(): text(v) for k, v in raw_row.items()}
            listing = row.get("nykaa sku code", "")
            seller = row.get("vendor sku code", "")
            yield make_record(
                "NYKAA", path, "CSV", source_row, listing, listing, seller, "", "",
                [("Vendor SKU Code", seller)],
                [("LISTING_ID", listing), ("SELLER_SKU", seller)],
            )


def load_snapdeal_xlsx(path: Path):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = first_sheet(wb)
    rows = ws.iter_rows(values_only=True)
    headers = [text(value).casefold() for value in next(rows)]
    for source_row, values in enumerate(rows, start=2):
        row = {headers[i]: text(v) for i, v in enumerate(values) if i < len(headers)}
        listing = row.get("supc", "")
        seller = row.get("sku code", "")
        if not listing:
            continue
        yield make_record(
            "SNAPDEAL", path, ws.title, source_row, listing, listing, seller, "", "",
            [("SKU Code", seller)],
            [("LISTING_ID", listing), ("SELLER_SKU", seller), ("SUPC", listing)],
        )
    wb.close()


# The Meesho catalogue export (.csv, or .xlsx with a "Products" sheet) carries
# the Product_Identifier that the master needs. Its name changes with every
# download, so it is recognised by these header columns instead.
MEESHO_EXPORT_HEADERS = frozenset({"catalog_id", "product_id", "product_identifier"})


def meesho_export_sheet(path: Path) -> str | None:
    """Name of the sheet in an .xlsx that holds the Meesho export, if any."""
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return None
    try:
        for sheet in workbook.worksheets:
            first = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
            if MEESHO_EXPORT_HEADERS <= {text(value).casefold() for value in first}:
                return sheet.title
    finally:
        workbook.close()
    return None


def is_meesho_export(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return MEESHO_EXPORT_HEADERS <= csv_headers(path)
    if suffix == ".xlsx":
        return meesho_export_sheet(path) is not None
    return False


def find_meesho_exports(portal_dir: Path):
    """Yield every Meesho catalogue export in the folder, newest last."""
    for path in sorted(portal_dir.iterdir(), key=lambda item: item.stat().st_mtime):
        if path.is_file() and is_meesho_export(path):
            yield path


def csv_headers(path: Path, delimiter: str = ",") -> set[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            row = next(csv.reader(handle, delimiter=delimiter), [])
    except (OSError, StopIteration):
        return set()
    return {text(value).casefold() for value in row}


def classify_portal_file(path: Path):
    """Pick a loader from the file's own header row, not just its extension.

    The export folder also holds files that carry no listing-to-SKU mapping
    (Myntra discount reports, for one); those return ``None`` and are skipped.
    """
    suffix = path.suffix.lower()

    if suffix == ".csv":
        headers = csv_headers(path)
        if {"seller sku code", "sku id", "style id"} <= headers:
            return load_myntra_csv, "MYNTRA listings"
        if {"nykaa sku code", "vendor sku code"} <= headers:
            return load_nykaa_csv, "NYKAA inventory"
        if {"seller-sku", "asin1"} <= headers:
            return load_amazon_txt, "AMAZON listings"
        if MEESHO_EXPORT_HEADERS <= headers:
            # Read for its identifiers by PortalIds, never as a mapping source.
            return None, "MEESHO export (identifiers only)"
        return None, "no listing/SKU mapping columns"

    if suffix == ".txt":
        if {"seller-sku", "asin1"} <= csv_headers(path, delimiter="	"):
            return load_amazon_txt, "AMAZON listings"
        return None, "no listing/SKU mapping columns"

    if suffix == ".xls":
        try:
            book = xlrd.open_workbook(path, on_demand=True)
            sheet = book.sheet_by_index(0)
            headers = {text(sheet.cell_value(0, col)).casefold() for col in range(sheet.ncols)}
            book.release_resources()
        except Exception:
            return None, "unreadable .xls"
        if {"seller sku id", "flipkart serial number"} <= headers:
            return load_flipkart_xls, "FLIPKART listings"
        return None, "no listing/SKU mapping columns"

    if suffix == ".xlsx":
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception:
            return None, "unreadable .xlsx"
        try:
            if "Inventory-Update-Data-Fill This" in wb.sheetnames:
                return load_meesho_xlsx, "MEESHO inventory"
            if AJIO_SHEET_NAME in wb.sheetnames:
                return load_jio_xlsx, "AJIO inventory"
            ws = first_sheet(wb)
            first = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
            headers = {text(value).casefold() for value in first}
            if {"supc", "sku code"} <= headers:
                return load_snapdeal_xlsx, "SNAPDEAL catalog"
        finally:
            wb.close()
        if meesho_export_sheet(path):
            # Read for its identifiers by PortalIds, never as a mapping source.
            return None, "MEESHO export (identifiers only)"
        return None, "no listing/SKU mapping columns"

    return None, "unsupported file type"


def load_portal_records(portal_dir: Path) -> list[PortalRecord]:
    records: list[PortalRecord] = []
    for path in sorted(portal_dir.iterdir(), key=lambda p: p.name.casefold()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_PORTAL_SUFFIXES:
            continue
        if OMS_NAME_HINT in path.name.casefold():
            continue
        loader, label = classify_portal_file(path)
        if loader is None:
            print(f"SKIPPED\t{path.name}\t{label}")
            continue
        before = len(records)
        records.extend(loader(path))
        print(f"LOADED\t{path.name}\t{label}\t{len(records) - before}")
    return records


def input_portal(channel: str) -> str:
    channel = channel.strip().upper()
    if channel.startswith("AJIO"):
        return "AJIO"
    if channel.startswith("AMAZON"):
        return "AMAZON"
    if channel.startswith("FLIPKART"):
        return "FLIPKART"
    if channel.startswith("MEESHO"):
        return "MEESHO"
    if channel.startswith("MYNTRA"):
        return "MYNTRA"
    if channel.startswith("NYKAA"):
        return "NYKAA"
    if channel.startswith("SNAPDEAL"):
        return "SNAPDEAL"
    return ""


def canonical_brand(value) -> str:
    raw = re.sub(r"\s+", " ", text(value)).strip()
    aliases = {
        "fashfun": "Fashfun",
        "fashfun clothing": "Fashfun",
        "serein": "Serein",
        "dressberry": "DressBerry",
        "dressberry x fwd": "DressBerry X fwd",
        "all about you": "all about you",
        "routes by all about you": "Routes by All About You",
        "murcia": "Murcia",
        "baesd": "BAESD",
        "glitchez": "glitchez",
        "here&now": "HERE&NOW",
        "metronaut": "METRONAUT",
        "masalli fashion": "Masalli Fashion",
        "leia": "LEIA",
        "ann springs": "Ann Springs",
        "shopsy": "Shopsy",
        "twenty dresses by nykaa fashion": "Twenty Dresses by Nykaa Fashion",
    }
    return aliases.get(raw.casefold(), raw)


def title_brand(value) -> str:
    title = re.sub(r"[^a-z0-9&]+", " ", text(value).casefold()).strip()
    for prefix, brand in TITLE_BRANDS:
        normalized_prefix = re.sub(r"[^a-z0-9&]+", " ", prefix).strip()
        if title.startswith(normalized_prefix):
            return brand
    return ""


def raw_family(value) -> str:
    normalized = normalize_text(value)
    if not normalized:
        return ""
    tokens = normalized.split("-")
    while tokens and tokens[-1] in {"PARENT", "SKU", "P"}:
        tokens.pop()
    if len(tokens) >= 2 and tokens[-2:] == ["FREE", "SIZE"]:
        tokens = tokens[:-2]
    elif tokens and tokens[-1] in SIZES:
        tokens.pop()
    elif tokens and tokens[-1] in {
        "SMALL", "MEDIUM", "LARGE", "XSMALL", "XLARGE", "XXLARGE", "FREESIZE",
    }:
        tokens.pop()
    return "-".join(tokens)


def prefix_brand(value, channel: str) -> str:
    normalized = normalize_text(value)
    if not normalized:
        return ""
    tokens = normalized.split("-")
    if len(tokens) >= 2 and tokens[0] == "M" and tokens[1] in {"SER", "SERN", "SR"}:
        prefix = tokens[1]
    elif len(tokens) >= 2 and tokens[:2] == ["NEW", "DB"]:
        prefix = "DB"
    else:
        prefix = tokens[0]

    portal = input_portal(channel)
    if prefix in {"FSH", "FASH", "FSHCC", "FH", "FS", "FAH", "NEW"}:
        return "Fashfun"
    if prefix in {"SER", "SERN", "SR", "SY"}:
        return "Fashfun" if portal == "MYNTRA" else ("Shopsy" if prefix == "SY" else "Serein")
    if prefix in {"MUR", "MURCC", "MU", "MR"}:
        return "Murcia"
    if prefix in {"DB", "DBCC"}:
        return "DressBerry"
    if prefix in {"AAY", "AAT"}:
        return "all about you"
    if prefix == "BSD":
        return "BAESD"
    if prefix in {"FWD", "GTZ"}:
        return "glitchez"
    if prefix == "HN":
        return "HERE&NOW"
    if prefix == "MTR":
        return "METRONAUT"
    if prefix == "MF":
        return "Masalli Fashion"
    if prefix in {"LEA", "LA", "LEIA", "LIA", "LIEA"}:
        return "LEIA"
    if prefix == "ANN":
        return "Ann Springs"
    if prefix == "NYK":
        return "Twenty Dresses by Nykaa Fashion"
    return ""


def title_or_prefix_brand(title: str, raw_sku: str, channel: str) -> tuple[str, str]:
    title_value = title_brand(title)
    prefix_value = prefix_brand(raw_sku, channel)
    title_head = text(title)[:120].casefold()
    if prefix_value and prefix_value.casefold().split(" by ")[0] in title_head:
        return prefix_value, "Portal product title + SKU prefix"
    if title_value:
        return title_value, "Portal product title"
    if prefix_value:
        return prefix_value, "Portal SKU prefix"
    return "", ""


def build_brand_indexes(portal_dir: Path):
    exact = defaultdict(Counter)
    family = defaultdict(Counter)
    sources = defaultdict(set)

    def add(portal: str, brand: str, keys, raw_values, source: str):
        brand = canonical_brand(brand)
        if not brand:
            return
        for value in keys:
            key = normalize_text(value)
            if key and key not in SIZES and key not in {"PARENT", "SKU", "OOS", "OUT-OF-STOCK"}:
                exact[(portal, key)][brand] += 1
                sources[(portal, key, brand)].add(source)
        for value in raw_values:
            key = raw_family(value)
            if key:
                family[(portal, key)][brand] += 1

    for path in sorted(portal_dir.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_PORTAL_SUFFIXES:
            continue
        if OMS_NAME_HINT in path.name.casefold():
            continue
        loader, _ = classify_portal_file(path)
        if loader is None:
            continue
        if loader is load_myntra_csv:
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                for row in csv.DictReader(handle):
                    brand = canonical_brand(row.get("brand", ""))
                    seller = row.get("seller sku code", "")
                    van = row.get("van", "")
                    size = row.get("size", "")
                    add(
                        "MYNTRA", brand,
                        [seller, row.get("sku id", ""), row.get("sku code", ""), van, f"{van}-{size}"],
                        [seller, f"{van}-{size}"],
                        f"{path.name}: brand field",
                    )
        elif loader is load_amazon_txt:
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                for row in csv.DictReader(handle, delimiter="\t"):
                    seller = row.get("seller-sku", "")
                    brand, source_type = title_or_prefix_brand(row.get("item-name", ""), seller, "AMAZON")
                    add(
                        "AMAZON", brand,
                        [row.get("listing-id", ""), seller, row.get("asin1", ""), row.get("product-id", "")],
                        [seller],
                        f"{path.name}: {source_type}",
                    )
        elif loader is load_flipkart_xls:
            workbook = xlrd.open_workbook(path, on_demand=True)
            worksheet = workbook.sheet_by_index(0)
            headers = [text(worksheet.cell_value(0, col)).casefold() for col in range(worksheet.ncols)]
            for row_index in range(2, worksheet.nrows):
                row = {
                    headers[col]: text(worksheet.cell_value(row_index, col))
                    for col in range(worksheet.ncols)
                }
                seller = row.get("seller sku id", "")
                brand, source_type = title_or_prefix_brand(row.get("product title", ""), seller, "FLIPKART")
                add(
                    "FLIPKART", brand,
                    [seller, row.get("listing id", ""), row.get("flipkart serial number", "")],
                    [seller],
                    f"{path.name}: {source_type}",
                )
            workbook.release_resources()
        elif loader is load_meesho_xlsx:
            workbook = load_workbook(path, read_only=True, data_only=True)
            worksheet = workbook["Inventory-Update-Data-Fill This"]
            headers = [
                text(value).casefold()
                for value in next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True))
            ]
            for values in worksheet.iter_rows(min_row=3, values_only=True):
                row = {
                    headers[index]: text(value)
                    for index, value in enumerate(values) if index < len(headers)
                }
                style = row.get("style id", "")
                size = row.get("variation", "")
                constructed = f"{style}-{size}" if style and size else style
                brand, source_type = title_or_prefix_brand(row.get("catalog name", ""), constructed, "MEESHO")
                if not brand:
                    brand, source_type = title_or_prefix_brand(row.get("product name", ""), constructed, "MEESHO")
                product = row.get("product id", "")
                catalog = row.get("catalog id", "")
                variation_id = row.get("variation id", "")
                add(
                    "MEESHO", brand,
                    [
                        f"{product}_{size}", f"{catalog}_{size}",
                        f"{product}_{variation_id}", f"{catalog}_{variation_id}", constructed,
                    ],
                    [constructed],
                    f"{path.name}: {source_type}",
                )
            workbook.close()
        elif loader is load_jio_xlsx:
            workbook = load_workbook(path, read_only=True, data_only=True)
            worksheet = workbook["B2C InventoryView"]
            headers = [
                text(value).casefold()
                for value in next(worksheet.iter_rows(min_row=2, max_row=2, values_only=True))
            ]
            for values in worksheet.iter_rows(min_row=3, values_only=True):
                row = {
                    headers[index]: text(value)
                    for index, value in enumerate(values) if index < len(headers)
                }
                seller = row.get("seller sku", "")
                style = row.get("seller style code", "")
                size = row.get("size", "")
                brand = prefix_brand(seller or style, "AJIO")
                add(
                    "AJIO", brand,
                    [row.get("jiocode", ""), row.get("ean", ""), seller, f"{style}-{size}"],
                    [seller, f"{style}-{size}"],
                    f"{path.name}: portal SKU prefix",
                )
            workbook.close()
        elif loader is load_nykaa_csv:
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                for row in csv.DictReader(handle):
                    listing = row.get("Nykaa SKU Code", "")
                    seller = row.get("Vendor SKU Code", "")
                    brand = prefix_brand(seller, "NYKAA")
                    add(
                        "NYKAA", brand, [listing, seller], [seller],
                        f"{path.name}: portal SKU prefix",
                    )
        elif loader is load_snapdeal_xlsx:
            workbook = load_workbook(path, read_only=True, data_only=True)
            worksheet = first_sheet(workbook)
            rows = worksheet.iter_rows(values_only=True)
            headers = [text(value).casefold() for value in next(rows)]
            for values in rows:
                row = {
                    headers[index]: text(value)
                    for index, value in enumerate(values) if index < len(headers)
                }
                seller = row.get("sku code", "")
                brand, source_type = title_or_prefix_brand(row.get("product name", ""), seller, "SNAPDEAL")
                add(
                    "SNAPDEAL", brand, [row.get("supc", ""), seller], [seller],
                    f"{path.name}: {source_type}",
                )
            workbook.close()
    return exact, family, sources


def map_result_brands(results, portal_dir: Path):
    exact, family, sources = build_brand_indexes(portal_dir)
    stats = Counter()

    def choose(candidates: Counter, fallback: str):
        if not candidates:
            return "", ""
        if len(candidates) == 1:
            return next(iter(candidates)), "UNIQUE"
        if fallback and fallback in candidates:
            return fallback, "PREFIX_RESOLVED"
        most_common = candidates.most_common()
        if len(most_common) >= 2 and most_common[0][1] >= most_common[1][1] * 3:
            return most_common[0][0], "STRONG_MAJORITY"
        return "", "; ".join(sorted(candidates))

    for result in results:
        portal = input_portal(result.channel)
        fallback = prefix_brand(result.channel_sku, result.channel) or prefix_brand(
            result.listing_id, result.channel
        )
        keys = [
            normalize_text(result.channel_sku),
            normalize_text(result.listing_id),
            normalize_text(result.match_key),
        ]
        exact_candidates = Counter()
        exact_source_names = set()
        for key in dict.fromkeys(key for key in keys if key):
            exact_candidates.update(exact.get((portal, key), {}))
        brand, decision = choose(exact_candidates, fallback)
        if brand:
            for key in dict.fromkeys(key for key in keys if key):
                exact_source_names.update(sources.get((portal, key, brand), set()))
            result.brand = brand
            result.brand_source = "Portal exact key"
            result.brand_note = "; ".join(sorted(exact_source_names))
            if decision != "UNIQUE":
                result.brand_note = (result.brand_note + "; " if result.brand_note else "") + decision
        else:
            family_candidates = Counter()
            for value in (result.channel_sku, result.listing_id):
                family_key = raw_family(value)
                if family_key:
                    family_candidates.update(family.get((portal, family_key), {}))
            family_brand, family_decision = choose(family_candidates, fallback)
            if family_brand:
                result.brand = family_brand
                result.brand_source = "Portal prefixed SKU family"
                result.brand_note = family_decision
            elif fallback:
                result.brand = fallback
                result.brand_source = "Channel SKU prefix rule"
                result.brand_note = "No exact portal brand key; used channel-aware prefix"
            elif exact_candidates or family_candidates:
                result.brand = ""
                result.brand_source = "AMBIGUOUS"
                candidates = set(exact_candidates) | set(family_candidates)
                result.brand_note = "Multiple brand candidates: " + "; ".join(sorted(candidates))
            else:
                result.brand = ""
                result.brand_source = "NO BRAND EVIDENCE"
                result.brand_note = "No brand field/title/prefixed SKU evidence in allowed sources"

    # Fill unprefixed rows only where other source-derived rows agree on a
    # single brand for the same channel/portal SKU. Product SkuCode is not used.
    channel_size_brands = defaultdict(set)
    channel_family_brands = defaultdict(set)
    portal_size_brands = defaultdict(set)
    portal_family_brands = defaultdict(set)
    for result in results:
        channel = text(result.channel).upper()
        portal_group = input_portal(result.channel) or channel
        if result.brand and result.size_sku:
            channel_size_brands[(channel, text(result.size_sku))].add(result.brand)
            portal_size_brands[(portal_group, text(result.size_sku))].add(result.brand)
        if result.brand and result.my_sku:
            channel_family_brands[(channel, text(result.my_sku))].add(result.brand)
            portal_family_brands[(portal_group, text(result.my_sku))].add(result.brand)

    for result in results:
        if result.brand:
            continue
        channel = text(result.channel).upper()
        portal_group = input_portal(result.channel) or channel
        size_candidates = channel_size_brands.get((channel, text(result.size_sku)), set())
        family_candidates = channel_family_brands.get((channel, text(result.my_sku)), set())
        portal_size_candidates = portal_size_brands.get((portal_group, text(result.size_sku)), set())
        portal_family_candidates = portal_family_brands.get((portal_group, text(result.my_sku)), set())
        if result.size_sku and len(size_candidates) == 1:
            result.brand = next(iter(size_candidates))
            result.brand_source = "Input channel SIZE SKU brand cross-match"
            result.brand_note = "Unique brand on another source-derived row with the same channel and SIZE SKU"
        elif result.my_sku and len(family_candidates) == 1:
            result.brand = next(iter(family_candidates))
            result.brand_source = "Input channel MY SKU brand family"
            result.brand_note = "Unique brand across source-derived variants in the same channel and MY SKU family"
        elif result.size_sku and len(portal_size_candidates) == 1:
            result.brand = next(iter(portal_size_candidates))
            result.brand_source = "Portal group SIZE SKU brand cross-match"
            result.brand_note = "Unique brand on another source-derived row in the same portal group and SIZE SKU"
        elif result.my_sku and len(portal_family_candidates) == 1:
            result.brand = next(iter(portal_family_candidates))
            result.brand_source = "Portal group MY SKU brand family"
            result.brand_note = "Unique brand across source-derived variants in the same portal group and MY SKU family"

    for result in results:
        stats[f"status:{'MAPPED' if result.brand else result.brand_source}"] += 1
        stats[f"brand:{result.brand or '(blank)'}"] += 1
        stats[f"source:{result.brand_source}"] += 1
        stats[f"channel:{result.channel}:{'MAPPED' if result.brand else result.brand_source}"] += 1
    return stats


def build_index(records: list[PortalRecord]):
    usable_index: dict[tuple[str, str], list[int]] = defaultdict(list)
    all_key_index: dict[tuple[str, str], list[int]] = defaultdict(list)
    for record_id, record in enumerate(records):
        for _, key in record.keys:
            all_key_index[(record.portal, key)].append(record_id)
            if record.status == "USABLE":
                usable_index[(record.portal, key)].append(record_id)
    return usable_index, all_key_index


def reference_check(reference: str, size_sku: str) -> str:
    parsed = parse_and_clean(reference)
    if not parsed:
        return "NO USABLE REFERENCE"
    return "MATCH" if parsed.normalized == size_sku else "DIFFERS"


def candidate_source_priority(source: str) -> int:
    source = source.casefold()
    if source in {"seller sku code", "seller sku", "seller-sku", "seller sku id"}:
        return 0
    if source == "van":
        return 1
    if "item-name" in source:
        return 2
    return 3


def input_problem_reason(raw_a: str, raw_b: str, had_reference_hit: bool) -> str:
    combined = f"{normalize_text(raw_a)} {normalize_text(raw_b)}"
    if "PARENT" in combined:
        return "Parent/non-variant listing; no usable size SKU"
    if had_reference_hit:
        return "Portal record matched, but portal row has no usable product SKU"
    if re.fullmatch(r"[\d\s_-]+", f"{raw_a}_{raw_b}".strip("_")):
        return "Only numeric/listing identifiers found; no matching portal reference"
    return "No usable sized SKU in source columns and no unique portal reference match"


def map_input(input_rows, records: list[PortalRecord], usable_index, all_key_index):
    results: list[MasterResult] = []
    stats = Counter()
    recoveries_by_channel = Counter()
    conflict_rows = []

    for row_idx, raw_a, raw_b, channel, product_reference in input_rows:
        result = MasterResult(row_idx, raw_a, raw_b, channel, product_reference)

        direct_a = parse_and_clean(raw_a) or parse_variant_before_parent(raw_a)
        direct_b = parse_and_clean(raw_b) or parse_variant_before_parent(raw_b)
        direct = direct_a or direct_b
        if direct:
            result.my_sku = direct.my_sku
            result.size_sku = direct.normalized
            if direct_a:
                result.mapping_source = (
                    "Channel Listing SKU Code (Parent suffix removed)"
                    if not parse_and_clean(raw_a) else "Channel Listing SKU Code"
                )
            else:
                result.mapping_source = (
                    "Channel Listing Id (Parent suffix removed)"
                    if not parse_and_clean(raw_b) else "Channel Listing Id"
                )
            result.status = "MAPPED"
            result.reference_check = reference_check(product_reference, direct.normalized)
            stats["direct_mapped"] += 1
            stats[f"reference:{result.reference_check}"] += 1
            results.append(result)
            continue

        portal = input_portal(channel)
        result.portal = portal
        input_keys = [normalize_key(raw_a), normalize_key(raw_b)]
        matched_ids = []
        all_matched_ids = []
        for key in input_keys:
            if not key or not portal:
                continue
            usable = usable_index.get((portal, key), [])
            any_records = all_key_index.get((portal, key), [])
            matched_ids.extend(usable)
            all_matched_ids.extend(any_records)
        matched_ids = list(dict.fromkeys(matched_ids))
        all_matched_ids = list(dict.fromkeys(all_matched_ids))
        # When the same portal key has both a real seller SKU and a constructed
        # fallback (for example VAN + numeric size), prefer the explicit seller
        # SKU. This uses portal lineage only and never Product SkuCode.
        if matched_ids:
            best_priority = min(candidate_source_priority(records[i].candidate_source) for i in matched_ids)
            matched_ids = [
                i for i in matched_ids
                if candidate_source_priority(records[i].candidate_source) == best_priority
            ]
        by_candidate: dict[str, list[int]] = defaultdict(list)
        for record_id in matched_ids:
            by_candidate[records[record_id].size_sku].append(record_id)

        def selected_match_key(selected_ids: list[int]) -> str:
            selected = set(selected_ids)
            for candidate_key in input_keys:
                if candidate_key and selected.intersection(usable_index.get((portal, candidate_key), [])):
                    return candidate_key
            return ""

        if len(by_candidate) == 1:
            size_sku, candidate_record_ids = next(iter(by_candidate.items()))
            record = records[candidate_record_ids[0]]
            result.my_sku = record.my_sku
            result.size_sku = size_sku
            result.mapping_source = "Portal Reference"
            result.reference_files = "; ".join(sorted({records[i].source_file for i in candidate_record_ids}))
            result.match_key = selected_match_key(candidate_record_ids)
            result.match_field = record.candidate_source
            result.status = "MAPPED"
            result.reference_check = reference_check(product_reference, size_sku)
            stats["portal_mapped"] += 1
            stats[f"portal_mapped:{portal}"] += 1
            stats[f"reference:{result.reference_check}"] += 1
            recoveries_by_channel[channel] += 1
        elif len(by_candidate) > 1:
            result.mapping_source = "Portal Reference"
            result.reference_files = "; ".join(sorted({records[i].source_file for i in matched_ids}))
            result.match_key = selected_match_key(matched_ids)
            result.status = "CONFLICT"
            result.problem_reason = "Portal key maps to multiple different size SKUs"
            result.conflict_candidates = "; ".join(sorted(by_candidate))
            stats["conflict"] += 1
            conflict_rows.append(result)
        else:
            result.status = "UNRESOLVED"
            result.problem_reason = input_problem_reason(raw_a, raw_b, bool(all_matched_ids))
            result.reference_files = "; ".join(sorted({records[i].source_file for i in all_matched_ids}))
            stats["unresolved"] += 1
            stats[f"unresolved:{portal or 'NO_PORTAL_FILE'}"] += 1
        results.append(result)

    return results, stats, recoveries_by_channel, conflict_rows


def postprocess_results(results: list[MasterResult]):
    family_sizes: dict[str, set[str]] = defaultdict(set)
    for result in results:
        if result.status == "MAPPED" and result.size_sku:
            family_sizes[result.my_sku].add(result.size_sku)

    for result in results:
        if result.status == "MAPPED":
            continue

        if parse_and_clean(result.product_reference):
            # Product SkuCode is the OMS mapping code, and it stays reference
            # only: MY SKU and SIZE SKU are built from the channel's own seller
            # SKU. A row with no seller-SKU evidence therefore gets no SKU at
            # all rather than borrowing the reference.
            result.status = "REFERENCE ONLY - NO SOURCE EVIDENCE"
            result.mapping_source = "Reference only (not used as output)"
            result.reference_check = "REFERENCE ONLY"
            result.problem_reason = "Valid reference exists, but no source/portal SKU evidence was found"
            result.conflict_candidates = ""
            continue

        combined = f"{normalize_text(result.channel_sku)} {normalize_text(result.listing_id)}"
        if "PARENT" in combined:
            base = parent_family_base(result.channel_sku) or parent_family_base(result.listing_id)
            variants = sorted(family_sizes.get(base, set()))
            # A small number of Amazon parent SKUs omit a style segment that is
            # present on every child (for example PANT-K-1-PARENT vs
            # PANT-K-1-K3-L). Link only when the source-derived child family is
            # unique, so this remains evidence-based and cannot choose between
            # multiple possible styles.
            if base and not variants:
                descendant_families = sorted(
                    family for family in family_sizes if family.startswith(base + "-")
                )
                if len(descendant_families) == 1:
                    base = descendant_families[0]
                    variants = sorted(family_sizes[base])
            result.my_sku = base
            result.size_sku = ""
            result.mapping_source = "Input Size Family"
            result.portal = "INPUT"
            result.reference_files = "Existing size variants in input"
            result.match_key = base
            result.match_field = "Parent listing linked to source-derived size family"
            result.status = "PARENT FAMILY (NO SINGLE SIZE)"
            result.reference_check = "NO USABLE REFERENCE"
            result.available_size_skus = "; ".join(variants)
            result.problem_reason = ""
            result.conflict_candidates = ""
            continue

        result.status = "OOS / NO SKU EVIDENCE"
        result.mapping_source = "Excluded OOS / source has no SKU"
        result.reference_check = "NO USABLE REFERENCE"
        result.problem_reason = "No sized SKU exists in allowed input/portal source fields"
        result.conflict_candidates = ""

    final_stats = Counter()
    recoveries_by_channel = Counter()
    for result in results:
        final_stats[f"status:{result.status}"] += 1
        final_stats[f"source:{result.mapping_source}"] += 1
        if result.reference_check:
            final_stats[f"reference:{result.reference_check}"] += 1
        if result.mapping_source.startswith("Channel Listing"):
            final_stats["direct_mapped"] += 1
        elif result.mapping_source.startswith("Portal Reference") and result.status == "MAPPED":
            final_stats["portal_mapped"] += 1
            recoveries_by_channel[result.channel] += 1
        if result.status == "MAPPED":
            final_stats["mapped_total"] += 1
    return final_stats, recoveries_by_channel


def is_parent_or_no_size(result: MasterResult) -> bool:
    """Return True for parent/base SKUs that do not contain one valid size."""
    source_tokens = (
        normalize_text(result.channel_sku).split("-")
        + normalize_text(result.listing_id).split("-")
    )
    if "PARENT" in source_tokens:
        return True
    if result.status == "PARENT FAMILY (NO SINGLE SIZE)":
        return True
    if result.size_sku and not parse_and_clean(result.size_sku):
        return True
    return bool(result.my_sku and not result.size_sku)


def find_oms_export(folder: Path):
    """Locate the OMS channel-listing export, zipped or loose, in ``folder``."""
    candidates = []
    for path in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file():
            continue
        name = path.name.casefold()
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for entry in archive.namelist():
                    if OMS_NAME_HINT in entry.casefold():
                        candidates.append((path, entry))
        elif path.suffix.lower() == ".csv" and OMS_NAME_HINT in name:
            candidates.append((path, None))
    if not candidates:
        return None
    # Newest export wins when several are present.
    return max(candidates, key=lambda item: item[0].stat().st_mtime)


def open_oms_rows(path: Path, entry):
    if entry is None:
        handle = path.open("r", encoding="utf-8-sig", newline="")
        return handle, csv.DictReader(handle)
    archive = zipfile.ZipFile(path)
    stream = io.TextIOWrapper(archive.open(entry), encoding="utf-8-sig", newline="")
    return archive, csv.DictReader(stream)


# ------------------------------------------ master sheet shape and portal ids

MASTER = ROOT / "MasterSheet.xlsx"


MASTER_SHEET = "Master"


COMBINED_SHEET = "Portal Combined"


BASE_COLUMNS = (
    "Channel Listing SKU Code",
    "Channel Listing Id",
    "Channel Name",
    "Brand",
    "Product SkuCode (Reference Only)",
    "MY SKU",
    "SIZE SKU",
    "FINAL SKU",
    "FINAL MY SKU",
    "DESIGN-NO",
    "LAUNCH DATE",
)


ID_COLUMNS = (
    "MYNTRA STYLE ID",
    "MYNTRA SKU CODE",
    "FLIPKART FSN",
    "MEESHO PRODUCT ID",
    "MEESHO CATALOG ID",
    "MEESHO PRODUCT IDENTIFIER",
    "AMAZON ASIN",
    "AJIO JIOCODE",
)




COLOR_COLUMN = "COLOR"
# The date the FINAL SKU first went live on Myntra, copied to every portal's row.
PORTAL_DATE_COLUMN = "PORTAL LISTING DATE"
MASTER_COLUMNS = BASE_COLUMNS + (PORTAL_DATE_COLUMN,) + ID_COLUMNS + (COLOR_COLUMN,)

COMBINED_COLUMNS = (
    "Portal",
    "Source File",
    "Brand",
    "Listing / SKU ID",
    "Style / Parent ID",
    "Seller SKU",
    "Size",
    "Color",
    "MY SKU",
    "SIZE SKU",
    "Title / Product Name",
    "Status",
)


COLUMN_WIDTHS = {
    "Channel Listing SKU Code": 37.5, "Channel Listing Id": 34.5,
    "Channel Name": 16.5, "Brand": 31.5,
    "Product SkuCode (Reference Only)": 34.5, "MY SKU": 30,
    "SIZE SKU": 39.5, "FINAL SKU": 39.5, "FINAL MY SKU": 30,
    "DESIGN-NO": 18, "LAUNCH DATE": 16, "PORTAL LISTING DATE": 20,
    "MYNTRA STYLE ID": 18, "MYNTRA SKU CODE": 24, "FLIPKART FSN": 20,
    "MEESHO PRODUCT ID": 20, "MEESHO CATALOG ID": 20,
    "MEESHO PRODUCT IDENTIFIER": 26,
    "AMAZON ASIN": 16, "AJIO JIOCODE": 16, "COLOR": 18,
    "Portal": 14, "Source File": 46, "Listing / SKU ID": 26,
    "Style / Parent ID": 22, "Seller SKU": 34, "Size": 10, "Color": 18,
    "Title / Product Name": 60, "Status": 16,
}


CHANNEL_LABELS = {
    "ajio": "AJIO",
    "ajio api": "AJIO API",
    "amazon": "AMAZON",
    "amazon df": "AMAZON DF",
    "amazon direct fulfillment": "AMAZON DF",
    "amazon smart": "AMAZON SMART",
    "amazon smartconnect wi": "AMAZON SMART",
    "flipkart": "FLIPKART",
    "limeroad": "LIMEROAD",
    "meesho": "MEESHO",
    "myntra": "MYNTRA",
    "myntra dbcc": "MYNTRA DBCC",
    "myntra dressberry cc": "MYNTRA DBCC",
    "myntra fashfun murcia cc": "MYNTRA FMCC",
    "myntra fmcc": "MYNTRA FMCC",
    "myntra ppmp": "MYNTRA PPMP",
    "nykaa": "NYKAA",
    "nykaa fashion": "NYKAA",
    "snapdeal": "SNAPDEAL",
}


def channel_label(value) -> str:
    raw = text(value)
    return CHANNEL_LABELS.get(raw.casefold(), raw.upper())


def row_key(channel, listing_id) -> tuple[str, str]:
    return channel_label(channel), text(listing_id)


def listing_id_value(value):
    """Channel Listing Id as a real number whenever the id is numeric.

    Half the channels number their listings (AJIO, Myntra, LimeRoad) and half
    use a code (Flipkart's LST..., Amazon's ASIN). An all-digit id is written as
    a number so every one of them sorts and matches alike, instead of some rows
    holding text and some holding numbers -- which is what breaks a lookup
    against the sheet. Anything that is not all digits is left as it is.

    A leading zero or an id longer than Excel's 15 significant digits would not
    survive the trip through a number, so those keep their text form.
    """
    raw = text(value)
    if not raw:
        return None
    if raw.isdigit() and len(raw) <= 15 and not (len(raw) > 1 and raw[0] == "0"):
        return int(raw)
    return raw


def portal_files(portal_dir: Path):
    """Yield ``(path, loader)`` for every export that carries a mapping."""
    for path in sorted(portal_dir.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_PORTAL_SUFFIXES:
            continue
        if OMS_NAME_HINT in path.name.casefold():
            continue
        loader, _ = classify_portal_file(path)
        if loader is not None:
            yield path, loader


class ColorIndex:
    """Colour lookups, keyed every way a master row can be matched.

    Only two exports carry a colour: the AJIO inventory views, and the Myntra
    style reports (which hold no listing mapping, so the record loader skips
    them). Colour belongs to the design rather than the channel, so a colour
    learnt from either source is reused across every marketplace.
    """

    def __init__(self, portal_dir: Path):
        self.by_size_sku: dict[str, Counter] = defaultdict(Counter)
        self.by_family: dict[str, Counter] = defaultdict(Counter)
        self.by_myntra_style: dict[str, Counter] = defaultdict(Counter)
        self.by_jio_code: dict[str, str] = {}
        self.stats: Counter = Counter()
        self._load(portal_dir)

    def _learn(self, color: str, raw_sku: str, fallback_sku: str = "") -> None:
        parsed = parse_and_clean(raw_sku) or parse_and_clean(fallback_sku)
        if parsed:
            self.by_size_sku[parsed.normalized][color] += 1
            self.by_family[parsed.my_sku][color] += 1

    def _load(self, portal_dir: Path) -> None:
        for path in sorted(portal_dir.iterdir(), key=lambda item: item.name.casefold()):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix == ".xlsx":
                workbook = load_workbook(path, read_only=True, data_only=True)
                if AJIO_SHEET_NAME not in workbook.sheetnames:
                    workbook.close()
                    continue
                sheet = workbook[AJIO_SHEET_NAME]
                values_iter = sheet.iter_rows(min_row=2, values_only=True)
                headers = [text(value).casefold() for value in next(values_iter)]
                for values in values_iter:
                    row = {headers[i]: text(v) for i, v in enumerate(values) if i < len(headers)}
                    color = row.get("color", "")
                    if not color:
                        continue
                    if row.get("jiocode"):
                        self.by_jio_code[row["jiocode"]] = color
                    style, size = row.get("seller style code", ""), row.get("size", "")
                    self._learn(color, row.get("seller sku", ""), f"{style}-{size}")
                    self.stats[f"ajio: {path.name}"] += 1
                workbook.close()
            elif suffix == ".csv":
                headers = csv_headers(path)
                if not {"color", "article no", "style id"} <= headers:
                    continue
                with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                    for raw_row in csv.DictReader(handle):
                        row = {text(k).casefold(): text(v) for k, v in raw_row.items()}
                        color = row.get("color", "")
                        if not color:
                            continue
                        if row.get("style id"):
                            self.by_myntra_style[row["style id"]][color] += 1
                        self._learn(color, row.get("article no", ""))
                        self.stats[f"myntra style report: {path.name}"] += 1

    @staticmethod
    def _only(counter: Counter) -> str:
        """A colour only counts when the key maps to exactly one."""
        return next(iter(counter)) if len(counter) == 1 else ""

    def for_row(self, size_sku: str, my_sku: str, myntra_style: str, jio_code: str) -> str:
        return (
            self._only(self.by_size_sku.get(size_sku, Counter()))
            or self.by_jio_code.get(jio_code, "")
            or self._only(self.by_myntra_style.get(myntra_style, Counter()))
            or self._only(self.by_family.get(my_sku, Counter()))
        )


def myntra_date(value: str) -> datetime | None:
    """Myntra's ``style catalogued date``, written as 20240509."""
    try:
        return datetime.strptime(text(value), "%Y%m%d")
    except ValueError:
        return None


class PortalIds:
    """Identifier lookups built from the raw portal exports."""

    def __init__(self, portal_dir: Path):
        self.myntra_style_by_sku_id: dict[str, str] = {}
        self.myntra_style_by_seller: dict[str, set[str]] = defaultdict(set)
        self.myntra_sku_code_by_sku_id: dict[str, str] = {}
        # Earliest "style catalogued date" a sku id carries across the accounts.
        self.myntra_listed_by_sku_id: dict[str, datetime] = {}
        self.flipkart_fsn_by_listing: dict[str, str] = {}
        self.flipkart_fsn_by_seller: dict[str, set[str]] = defaultdict(set)
        self.flipkart_fsn_by_size_sku: dict[str, set[str]] = defaultdict(set)
        self.meesho_catalog_by_product: dict[str, str] = {}
        self.meesho_identifier_by_product: dict[str, str] = {}
        self.meesho_identifier_by_sku_id: dict[str, str] = {}
        self.amazon_asin_by_listing: dict[str, str] = {}
        self.amazon_asin_by_seller: dict[str, set[str]] = defaultdict(set)
        self.ajio_code_by_jiocode: dict[str, str] = {}
        self.ajio_code_by_style: dict[str, set[str]] = defaultdict(set)
        self.stats: Counter = Counter()
        self._load(portal_dir)

    def _load(self, portal_dir: Path) -> None:
        readers = {
            load_myntra_csv: self._load_myntra,
            load_flipkart_xls: self._load_flipkart,
            load_amazon_txt: self._load_amazon,
            load_meesho_xlsx: self._load_meesho,
            load_jio_xlsx: self._load_ajio,
        }
        for path, loader in portal_files(portal_dir):
            reader = readers.get(loader)
            if reader is not None:
                reader(path)
        # Not a mapping source, so classify_portal_file leaves it out of
        # portal_files; it is read here purely for Product_Identifier.
        for path in find_meesho_exports(portal_dir):
            self._load_meesho_export(path)

    def _load_myntra(self, path: Path) -> None:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for raw_row in csv.DictReader(handle):
                row = {text(k).casefold(): text(v) for k, v in raw_row.items()}
                style = row.get("style id", "")
                if not style:
                    continue
                sku_id = row.get("sku id", "")
                if sku_id:
                    self.myntra_style_by_sku_id[sku_id] = style
                    if row.get("sku code", ""):
                        self.myntra_sku_code_by_sku_id[sku_id] = row["sku code"]
                    listed = myntra_date(row.get("style catalogued date", ""))
                    earlier = self.myntra_listed_by_sku_id.get(sku_id)
                    if listed and (earlier is None or listed < earlier):
                        self.myntra_listed_by_sku_id[sku_id] = listed
                seller = row.get("seller sku code", "")
                if seller:
                    self.myntra_style_by_seller[seller].add(style)
                self.stats[f"myntra: {path.name}"] += 1

    def _load_flipkart(self, path: Path) -> None:
        book = xlrd.open_workbook(path, on_demand=True)
        sheet = book.sheet_by_index(0)
        headers = [text(sheet.cell_value(0, col)).casefold() for col in range(sheet.ncols)]
        listing_col = headers.index("listing id")
        fsn_col = headers.index("flipkart serial number")
        seller_col = headers.index("seller sku id")
        for row_idx in range(2, sheet.nrows):
            fsn = text(sheet.cell_value(row_idx, fsn_col))
            if not fsn:
                continue
            listing = text(sheet.cell_value(row_idx, listing_col))
            seller = text(sheet.cell_value(row_idx, seller_col))
            if listing:
                self.flipkart_fsn_by_listing[listing] = fsn
            if seller:
                self.flipkart_fsn_by_seller[seller].add(fsn)
                parsed = parse_and_clean(seller)
                if parsed:
                    self.flipkart_fsn_by_size_sku[parsed.normalized].add(fsn)
            self.stats[f"flipkart: {path.name}"] += 1
        book.release_resources()

    def _load_amazon(self, path: Path) -> None:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for raw_row in csv.DictReader(handle, delimiter="\t"):
                row = {text(k).casefold(): text(v) for k, v in raw_row.items()}
                asin = row.get("asin1", "") or row.get("product-id", "")
                if not asin:
                    continue
                listing = row.get("listing-id", "")
                seller = row.get("seller-sku", "")
                if listing:
                    self.amazon_asin_by_listing[listing] = asin
                if seller:
                    self.amazon_asin_by_seller[seller].add(asin)
                self.stats[f"amazon: {path.name}"] += 1

    def _load_meesho(self, path: Path) -> None:
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook["Inventory-Update-Data-Fill This"]
        rows = sheet.iter_rows(values_only=True)
        headers = [text(value).casefold() for value in next(rows)]
        next(rows, None)  # description row
        for values in rows:
            row = {headers[i]: text(v) for i, v in enumerate(values) if i < len(headers)}
            product = row.get("product id", "")
            catalog = row.get("catalog id", "")
            if product and catalog:
                self.meesho_catalog_by_product[product] = catalog
                self.stats[f"meesho: {path.name}"] += 1
        workbook.close()

    def _load_meesho_export(self, path: Path) -> None:
        """Read Product_Identifier out of the Meesho catalogue export."""
        for row in self._meesho_export_rows(path):
            identifier = row.get("product_identifier", "")
            if not identifier:
                continue
            product = row.get("product_id", "")
            if product:
                self.meesho_identifier_by_product[product] = identifier
            sku_id = row.get("sku_id", "")
            if sku_id:
                self.meesho_identifier_by_sku_id[sku_id] = identifier
            self.stats[f"meesho export: {path.name}"] += 1

    @staticmethod
    def _meesho_export_rows(path: Path):
        """Yield the export's rows as {lower-case header: text}, .csv or .xlsx."""
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                for raw_row in csv.DictReader(handle):
                    yield {text(key).casefold(): text(value) for key, value in raw_row.items()}
            return
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook[meesho_export_sheet(path)]
            values_iter = sheet.iter_rows(values_only=True)
            headers = [text(value).casefold() for value in next(values_iter, ())]
            for values in values_iter:
                yield {headers[i]: text(v) for i, v in enumerate(values) if i < len(headers)}
        finally:
            workbook.close()

    def _load_ajio(self, path: Path) -> None:
        """Build the AJIO style codes from the JioCode and Colour columns."""
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook[AJIO_SHEET_NAME]
        rows = sheet.iter_rows(min_row=2, values_only=True)
        headers = [text(value).casefold() for value in next(rows)]
        at = {name: index for index, name in enumerate(headers)}
        if "jiocode" not in at or "color" not in at:
            workbook.close()
            raise SystemExit(f"{path.name}: {AJIO_SHEET_NAME} has no JioCode/Color columns")
        for values in rows:
            jiocode = text(values[at["jiocode"]]).strip()
            code = ajio_style_code(jiocode, values[at["color"]])
            if not code:
                continue
            self.ajio_code_by_jiocode[jiocode] = code
            self.ajio_code_by_style[jiocode[:AJIO_STYLE_DIGITS]].add(code)
            self.stats[f"ajio: {path.name}"] += 1
        workbook.close()

    @staticmethod
    def _only(values: set[str]) -> str:
        return next(iter(values)) if len(values) == 1 else ""

    def for_row(self, channel: str, sku_code: str, listing_id: str, size_sku: str) -> list[str]:
        """Return the identifier values for one MasterSheet row."""
        myntra = myntra_sku_code = flipkart = meesho_product = meesho_catalog = ""
        meesho_identifier = amazon = ajio = ""

        if channel.startswith("MYNTRA"):
            myntra = self.myntra_style_by_sku_id.get(listing_id, "")
            if not myntra:
                myntra = self._only(self.myntra_style_by_seller.get(sku_code, set()))
            myntra_sku_code = self.myntra_sku_code_by_sku_id.get(listing_id, "")
        elif channel == "FLIPKART":
            flipkart = self.flipkart_fsn_by_listing.get(listing_id, "")
            if not flipkart:
                flipkart = self._only(self.flipkart_fsn_by_seller.get(sku_code, set()))
            if not flipkart and size_sku:
                flipkart = self._only(self.flipkart_fsn_by_size_sku.get(size_sku, set()))
        elif channel == "MEESHO":
            meesho_product = listing_id.split("_")[0]
            if not meesho_product.isdigit():
                meesho_product = ""
            meesho_catalog = self.meesho_catalog_by_product.get(meesho_product, "")
            # The identifier sits on the product, so every size shares it.
            meesho_identifier = self.meesho_identifier_by_product.get(meesho_product, "")
            if not meesho_identifier:
                meesho_identifier = self.meesho_identifier_by_sku_id.get(listing_id, "")
        elif channel.startswith("AMAZON"):
            amazon = self.amazon_asin_by_listing.get(listing_id, "")
            if not amazon and listing_id.upper().startswith("B0") and len(listing_id) == 10:
                amazon = listing_id.upper()
            if not amazon:
                amazon = self._only(self.amazon_asin_by_seller.get(sku_code, set()))
        elif channel.startswith("AJIO"):
            # The OMS listing id is the size-level JioCode; the sheet turns it
            # into the style code. Fall back to the style group when that exact
            # size is missing from the sheet but its colour is unambiguous.
            ajio = self.ajio_code_by_jiocode.get(listing_id, "")
            if not ajio and listing_id.isdigit():
                ajio = self._only(self.ajio_code_by_style.get(
                    listing_id[:AJIO_STYLE_DIGITS], set()
                ))

        return [
            myntra, myntra_sku_code, flipkart, meesho_product, meesho_catalog,
            meesho_identifier, amazon, ajio,
        ]


def combined_portal_rows(portal_dir: Path, colors: ColorIndex | None = None):
    """Every portal export, merged into one normalised listing table."""
    stats = Counter()

    def emit(portal, path, brand, listing, style, seller, size, title, status, color=""):
        parsed = parse_and_clean(seller) or parse_and_clean(f"{style}-{size}" if style and size else "")
        if not color and colors is not None and parsed:
            color = colors.for_row(parsed.normalized, parsed.my_sku, style, listing)
        stats[portal] += 1
        return [
            portal, path.name, brand or None, listing or None, style or None,
            seller or None, size or None, color or None,
            parsed.my_sku if parsed else None,
            parsed.normalized if parsed else None,
            title or None, status or None,
        ]

    rows = []
    for path, loader in portal_files(portal_dir):
        if loader is load_myntra_csv:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for raw in csv.DictReader(handle):
                    row = {text(k).casefold(): text(v) for k, v in raw.items()}
                    rows.append(emit(
                        "MYNTRA", path, row.get("brand", ""), row.get("sku id", ""),
                        row.get("style id", ""), row.get("seller sku code", ""),
                        row.get("size", ""), row.get("style name", ""),
                        row.get("listing status description", ""),
                    ))
        elif loader is load_amazon_txt:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for raw in csv.DictReader(handle, delimiter="\t"):
                    row = {text(k).casefold(): text(v) for k, v in raw.items()}
                    rows.append(emit(
                        "AMAZON", path, "", row.get("listing-id", ""),
                        row.get("asin1", "") or row.get("product-id", ""),
                        row.get("seller-sku", ""), "", row.get("item-name", ""),
                        row.get("status", ""),
                    ))
        elif loader is load_flipkart_xls:
            book = xlrd.open_workbook(path, on_demand=True)
            sheet = book.sheet_by_index(0)
            headers = [text(sheet.cell_value(0, col)).casefold() for col in range(sheet.ncols)]
            for row_idx in range(2, sheet.nrows):
                row = {headers[col]: text(sheet.cell_value(row_idx, col)) for col in range(sheet.ncols)}
                rows.append(emit(
                    "FLIPKART", path, "", row.get("listing id", ""),
                    row.get("flipkart serial number", ""), row.get("seller sku id", ""),
                    "", row.get("product title", ""), row.get("listing status", ""),
                ))
            book.release_resources()
        elif loader is load_meesho_xlsx:
            workbook = load_workbook(path, read_only=True, data_only=True)
            sheet = workbook["Inventory-Update-Data-Fill This"]
            values_iter = sheet.iter_rows(values_only=True)
            headers = [text(v).casefold() for v in next(values_iter)]
            next(values_iter, None)
            for values in values_iter:
                row = {headers[i]: text(v) for i, v in enumerate(values) if i < len(headers)}
                rows.append(emit(
                    "MEESHO", path, "", row.get("product id", ""),
                    row.get("catalog id", ""), row.get("style id", ""),
                    row.get("variation", ""), row.get("product name", ""),
                    row.get("stock", ""),
                ))
            workbook.close()
        elif loader is load_jio_xlsx:
            workbook = load_workbook(path, read_only=True, data_only=True)
            sheet = workbook[AJIO_SHEET_NAME]
            values_iter = sheet.iter_rows(min_row=2, values_only=True)
            headers = [text(v).casefold() for v in next(values_iter)]
            for values in values_iter:
                row = {headers[i]: text(v) for i, v in enumerate(values) if i < len(headers)}
                rows.append(emit(
                    "AJIO", path, "", row.get("jiocode", ""),
                    row.get("seller style code", ""), row.get("seller sku", ""),
                    row.get("size", ""), "", "", row.get("color", ""),
                ))
            workbook.close()
        elif loader is load_nykaa_csv:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for raw in csv.DictReader(handle):
                    row = {text(k).casefold(): text(v) for k, v in raw.items()}
                    rows.append(emit(
                        "NYKAA", path, row.get("brand name", ""), row.get("nykaa sku code", ""),
                        "", row.get("vendor sku code", ""), "", "", row.get("inventory", ""),
                    ))
        elif loader is load_snapdeal_xlsx:
            workbook = load_workbook(path, read_only=True, data_only=True)
            sheet = first_sheet(workbook)
            values_iter = sheet.iter_rows(values_only=True)
            headers = [text(v).casefold() for v in next(values_iter)]
            for values in values_iter:
                row = {headers[i]: text(v) for i, v in enumerate(values) if i < len(headers)}
                if not row.get("supc"):
                    continue
                rows.append(emit(
                    "SNAPDEAL", path, "", row.get("supc", ""), "",
                    row.get("sku code", ""), "", row.get("product name", ""),
                    row.get("enabled by seller", ""),
                ))
            workbook.close()
    return rows, stats


def read_master(path: Path):
    workbook = load_workbook(path, data_only=True)
    sheet = workbook[MASTER_SHEET]
    rows = sheet.iter_rows(values_only=True)
    headers = [text(value) for value in next(rows)]
    if headers[: len(BASE_COLUMNS)] != list(BASE_COLUMNS):
        raise SystemExit(f"Unexpected MasterSheet columns: {headers}")
    # Read by header, not by position, so a column added to MASTER_COLUMNS
    # lands in its own slot instead of shifting everything after it.
    width = len(MASTER_COLUMNS)
    target = {name: index for index, name in enumerate(MASTER_COLUMNS)}
    moves = [(source, target[name]) for source, name in enumerate(headers) if name in target]
    unknown = [name for name in headers if name and name not in target]
    if unknown:
        print(f"IGNORED COLUMNS\t{', '.join(unknown)}")
    for name in MASTER_COLUMNS:
        if name not in headers:
            print(f"NEW COLUMN\t{name}")
    data = []
    for values in rows:
        row = [None] * width
        for source, destination in moves:
            if source < len(values):
                row[destination] = values[source]
        data.append(row)
    # Carry over the column widths the user tuned in Excel, keyed by header
    # name so inserting a column does not hand its width to its neighbour.
    widths = {}
    for position, name in enumerate(headers, start=1):
        dimension = sheet.column_dimensions.get(get_column_letter(position))
        if name and dimension is not None and dimension.width:
            widths[name] = dimension.width
    workbook.close()
    return data, widths


def learn_mappings(rows: list[list]):
    """Learn the manual conventions already recorded in MasterSheet."""
    final_my = defaultdict(Counter)
    design_no = defaultdict(Counter)
    launch_date = defaultdict(Counter)
    for row in rows:
        my_sku, final = text(row[5]), text(row[8])
        if my_sku and final:
            final_my[my_sku][final] += 1
        if final:
            if text(row[9]):
                design_no[final][text(row[9])] += 1
            if row[10] is not None:
                launch_date[final][row[10]] += 1

    def collapse(counters):
        return {key: counter.most_common(1)[0][0] for key, counter in counters.items()}

    return collapse(final_my), collapse(design_no), collapse(launch_date)


SUPPORTING_DIR = ROOT / "supporting"
FINAL_SKU_SHEET = SUPPORTING_DIR / "Final Sku Sheet.xlsx"
FABRIC_CODE_SHEET = SUPPORTING_DIR / "Fabric Code.xlsx"
LAUNCH_DATE_SHEET = SUPPORTING_DIR / "Launch Dates.xlsx"


class FinalSkus:
    """FINAL SKU / FINAL MY SKU as recorded in ``Final Sku Sheet.xlsx``.

    The sheet has the columns SIZE SKU, MY SKU, FINAL SIZE SKU and FINAL MY SKU,
    and is the single authority for the two FINAL columns of the master.
    """

    def __init__(self, path: Path):
        self.by_size: dict[str, tuple[str, str]] = {}
        self.by_family: dict[str, str] = {}
        # The sheet as read, for master.db: SIZE SKU -> (MY SKU, FINAL SIZE SKU, FINAL MY SKU).
        self.sheet_rows: dict[str, tuple[str, str, str]] = {}
        if not path.is_file():
            print(f"FINAL SKU SHEET\tnot found: {path.name} (FINAL columns left as they are)")
            return
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        values_iter = sheet.iter_rows(values_only=True)
        headers = [text(value).upper() for value in next(values_iter, ())]
        missing = {"SIZE SKU", "MY SKU", "FINAL SIZE SKU", "FINAL MY SKU"} - set(headers)
        if missing:
            workbook.close()
            raise SystemExit(f"{path.name} is missing column(s): {', '.join(sorted(missing))}")
        at = {name: headers.index(name) for name in headers}
        conflicts = Counter()
        for values in values_iter:
            def cell(name):
                index = at[name]
                return text(values[index]) if index < len(values) else ""
            size_sku, my_sku = cell("SIZE SKU"), cell("MY SKU")
            final_sku, final_my = cell("FINAL SIZE SKU"), cell("FINAL MY SKU")
            if size_sku:
                self.sheet_rows[size_sku] = (my_sku, final_sku, final_my)
            if size_sku and final_sku:
                key = size_sku.upper()
                if key in self.by_size and self.by_size[key] != (final_sku, final_my):
                    conflicts["SIZE SKU"] += 1
                self.by_size[key] = (final_sku, final_my)
            if my_sku and final_my:
                key = my_sku.upper()
                if key in self.by_family and self.by_family[key] != final_my:
                    conflicts["MY SKU"] += 1
                self.by_family[key] = final_my
        workbook.close()
        print(
            f"FINAL SKU SHEET\t{path.name}\tsize SKUs {len(self.by_size)}"
            f"\tfamilies {len(self.by_family)}"
            f"\tconflicting rows (last one wins) {sum(conflicts.values())}"
        )

    def lookup(self, my_sku: str, size_sku: str) -> tuple[str, str] | None:
        """Return ``(FINAL SKU, FINAL MY SKU)`` for a row, or None if not listed."""
        exact = self.by_size.get(size_sku.upper())
        if exact:
            return exact
        final_my = self.by_family.get(my_sku.upper())
        if final_my and size_sku and size_sku.upper().startswith(my_sku.upper()):
            return final_my + size_sku[len(my_sku):], final_my
        return None


def apply_final_skus(rows: list[list], finals: FinalSkus) -> None:
    """Overwrite FINAL SKU and FINAL MY SKU from ``Final Sku Sheet.xlsx``.

    Runs after every other rule so the sheet's values are what gets saved.
    """
    my_at = MASTER_COLUMNS.index("MY SKU")
    size_at = MASTER_COLUMNS.index("SIZE SKU")
    final_at = MASTER_COLUMNS.index("FINAL SKU")
    final_my_at = MASTER_COLUMNS.index("FINAL MY SKU")
    stats = Counter()
    for row in rows:
        size_sku = text(row[size_at])
        found = finals.lookup(text(row[my_at]), size_sku)
        if found is None:
            continue
        match = "by SIZE SKU" if size_sku.upper() in finals.by_size else "by MY SKU"
        final_sku, final_my = found
        if text(row[final_at]) == final_sku and text(row[final_my_at]) == final_my:
            stats[f"same ({match})"] += 1
            continue
        row[final_at] = final_sku
        row[final_my_at] = final_my or None
        stats[f"updated ({match})"] += 1
    for label in ("updated (by SIZE SKU)", "updated (by MY SKU)",
                  "same (by SIZE SKU)", "same (by MY SKU)"):
        print(f"FINAL SKU SHEET\t{label}\t{stats[label]}")


def read_sku_sheet(path: Path, value_headers: tuple[str, ...]) -> dict[str, object]:
    """Read a two-column supporting sheet: SKU -> value, blanks skipped.

    ``value_headers`` lists the spellings the value column may carry (the
    fabric sheet, for one, is headed ``FABRCI CODE``). A merged cell -- the
    fabric code is merged over each SKU group -- counts for every row it
    spans, not only the top one that Excel stores the value in.
    """
    if not path.is_file():
        print(f"SUPPORTING\tnot found: {path.name} (left as it is)")
        return {}
    # Not read-only: merged ranges are only available on a fully loaded sheet.
    workbook = load_workbook(path, data_only=True)
    sheet = workbook.worksheets[0]
    merged = {}
    for cells in sheet.merged_cells.ranges:
        top_left = sheet.cell(cells.min_row, cells.min_col).value
        for row_no in range(cells.min_row, cells.max_row + 1):
            for col_no in range(cells.min_col, cells.max_col + 1):
                merged[(row_no, col_no)] = top_left
    values_iter = (
        tuple(merged.get((row_no, col_no), value) for col_no, value in enumerate(values, start=1))
        for row_no, values in enumerate(sheet.iter_rows(values_only=True), start=1)
    )
    headers = [text(value).upper() for value in next(values_iter, ())]
    value_at = next((headers.index(name) for name in value_headers if name in headers), None)
    if "SKU" not in headers or value_at is None:
        workbook.close()
        raise SystemExit(f"{path.name} needs a SKU column and one of: {', '.join(value_headers)}")
    sku_at = headers.index("SKU")
    found, conflicts = {}, 0
    for values in values_iter:
        sku = text(values[sku_at]).upper() if sku_at < len(values) else ""
        value = values[value_at] if value_at < len(values) else None
        if not sku or not text(value):
            continue
        if sku in found and text(found[sku]) != text(value):
            conflicts += 1
        found[sku] = value
    workbook.close()
    print(f"SUPPORTING\t{path.name}\tSKUs with a value {len(found)}"
          f"\tconflicting rows (last one wins) {conflicts}")
    return found


def as_date(value):
    """A launch date as a datetime, whether the sheet stored a date or text."""
    if isinstance(value, datetime):
        return value
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text(value), pattern)
        except ValueError:
            continue
    return None


def apply_supporting_sheets(rows: list[list], fabric_path: Path, launch_path: Path) -> None:
    """Fill DESIGN-NO and LAUNCH DATE from the sheets in ``supporting/``.

    Both sheets are keyed by family SKU, looked up under FINAL MY SKU first and
    MY SKU second. ``Fabric Code.xlsx`` is the authority for DESIGN-NO: a blank
    is filled and a different value is corrected. ``Launch Dates.xlsx`` only
    fills a blank LAUNCH DATE; a date already recorded is kept.
    """
    fabric = read_sku_sheet(fabric_path, ("FABRIC CODE", "FABRCI CODE", "DESIGN-NO"))
    launch = read_sku_sheet(launch_path, ("DATE", "LAUNCH DATE"))
    my_at = MASTER_COLUMNS.index("MY SKU")
    final_my_at = MASTER_COLUMNS.index("FINAL MY SKU")
    design_at = MASTER_COLUMNS.index("DESIGN-NO")
    launch_at = MASTER_COLUMNS.index("LAUNCH DATE")
    stats = Counter()

    def lookup(table, row):
        for at in (final_my_at, my_at):
            key = text(row[at]).upper()
            if key and key in table:
                return table[key]
        return None

    for row in rows:
        code = text(lookup(fabric, row))
        if code:
            current = text(row[design_at])
            if current == code:
                stats["DESIGN-NO same"] += 1
            else:
                stats["DESIGN-NO corrected" if current else "DESIGN-NO filled"] += 1
                row[design_at] = code
        if row[launch_at] in (None, ""):
            raw = lookup(launch, row)
            if raw is not None:
                date = as_date(raw)
                if date is None:
                    stats["LAUNCH DATE unreadable in sheet"] += 1
                else:
                    row[launch_at] = date
                    stats["LAUNCH DATE filled"] += 1
    for label in ("DESIGN-NO filled", "DESIGN-NO corrected", "DESIGN-NO same",
                  "LAUNCH DATE filled", "LAUNCH DATE unreadable in sheet"):
        print(f"SUPPORTING\t{label}\t{stats[label]}")


def derive_final(my_sku: str, size_sku: str, final_my_map: dict[str, str]) -> tuple[str, str]:
    final_my = final_my_map.get(my_sku, my_sku)
    if size_sku and my_sku and size_sku.startswith(my_sku):
        return final_my + size_sku[len(my_sku):], final_my
    return size_sku, final_my


# ---------------------------------------------------------------- the update

def load_oms_rows(portal_dir: Path):
    """Read the OMS channel-listing export into memory.

    The export prefixes every channel with the seller entity
    (``BINDAL EXPORTS LIMITED - Amazon``); MasterSheet keeps the bare channel.
    """
    found = find_oms_export(portal_dir)
    if found is None:
        raise SystemExit(
            f"No OMS channel-listing export (*{OMS_NAME_HINT}*.csv, loose or "
            f"zipped) found in {portal_dir}"
        )
    source, entry = found
    holder, reader = open_oms_rows(source, entry)
    rows = []
    channels = Counter()
    try:
        for row_idx, raw_row in enumerate(reader, start=2):
            row = {text(key).casefold(): text(value) for key, value in raw_row.items()}
            channel = CHANNEL_ENTITY_PREFIX.sub("", row.get("channel name", ""))
            rows.append((
                row_idx,
                row.get("channel listing sku code", ""),
                row.get("channel listing id", ""),
                channel,
                row.get("product skucode", ""),
            ))
            channels[channel] += 1
    finally:
        holder.close()
    label = source.name if entry is None else f"{source.name}::{entry}"
    print(f"OMS EXPORT\t{label}\t{len(rows)} rows")
    for channel, count in channels.most_common():
        print(f"  channel\t{channel}\t{count}")
    return rows


def listing_only_results(input_rows, records: list[PortalRecord]):
    """Build master rows for listings the OMS mapping has not caught up with.

    A marketplace listing that appears in a listing file but nowhere in the OMS
    channel-listing export still belongs in the master -- everything a channel
    sells should be there. Such a row carries no ``Product SkuCode``, because
    there is no OMS mapping code to record, and that column is left blank. MY
    SKU and SIZE SKU come from the listing file's own seller SKU, exactly as
    they do for a listing the export does know about.

    The channel name comes from the listing file itself: whichever channel the
    rest of that file's rows resolve to in the export. One file is one seller
    account on one marketplace, so its remaining rows belong to that same
    channel.
    """
    channel_by_key: dict[tuple[str, str], str] = {}
    for _row_idx, raw_a, raw_b, channel, _reference in input_rows:
        portal = input_portal(channel)
        if not portal:
            continue
        for key in (normalize_key(raw_a), normalize_key(raw_b)):
            if key:
                channel_by_key.setdefault((portal, key), channel)

    file_channels: dict[str, Counter] = defaultdict(Counter)
    unmatched: list[PortalRecord] = []
    for record in records:
        known = [
            channel_by_key[(record.portal, key)]
            for _, key in record.keys
            if (record.portal, key) in channel_by_key
        ]
        if known:
            file_channels[record.source_file].update(known)
        else:
            unmatched.append(record)

    results: list[MasterResult] = []
    seen: set[tuple[str, str]] = set()
    added, skipped = Counter(), Counter()
    for record in unmatched:
        if record.status != "USABLE" or not record.listing_id:
            skipped[record.source_file] += 1
            continue
        ranked = file_channels[record.source_file].most_common(1)
        channel = ranked[0][0] if ranked else record.portal
        key = row_key(channel, record.listing_id)
        if key in seen:
            skipped[record.source_file] += 1
            continue
        seen.add(key)
        results.append(MasterResult(
            original_row=0,
            # The OMS export puts the seller SKU in Channel Listing SKU Code, so
            # a listing-only row is written the same way and stays comparable.
            channel_sku=record.seller_sku or record.channel_sku,
            listing_id=record.listing_id,
            channel=channel,
            product_reference="",
            my_sku=record.my_sku,
            size_sku=record.size_sku,
            mapping_source="Listing file only (not in OMS mapping)",
            portal=record.portal,
            reference_files=record.source_file,
            match_field=record.candidate_source,
            status="MAPPED",
            reference_check="NO OMS MAPPING",
        ))
        added[record.source_file] += 1

    for source_file in sorted(set(added) | set(skipped)):
        print(
            f"LISTING ONLY\t{source_file}\tadded {added[source_file]}"
            f"\tno usable SKU {skipped[source_file]}"
        )
    print(f"LISTING ONLY\ttotal\t{sum(added.values())} listings not in the OMS mapping")
    return results


def resolve_listings(portal_dir: Path):
    """Run the mapping pipeline.

    Returns the rows destined for the master and the raw OMS export rows.
    """
    input_rows = load_oms_rows(portal_dir)
    records = load_portal_records(portal_dir)
    if not records:
        raise SystemExit(f"No portal records could be loaded from {portal_dir}")

    usable_index, all_key_index = build_index(records)
    results, stats, _recoveries, _conflicts = map_input(
        input_rows, records, usable_index, all_key_index
    )
    postprocess_results(results)
    results.extend(listing_only_results(input_rows, records))
    brand_stats = map_result_brands(results, portal_dir)

    mapped = [result for result in results if not is_parent_or_no_size(result)]
    print(
        f"RESOLVED\t{len(mapped)} of {len(results)} listings"
        f"\tbrand mapped {brand_stats['status:MAPPED']}"
        f"\tbrand blank {brand_stats['status:NO BRAND EVIDENCE']}"
    )
    return mapped, input_rows


def build_master_rows(mapped, existing: list[list], finals: FinalSkus):
    """Merge freshly resolved listings into the existing master rows."""
    final_my_map, design_map, launch_map = learn_mappings(existing)
    # Final Sku Sheet.xlsx outranks what the master has learnt, so a new row's
    # DESIGN-NO and LAUNCH DATE are looked up under the sheet's FINAL MY SKU.
    final_my_map.update(finals.by_family)
    print(
        f"LEARNED\tFINAL MY SKU families={len(final_my_map)}"
        f"\tDESIGN-NO={len(design_map)}\tLAUNCH DATE={len(launch_map)}"
    )

    known = {row_key(row[2], row[1]) for row in existing}
    new_rows, unmapped, seen = [], [], set()
    for result in mapped:
        key = row_key(result.channel, result.listing_id)
        if key in known or key in seen:
            continue
        seen.add(key)
        head = [
            text(result.channel_sku), text(result.listing_id), key[0],
            text(result.brand) or None, text(result.product_reference) or None,
        ]
        my_sku, size_sku = text(result.my_sku), text(result.size_sku)
        if not size_sku:
            # The master only ever holds rows that carry a sized SKU.
            unmapped.append(head)
            continue
        final_sku, final_my = (
            finals.lookup(my_sku, size_sku) or derive_final(my_sku, size_sku, final_my_map)
        )
        new_rows.append(head + [
            my_sku or None, size_sku or None, final_sku or None, final_my or None,
            design_map.get(final_my) or None, launch_map.get(final_my),
        ] + [None] * (len(MASTER_COLUMNS) - len(BASE_COLUMNS)))

    live = {row_key(result.channel, result.listing_id) for result in mapped}
    stale = sum(1 for row in existing if row_key(row[2], row[1]) not in live)
    print(f"NEW ROWS\t{len(new_rows)}")
    print(f"NEW WITHOUT SKU (parked)\t{len(unmapped)}")
    print(f"KEPT (no longer in export)\t{stale}")
    return new_rows, unmapped


def sync_product_reference(rows: list[list], input_rows) -> None:
    """Make ``Product SkuCode (Reference Only)`` equal the OMS export's value.

    The column is a straight copy of the export's ``Product SkuCode``, blank
    included. A row is found by Channel Name + Channel Listing Id; a row whose
    listing id has left the export falls back to Channel Name + Channel Listing
    SKU Code, when that names a single Product SkuCode. A row the export does
    not carry either way keeps what it has.
    """
    by_id: dict[tuple[str, str], str] = {}
    by_code: dict[tuple[str, str], set[str]] = defaultdict(set)
    for _row_idx, channel_sku, listing_id, channel, product in input_rows:
        label = channel_label(channel)
        by_id[row_key(label, listing_id)] = text(product)
        if text(channel_sku):
            by_code[(label, text(channel_sku).upper())].add(text(product))

    at = MASTER_COLUMNS.index("Product SkuCode (Reference Only)")
    stats = Counter()
    for row in rows:
        key = row_key(row[2], row[1])
        if key in by_id:
            value, match = by_id[key], "by listing id"
        else:
            values = by_code.get((key[0], text(row[0]).upper()), set())
            if len(values) != 1:
                stats["not in OMS export (kept)"] += 1
                continue
            value, match = next(iter(values)), "by SKU code"
        current = text(row[at])
        if current == value:
            stats[f"same ({match})"] += 1
            continue
        stats[f"{'changed' if current else 'filled'} ({match})"] += 1
        row[at] = value or None
    for label in ("changed (by listing id)", "filled (by listing id)", "same (by listing id)",
                  "changed (by SKU code)", "filled (by SKU code)", "same (by SKU code)",
                  "not in OMS export (kept)"):
        print(f"PRODUCT SKUCODE\t{label}\t{stats[label]}")


REFRESH_COLUMNS = ("SIZE SKU",)


def refresh_mapped_columns(existing: list[list], mapped) -> None:
    """Re-sync SIZE SKU on rows that are already in the master.

    ``SIZE SKU`` is rebuilt from the channel's own seller SKU -- the listing
    files, or the seller SKU the OMS export carries in ``Channel Listing SKU
    Code`` -- so it follows whatever the marketplace currently lists.
    Everything else on the row -- FINAL SKU, FINAL MY SKU, DESIGN-NO, LAUNCH
    DATE and the portal ids -- is left exactly as it is. A blank in the fresh
    result never clears a value that is already recorded, so a row whose seller
    SKU has gone missing keeps what it has. ``Product SkuCode (Reference
    Only)`` is handled by ``sync_product_reference``.
    """
    fresh = {}
    for result in mapped:
        fresh[row_key(result.channel, result.listing_id)] = (text(result.size_sku),)

    offsets = [MASTER_COLUMNS.index(name) for name in REFRESH_COLUMNS]
    changed, added, unchanged = Counter(), Counter(), Counter()
    for row in existing:
        values = fresh.get(row_key(row[2], row[1]))
        if values is None:
            continue
        for name, at, value in zip(REFRESH_COLUMNS, offsets, values):
            if not value:
                continue
            current = text(row[at])
            if current == value:
                unchanged[name] += 1
            elif current:
                row[at] = value
                changed[name] += 1
            else:
                row[at] = value
                added[name] += 1
    for name in REFRESH_COLUMNS:
        print(
            f"REFRESHED\t{name}\tchanged {changed[name]}"
            f"\tfilled blank {added[name]}\tsame {unchanged[name]}"
        )


# The two SKU columns that end in a size, and the two that hold only a family.
# Both kinds drop their colour words; only the sized ones are re-parsed to check
# the result is still a readable SKU.
SIZED_SKU_COLUMNS = ("SIZE SKU", "FINAL SKU")
FAMILY_SKU_COLUMNS = ("MY SKU", "FINAL MY SKU")


def enforce_sku_rules(rows: list[list]) -> None:
    """Hold every row to the two rules the SKU columns are built on.

    Colour is recorded in the COLOR column, so it is never part of any SKU:
    ``E-18-PINK-M`` becomes ``E-18-M`` and ``K-19-BLACK`` becomes ``K-19``, in
    the hand-maintained FINAL SKU and FINAL MY SKU as much as in MY SKU and SIZE
    SKU. A colour dropped from a row whose COLOR cell is still empty is written
    into that cell first, so the colour moves to where it belongs instead of
    being lost. And MY SKU is always the family of SIZE SKU rather than a
    separate reading of the seller SKU, so the two can never disagree.

    This runs over every row, not only the ones the current export still
    carries, so a listing that has since dropped out of the export is held to
    the same rules.
    """
    sized = [MASTER_COLUMNS.index(name) for name in SIZED_SKU_COLUMNS]
    families = [MASTER_COLUMNS.index(name) for name in FAMILY_SKU_COLUMNS]
    my_at = MASTER_COLUMNS.index("MY SKU")
    size_at = MASTER_COLUMNS.index("SIZE SKU")
    color_at = MASTER_COLUMNS.index(COLOR_COLUMN)
    stats = Counter()

    for row in rows:
        dropped: list[str] = []
        for name, at in zip(SIZED_SKU_COLUMNS + FAMILY_SKU_COLUMNS, sized + families):
            value = text(row[at])
            colourless = without_colour(value)
            if not value or colourless == value:
                continue
            # Only drop the colour when what is left is still a usable SKU; a
            # style whose whole name is a colour word keeps the spelling it has.
            usable = (
                bool(parse_and_clean(colourless)) if at in sized
                else any(character.isalpha() for character in colourless)
            )
            if not usable:
                stats[f"{name} kept (colour is the whole name)"] += 1
                continue
            dropped.extend(token for token in value.split("-") if token in COLOUR_TOKENS)
            row[at] = colourless
            stats[f"{name} colour dropped"] += 1

        if dropped and not text(row[color_at]):
            # Keep the colour the SKU was carrying rather than losing it: the
            # COLOR column is where it belongs.
            seen = list(dict.fromkeys(dropped))
            row[color_at] = " ".join(token.title() for token in seen)
            stats["COLOR filled from the dropped colour"] += 1

        size_sku = text(row[size_at])
        if not size_sku:
            continue
        parsed = parse_and_clean(size_sku)
        if parsed is None:
            stats["SIZE SKU left unparsed"] += 1
        elif text(row[my_at]) != parsed.my_sku:
            row[my_at] = parsed.my_sku
            stats["MY SKU resynced to its SIZE SKU"] += 1

    for label in (
        [f"{name} colour dropped" for name in SIZED_SKU_COLUMNS + FAMILY_SKU_COLUMNS]
        + ["COLOR filled from the dropped colour", "MY SKU resynced to its SIZE SKU",
           "SIZE SKU left unparsed"]
        + sorted(key for key in stats if key.endswith("(colour is the whole name)"))
    ):
        print(f"SKU RULES\t{label}\t{stats[label]}")


# AJIO JIOCODE is rebuilt from the AJIO sheet on every run rather than only
# filled when blank: it is a derived value, so the sheet is its authority and
# not whatever the master happens to already hold. MYNTRA SKU CODE likewise
# comes straight from the Myntra listing's "sku code" for the row's sku id.
AUTHORITATIVE_ID_COLUMNS = frozenset({"AJIO JIOCODE", "MYNTRA SKU CODE"})


def fill_portal_listing_date(rows: list[list], ids: PortalIds) -> None:
    """Give every row the date its FINAL SKU first went live on Myntra.

    The Myntra rows' sku ids give each FINAL SKU its earliest ``style
    catalogued date`` across the Myntra accounts; that date is then written to
    the FINAL SKU's rows on every portal. A FINAL SKU Myntra does not list
    falls back to the earliest date of its FINAL MY SKU. It is rebuilt every
    run, and a row with neither keeps what it has.
    """
    final_at = MASTER_COLUMNS.index("FINAL SKU")
    final_my_at = MASTER_COLUMNS.index("FINAL MY SKU")
    date_at = MASTER_COLUMNS.index(PORTAL_DATE_COLUMN)
    by_final: dict[str, datetime] = {}
    by_family: dict[str, datetime] = {}

    def keep_earliest(table, key, listed):
        if key and (key not in table or listed < table[key]):
            table[key] = listed

    for row in rows:
        if not channel_label(row[2]).startswith("MYNTRA"):
            continue
        listed = ids.myntra_listed_by_sku_id.get(text(row[1]))
        if listed is None:
            continue
        keep_earliest(by_final, text(row[final_at]).upper(), listed)
        keep_earliest(by_family, text(row[final_my_at]).upper(), listed)

    stats = Counter()
    for row in rows:
        listed = by_final.get(text(row[final_at]).upper())
        match = "by FINAL SKU"
        if listed is None:
            listed = by_family.get(text(row[final_my_at]).upper())
            match = "by FINAL MY SKU"
        if listed is None:
            stats["not on Myntra (kept)"] += 1
            continue
        stats[f"same ({match})" if row[date_at] == listed else f"set ({match})"] += 1
        row[date_at] = listed
    for label in ("set (by FINAL SKU)", "set (by FINAL MY SKU)", "same (by FINAL SKU)",
                  "same (by FINAL MY SKU)", "not on Myntra (kept)"):
        print(f"{PORTAL_DATE_COLUMN}\t{label}\t{stats[label]}")


def fill_derived_columns(rows: list[list], portal_dir: Path, colors: ColorIndex) -> None:
    """Fill the portal id and colour columns, but only where still blank.

    ``AUTHORITATIVE_ID_COLUMNS`` are the exception: those are rewritten from the
    portal export whenever it resolves a value, and keep what the master already
    holds only when it does not.
    """
    ids = PortalIds(portal_dir)
    fill_portal_listing_date(rows, ids)
    filled, kept, corrected = Counter(), Counter(), Counter()
    base = MASTER_COLUMNS.index(ID_COLUMNS[0])
    color_at = MASTER_COLUMNS.index(COLOR_COLUMN)
    for row in rows:
        channel = channel_label(row[2])
        values = None
        for offset, name in enumerate(ID_COLUMNS):
            current = text(row[base + offset])
            if current and name not in AUTHORITATIVE_ID_COLUMNS:
                kept[name] += 1
                filled[name] += 1
                continue
            if values is None:
                values = ids.for_row(channel, text(row[0]), text(row[1]), text(row[6]))
            if values[offset]:
                if current and current != values[offset]:
                    corrected[name] += 1
                row[base + offset] = values[offset]
                filled[name] += 1
            elif current:
                kept[name] += 1
                filled[name] += 1
        # Colour comes last: it keys off the ids just filled in above. AJIO is
        # the exception -- ColorIndex is keyed by the raw size-level JioCode,
        # which is the OMS listing id, not the style code in AJIO JIOCODE.
        if text(row[color_at]):
            kept[COLOR_COLUMN] += 1
            filled[COLOR_COLUMN] += 1
        else:
            color = colors.for_row(
                text(row[6]), text(row[5]),
                text(row[base + ID_COLUMNS.index("MYNTRA STYLE ID")]),
                text(row[1]) if channel.startswith("AJIO") else "",
            )
            if color:
                row[color_at] = color
                filled[COLOR_COLUMN] += 1
    for name in ID_COLUMNS + (COLOR_COLUMN,):
        note = f"\t(corrected: {corrected[name]})" if corrected[name] else ""
        print(
            f"FILLED\t{name}\t{filled[name]}/{len(rows)}"
            f"\t(kept existing: {kept[name]}){note}"
        )


