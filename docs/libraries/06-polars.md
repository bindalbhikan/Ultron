# 6. Polars — tables instead of pandas

**Status**: ⏳

**Why**: 5-20x faster than pandas with far less memory, multi-core, lazy queries, strict types (ids stay
text: no more `46148.0`). For Bindal's files (a few MB) the gain is seconds; for a seller with 100x the orders
it is the difference between a run that finishes and one that runs out of memory.

**Where pandas is now**: ~38 files, ~900 calls (business report 6, return analysis 4, AJIO TAT 4, grouping 3,
VMS 2, portal sale 2, Flipkart price 2, and one each in the other workings).

**Plan**
1. `ultron/core/frames.py`: read CSV / xlsx (calamine) into Polars with id columns as text; write xlsx with
   xlsxwriter; a `to_pandas()` bridge while both live side by side.
2. Benchmark: Bindal's real reports and the same x10 / x100, time and memory, pandas vs Polars.
3. Working by working, the heaviest and seller-neutral first: business report, return analysis, portal sale,
   Myntra history, then the daily ones. Each with a **parity test**: old and new code on the same input
   files give the same output, cell by cell, before the switch.
4. The owner's own engines (SPF `engine.py`, grouping engine: "rules unchanged") only with the owner's OK.
