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

**Sheets** (laid out like the owner's Myntra calculator, PRICING/MYNTRA CAL V2; owner, 14 Nov 2026)

* *Summary*: build time, tier, how a settlement is made, and per Brand-Category: listings,
  package, commission % / CLF / fixed fee range, and the check (formula = Flipkart), plus how
  often the workbook's SP equals Flipkart's exact SP in TP TO SP.
* *TP TO SP* (`Table5`): every FSN of the Final TP file. TP, Brand-Category, then per price slot
  **P** (price point), **F** (fixed fee × 1.18), **C** (commission % × 1.18), **L** (CLF) and
  **S** (the SP that reaches the TP in that slot); **SP** = the first S inside its slot. Then the
  forward check: Sell Price, Slab Slot, Slab Price Point, CLF, Seller Price, Comm %, Comm,
  Fixed Fee, GST on Charges, TDS_TCS, Payout, OG TP, DELTA; and Flipkart's exact SP / status,
  current SP / settlement, MRP, Discount %, REMARK (Rs 109, 90% discount, fee-slab gap, Flipkart
  differs). The SP aims at TP − 0.5, since Flipkart rounds the settlement.
* *SP TO TP* (`Table4`): every live listing; Sell Price (yellow) is yours to change; Payout is
  the settlement, beside Flipkart's own settlement, Delta, the Final TP and a remark.
* *Parameter*: TDS_TCS (0.6% / 1.05 of seller price), GST_On_Charges (18%), and the CLF table
  (CLF_Keys / CLF_Rates) by Brand-Category and slot.
* *Parameter1*: `Commission` and `Fixed_Fee` (incl. collection and shipping) by Brand-Category
  and slot (Commission_Keys / _Rates, Fixed_Fee_Keys / _Rates).
* *Parameter Rate Card*: Flipkart's rate card call, for reference (base rates only).
* *_Calc_Config*: Price_Slots, Price_Thresholds (price < threshold), Slot_Starts. The slots are
  every slab end of any Brand-Category, so the fees are constant inside a slot.

Checked 14 Nov in Excel: SP TO TP gives Flipkart's settlements exactly (110 → 29, 499 → 401,
501 → 371, 1,501 → 1,086, 2,000 → 1,506 for All About You apparel sets); TP TO SP gives
DELTA 0.

The formulas are for the group's common package; a listing with another package can differ by
a few rupees of CLF. Flipkart's exact column (TP TO SP) is per listing.
