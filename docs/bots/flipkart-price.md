# Flipkart Final TP update — `python run.py flipkart-price`

**When**: 8:00 AM IST daily (`flipkart-price.yml`, started by the worker's cron, `SCHEDULE` in
`worker/src/worker.js`). By hand: `/fkprice` (or `/fkprice dry`: plan only) on Telegram, the
Flipkart menu button, or the workflow. Built on the owner's instruction of 14 Nov 2026: this
working changes live prices, but only toward the owner's own Final TP.

**Input**: the newest `.xlsx` in Drive AGENT WORK > FLIPKART > PRICE UPDATE (14 Nov:
`FK Settlement Update NOV.xlsx`, 6,130 FSNs), columns **Flipkart Serial Number** (FSN) and
**Final TP** (the bank settlement wanted, rounded to whole rupees). Other columns are ignored.
An FSN listed twice with two different TPs stops the run (the owner says which). `--file` gives
a local workbook instead.

**What it does**

1. Reads every ACTIVE listing from Seller Hub's listing table (`FlipkartClient.listings`: sku,
   listing id, FSN, vertical, MRP, `ssp` selling price, `esp` bank settlement). The read must
   return every listing (6,388 on 14 Nov) or the run stops before changing anything.
2. Listings whose settlement already equals the Final TP are **not touched**. FSNs in the file
   that are not live are listed ("Not live").
3. Every other listing moves toward its TP in steps Flipkart accepts:
   * up: at most **+20%** of the current settlement a step. Some listings have a lower limit
     (14 Nov: "upto 10% of current value"): the % in Flipkart's refusal is used and the step is
     tried again at once. At most **2 increases a day**: today's increases (Seller Hub's price
     history, also the ones made by hand) count.
   * down: at most **−30%** a step, repeated in the same run.
   * the selling price for the settlement comes from **Flipkart's own calculator** (reverse:
     settlement → price). A settlement inside a fee-slab gap has no price
     (`DELTA_IN_SETTLEMENT_VALUE`): the nearest reachable one within the step limits is used,
     never below the TP. If the TP itself is unreachable, the listing stays at that nearest value.
   * price floor **Rs 109**: a step that would go below it stops at 109 first (its settlement
     from the forward calculator); the next step goes lower.
   * discount at most **90%**: a TP whose price would be under 10% of MRP is not set, and named.
   * at most `FK_PRICE_MAX_STEPS` (6) steps per listing a run.
4. What is not at TP today (2-a-day limit, a refusal) continues on the next run.

**Output**: `output/flipkart-price/Flipkart Final TP update <date time>.xlsx` (sheets *Listings*:
start / now / status per listing; *Steps*: every step, its settlement and price, and Flipkart's
answer; *Not live*) and a Telegram summary with the file.

**Test of 14 Nov 2026**: AAY-COORD-CT-1-P8-L, TP 373: 333 → 366 (10% limit) → 373, price 448 →
470, checked on Seller Hub (listing table and price history). Dry run: 3,565 listings at TP,
2,545 to change (2,518 up, 27 down), 20 FSNs not live.

**Calls**: see `docs/PORTALS.md` (Flipkart, listings and prices).
