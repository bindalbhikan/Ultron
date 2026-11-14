# Flipkart calculator — `python run.py flipkart-calc`

**When**: 7:00 AM IST every Monday (`flipkart-calc.yml`, started by the worker's cron, `SCHEDULE`
in `worker/src/worker.js`). By hand: `/fkcalc` on Telegram, the Flipkart menu button
(🧮 Calculator), or the workflow. Reads only: no price is changed.

**Result**: `Flipkart Calculator.xlsx` in Drive AGENT WORK > FLIPKART > CALCULATOR (replaced in
place, same link), and a Telegram message with the link. Layout follows the owner's Myntra
calculator (PRICING/MYNTRA CAL V2).

**How Flipkart settles** (read from Flipkart's own calculator, 14 Nov 2026; Fulfilled by You):

* seller price = SP − customer logistics fee (CLF, by price slab and package: Rs 59–191)
* commission = seller price × commission %, by **brand + category** and price slab (FashFun /
  Serein 14% flat; All About You / Dressberry 0% to 200, 8% to 300, 3% to 499, 2% to 800,
  7% to 1,000, 13% above, for apparel sets). Flipkart's rate card call shows only the base 14%.
* fixed fee Rs 10 (Rs 20 above 1,500); collection fee and forward shipping 0
* settlement = seller price − (commission + fixed + collection + shipping) × 1.18 −
  seller price / (1 + product GST 5%) × 0.6% (TCS 0.5% + TDS 0.1%), rounded

**How the slabs are found**: for every brand + category, up to 50 of its live listings with the most
common package are priced together (one price per listing per call) every Rs 10 from 100 to
3,000. Every change of CLF / commission % / fixed fee is narrowed to the rupee by halving. The
formula is checked against every price read (Summary: "formula = Flipkart"; 14 Nov test,
All About You apparel set: 351 of 351).

**Sheets**

* *Summary*: build time, tier, how it works, the check per brand-category.
* *Calculator*: yellow cells: pick the Brand-Category, type a TP → SP, or an SP → settlement.
* *TP TO SP*: every FSN of the Final TP file (FLIPKART/PRICE UPDATE): Flipkart's exact SP for its
  TP (reverse calculator, the listing's own package), the workbook's SP, discount %, remark
  (fee-slab gap, below Rs 109, over 90% discount).
* *SP TO TP*: every live listing: its SP and Flipkart's settlement, the formula's settlement, and a
  "New SP" column to try a price.
* *Parameter*: the slab table (Brand-Category, SP from / to, CLF, commission %, fixed, collection,
  shipping, product GST, package) with the settlement at each slab's ends.
* *Rate card*: Flipkart's rate card (orchestrator) per brand-category, for reference.

The formulas are for the group's common package; a listing with another package can differ by
a few rupees of CLF. Flipkart's exact column (TP TO SP) is per listing.
