# 5. pydantic v2 — portal answers checked

**Status**: ⏳

**Why**: "data must never be wrong". A portal that renames a field or a column today gives empty or 0
values far down the line (OMSGuru's new SLA column, 5 Nov 2026). A pydantic model per portal answer fails
at once, with the field named. Rust core: fast enough for every row of a big seller.

**Plan**
1. Models for the answers the bots read most: Myntra report jobs and SPF claims, AJIO orders / RTV,
   Flipkart report centre, OMSGuru order lines, SRM ledger lines.
2. Validate at the portal client, before any working sees the data; a failed check names the field on Telegram.
