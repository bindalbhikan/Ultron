"""OMSGuru sale quantities: GROSS units per order date and report block.

The order list lines come from ultron.portals.omsguru_orders (the same for every seller);
this maps their channels to the blocks of the SALE REPORT sheet. Cancelled orders stay in GROSS,
as in the original main.py.
"""
from __future__ import annotations

from collections import Counter
from datetime import date

from ultron.portals.omsguru import OmsGuruClient
from ultron.portals.omsguru_orders import (CANCELLED, LIST_CAP, channel_names, order_lines,  # noqa: F401
                                             units_by_channel)

# The first matching keyword decides the destination block of the sale report.
# Cocoblu (an Amazon seller channel) has its own block since Oct 2026; Snapdeal is not reported.
IGNORE = "-"
CHANNEL_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("cocoblu",), "COCOBLU"),
    (("amazon",), "AZ/FX/FBA"),
    (("meesho",), "MEESHO"),
    (("ajio",), "AJIO B2C"),
    (("flipkart",), "FLIPKART"),
    (("myntra",), "MYNTRA"),
    (("nykaa",), "NYKAA"),
    (("snapdeal",), IGNORE),
)
OMS_BLOCKS = sorted({block for _, block in CHANNEL_RULES} - {IGNORE})


def block_for(channel_name: str) -> str | None:
    _, separator, marketplace = channel_name.partition(" - ")
    label = " ".join((marketplace if separator else channel_name).split()).upper()
    name = label.casefold()
    for keywords, block in CHANNEL_RULES:
        if any(k in name for k in keywords):
            return block
    if label in {"", "-"}:
        return None
    if label in {"TOTAL", "SJIT", "FBF", "AZ/FX/FBA", "AMAZON/FLEX/FBA"} or label.startswith("="):
        return f"OMS {label}"
    return label


def report_blocks(names: dict[str, str]) -> list[str]:
    """Include newly configured marketplaces even before their first order."""
    found = {block_for(name) for cid, name in names.items() if cid and name}
    return [*OMS_BLOCKS, *sorted(found - set(OMS_BLOCKS) - {None, IGNORE})]


def gross_by_day(client: OmsGuruClient, days: list[date], max_pages: int = 80):
    """Return gross units, unmapped units and all configured report blocks."""
    units, _, names = units_by_channel(client, days, max_pages)
    gross, unmapped = blocks_of(units, names)
    return gross, unmapped, report_blocks(names)


def blocks_of(units: Counter, names: dict[str, str]):
    """units_by_channel's Counter[(day, channel id)] as (Counter[(day, block)], Counter of unmapped channel units)."""
    gross: Counter = Counter()
    unmapped: Counter = Counter()
    for (day, chid), qty in units.items():
        name = names.get(chid, chid or "(blank)")
        block = block_for(name) if names.get(chid) and chid else None
        if block == IGNORE:
            continue
        if block:
            gross[(day, block)] += qty
        else:
            unmapped[name] += qty
    return gross, unmapped
