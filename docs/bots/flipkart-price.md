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
     (14 Nov: "upto 10% of current value", 247 of 479 in one part): the step is tried again at
     once at **9.68%** (owner, 14 Nov: 9.68% × 2 a day). At most **2 increases a day**: a 3rd (also after increases made by hand)
     is refused by Flipkart ("You can increase the bank settlement 2 times per day") and that
     listing waits for the next run.
   * down: at most **−29.68%** a step (0.32 points under Flipkart's 30%, owner 14 Nov), repeated
     in the same run.
   * the selling price for the settlement comes from **Flipkart's own calculator** (reverse:
     settlement → price). A settlement inside a fee-slab gap has no price
     (`DELTA_IN_SETTLEMENT_VALUE`), and Flipkart's reverse calculator also fails next to a slab
     edge. Then the price is searched with the **forward** calculator (SP → settlement, halving
     between Rs 109 and the MRP): on the last step the settlement nearest the TP within **±Rs 2**
     (exact first, then above; owner 14 Nov: "TP must match, try Rs 1-2 either side"), on a middle
     step the nearest inside the step limits. Example (All About You dress): SP 400 → 279,
     SP 401 → 288, so TP 286 → 288 (+2), TP 278 → 280 (+2). A listing already within Rs 2 that
     cannot get closer is reported as such.
   * price floor **Rs 109**: a step that would go below it stops at 109 first (its settlement
     from the forward calculator); the next step goes lower.
   * discount at most **90%**: a TP whose price would be under 10% of MRP is not set, and named.
   * at most `FK_PRICE_MAX_STEPS` (6) steps per listing a run.
4. What is not at TP today (2-a-day limit, a refusal) continues on the next run.

**GitHub matrix** (owner, 14 Nov 2026): one job managed ~5 listings a minute, too slow for ~2,500.
The workflow runs **5 parts at once** (`--part I/5`: each takes the listings whose listing-id
CRC32 mod 5 is its own, logs in on its own), then a **report** job decrypts the parts' outputs and
joins them (`--merge parts`): one Telegram message and one Excel. A failed part is named in the
message ("only N of 5 parts finished").

**TP update master** (owner, 14 Nov 2026; `flipkart_price/master.py`): Drive AGENT WORK > FLIPKART >
TP UPDATE MASTER > `FLIPKART TP UPDATE MASTER.xlsx`, one sheet per month. Columns FSN | SKU | Final TP,
then per day the date over two columns **Old TP | New TP** (the settlement before the day's first run
and after its last run). A listing gets its row the first time the update works on it. The report job
writes it after every run (not a dry run, not `--no-upload`) and it is the file sent on Telegram; the
run's own detailed Excel stays in the run's encrypted output. It is kept outside PRICE UPDATE, whose
newest .xlsx is the Final TP file. 14 Nov was seeded from the 3:18 PM listing read (before any change)
and the live settlements: 2,545 listings, 431 at TP.

**Telegram summary** (owner, 14 Nov: simple): at Final TP (and how many today), price updated
today, still pending (moved closer / not changed) with the reasons, not live.

**Run of 14 Nov 2026** (5 parts, 16:03–16:19): 3,566 at TP before, 2,532 listings changed;
most increases need 2–3 days (2 a day). Part 1: 920 steps made, 247 "10%" refusals retried.

**Output**: `<output folder>/flipkart-price/Flipkart Final TP update <date time>.xlsx` (sheets *Listings*:
start / now / status per listing; *Steps*: every step, its settlement and price, and Flipkart's
answer; *Not live*) and a Telegram summary with the file.

**Test of 14 Nov 2026**: AAY-COORD-CT-1-P8-L, TP 373: 333 → 366 (10% limit) → 373, price 448 →
470, checked on Seller Hub (listing table and price history). Dry run: 3,565 listings at TP,
2,545 to change (2,518 up, 27 down), 20 FSNs not live.

**Calls**: see `docs/PORTALS.md` (Flipkart, listings and prices).
