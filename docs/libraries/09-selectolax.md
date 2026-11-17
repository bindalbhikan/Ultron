# 9. selectolax — HTML

**Status**: ✅ 17 Nov 2026

**Why**: BeautifulSoup is slow (pure Python); selectolax (Lexbor, C) parses 10-30x faster with CSS selectors, and
Lexbor follows the HTML5 rules browsers use (an unclosed `<td>` closes, where Python's html.parser nests it in the
cell before).

**Done**
* One place reads HTML: `ultron/core/html.py` — `parse(html)`, `select` / `select_one` (CSS), `text()` (BeautifulSoup's
  `get_text(" ", strip=True)`: pieces stripped, joined by a space, script / style left out), `text_of(node)` (spaces
  folded), `attr` / `node["href"]`, `children("td")` (direct child elements), `next_sibling("dd")`, `parent_of("li")`.
  selectolax when installed (GitHub, the PCs: the `workings` extra); else BeautifulSoup with the same calls, so the
  seller-neutral core (`ultron.portals.omsguru`) still installs pure Python on Android / Termux.
* Moved onto it: `portals/omsguru.py` (login message, warehouses, exports, failed listings, channels, push inventory,
  order list, order page), `portals/omsguru_orders.py` (the order list rows), `workings/portals/omsguru_returns.py`
  (return lookups), `workings/vms/myntra.py` (VMS list, label link), `workings/erp_oms_return/accept.py` (order
  details, Quick Returns forms). No BeautifulSoup call is left outside `core/html.py`.

**Checked before the switch** (real OMSGuru pages, GET only; the Quick Returns search in manual mode accepts
nothing): every page saved once, then read by the old code (a `main` worktree, BeautifulSoup) and the new: all 80
results the same — 2 warehouses, 12 channels, failed / unmanaged listings, 428 + 769 orders listed, 435 order lines,
70 order pages (items, status history, the return reader, the ERP order details; 25 of them returned orders), 233
VMS rows over both warehouses, the 2 Quick Returns forms' SKU rows. Both engines of `core/html.py` give the same
answers on 195 order pages and 8 list pages: selectolax 2.2 s, BeautifulSoup 34.7 s (16x). `tests/test_html.py`.

(The page store of the check keyed pages by URL and warehouse: OMSGuru shows another warehouse's orders on the same
list URL after `setCurWarehouse`.)
