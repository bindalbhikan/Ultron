# 9. selectolax — HTML

**Status**: ⏳

**Why**: BeautifulSoup is slow (pure Python); selectolax (Lexbor, C) parses 10-30x faster with CSS
selectors. Already used in some places; OMSGuru's order pages and lists still go through BeautifulSoup.

**Plan**: `omsguru.py` / `omsguru_orders.py` / `omsguru_returns.py` first (the most pages); a parity test
on saved pages: the same rows out.
