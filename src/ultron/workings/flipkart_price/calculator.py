"""Flipkart calculator workbook: TP -> SP, SP -> TP and the fee parameters, per brand and category.

Flipkart's settlement for a selling price (SP), as its own calculator gives it (checked 14 Nov 2026):

    seller price  s = SP - customer logistics fee (CLF, by price slab)
    commission      = s x commission %      (by brand + category + price slab: FashFun 14% flat,
                                             All About You / Dressberry slab rates, e.g. 3% at 400)
    fees            = commission + fixed fee (Rs 10, Rs 20 above 1,500) + collection + shipping
    settlement      = s - fees x 1.18 (GST) - s / (1 + product GST) x 0.6% (TCS 0.5% + TDS 0.1%)

The slabs are not in Flipkart's rate card call (it shows the base 14%), so they are read from the
calculator: for every brand + category, a sample of its live listings is priced every Rs 10 from
100 to 3,000 and every change of CLF / commission % / fixed fee is narrowed to the rupee. The
workbook's formulas use that table; Flipkart's own exact answer per listing sits beside them.

Laid out like the owner's Myntra calculator (PRICING/MYNTRA CAL V2): Summary, TP TO SP (every FSN
of the Final TP file: P / F / C / L / S blocks per price slot, SP, the forward check, Flipkart's
exact SP), SP TO TP (every live listing), Parameter (CLF), Parameter1 (Commission, Fixed_Fee),
Parameter Rate Card (Flipkart's rate card), _Calc_Config (Price_Slots, Price_Thresholds).
Written to Drive AGENT WORK > FLIPKART > CALCULATOR as "Flipkart Calculator.xlsx". Reads only.
"""
from __future__ import annotations

import argparse
import math
import logging
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import xlsxwriter

from ..core import telegram
from ..core.app import run_bot
from ..core.config import output_dir
from ..portals.flipkart import FlipkartClient
from .pipeline import fetch_target_file, read_targets
from ..core import clients

log = logging.getLogger("bindal.flipkart_calc")

LOW, HIGH, STEP = 100, 3000, 10      # prices scanned
GST_ON_FEES = 0.18
TCS_TDS = 0.006                      # TCS 0.5% + TDS 0.1% of the taxable value
FOLDER = ("FLIPKART", "CALCULATOR")
NAME = "Flipkart Calculator.xlsx"
PARAMS = ("clf", "rate", "fixed", "collection", "shipping", "gst")


def key_of(brand: str, vertical: str) -> str:
    return f"{(brand or '').strip()}-{(vertical or '').strip()}"


def package(x: dict) -> tuple:
    """(weight kg, length, breadth, height cm) of a listing's first package."""
    pk = next(iter((x.get("packages") or {}).values()), {}) or {}
    return tuple(pk.get(k) for k in ("weight", "length", "breadth", "height"))


def point(ans: dict) -> dict | None:
    """The fee parameters of one calculator answer (Fulfilled by You / NON_FBF split)."""
    sp, s = ans.get("selling_price"), ans.get("seller_price")
    zone = next((z for z in ans.get("zone_level_splits") or [] if z.get("fulfilment_type") == "NON_FBF"), None)
    if not sp or s is None or not zone:
        return None
    sc = zone["settlement_calculator"]
    fee = {f["feeKey"]: float(f["nationalValue"]) for f in sc.get("feeGroups") or []}
    tcs = float((sc.get("tcs") or {}).get("national") or 0)
    gst = 0.05
    if tcs >= 1:                     # taxable value = s / (1 + gst); TCS is 0.5% of it
        gst = min((0.05, 0.12, 0.18), key=lambda g: abs(s / (tcs / 0.005) - 1 - g))
    rate = round(fee.get("platform_fee", 0) / s * 100, 1) / 100 if s else 0.0
    return {"sp": int(sp), "clf": int(ans.get("customer_logistics_fee") or 0), "rate": rate,
            "fixed": fee.get("closing_fee", 0.0), "collection": fee.get("payment_fee", 0.0),
            "shipping": fee.get("forward_shipping_fee", 0.0), "gst": gst,
            "settlement": int(ans.get("settlement_value") or zone["national"]["settlement_value"])}


def settlement(sp: float, p: dict) -> int:
    """The formula the workbook uses (kept in step with the Excel formulas below)."""
    s = sp - p["clf"]
    fees = s * p["rate"] + p["fixed"] + p["collection"] + p["shipping"]
    return int(round(s - fees * (1 + GST_ON_FEES) - s / (1 + p["gst"]) * TCS_TDS))


class Scanner:
    """Prices listings of one brand + category through Flipkart's calculator; one listing takes one
    price per call, so up to 50 prices go in one call spread over different listings."""

    def __init__(self, client: FlipkartClient, tier: str, listing_ids: list[str]):
        self.client, self.tier, self.ids = client, tier, listing_ids[:50]
        self.cache: dict[int, dict] = {}

    def prices(self, sps: list[int]) -> None:
        todo = [s for s in dict.fromkeys(sps) if s not in self.cache]
        for i in range(0, len(todo), len(self.ids)):
            part = todo[i:i + len(self.ids)]
            items = [{"listing_id": lid, "selling_price": sp} for lid, sp in zip(self.ids, part)]
            ans = self.client.calculator(items, self.tier)
            for lid, sp in zip(self.ids, part):
                p = point(ans.get(lid) or {})
                if p:
                    self.cache[sp] = p

    def same(self, a: int, b: int) -> bool:
        pa, pb = self.cache.get(a), self.cache.get(b)
        return bool(pa and pb) and all(pa[k] == pb[k] for k in PARAMS)

    def scan(self) -> list[dict]:
        """Slab table: [{from, to, clf, rate, fixed, collection, shipping, gst}], to the rupee."""
        grid = list(range(LOW, HIGH + 1, STEP))
        self.prices(grid)
        pairs = [(a, b) for a, b in zip(grid, grid[1:]) if a in self.cache and b in self.cache and not self.same(a, b)]
        while pairs:                     # bisect every change of slab, all of them together
            mids = [(a + b) // 2 for a, b in pairs]
            self.prices(mids)
            nxt = []
            for (a, b), m in zip(pairs, mids):
                if m not in self.cache:
                    continue
                lo, hi = (m, b) if self.same(a, m) else (a, m)
                if hi - lo > 1:
                    nxt.append((lo, hi))
            pairs = nxt
        rows, cur = [], None
        for sp in sorted(self.cache):
            p = self.cache[sp]
            if cur and all(cur[k] == p[k] for k in PARAMS):
                cur["to"] = sp
                continue
            if cur:
                cur["to"] = sp - 1
            cur = {"from": sp, "to": sp, **{k: p[k] for k in PARAMS}}
            rows.append(cur)
        if cur:
            cur["to"] = 99999
        if rows:
            rows[0]["from"] = 0
        return rows

    def check(self) -> tuple[int, int]:
        """(prices checked, formula == Flipkart) over every price the scan read."""
        table = self.scan_cache or []
        ok = n = 0
        for sp, p in self.cache.items():
            row = next((r for r in table if r["from"] <= sp <= r["to"]), None)
            if row:
                n += 1
                ok += settlement(sp, row) == p["settlement"]
        return n, ok

    scan_cache: list[dict] | None = None


def run(args) -> int:
    started = datetime.now()
    client = clients.flipkart()
    tier = client.tier()
    listings = client.listings("ACTIVE")
    groups: dict[str, list[dict]] = defaultdict(list)
    for x in listings:
        if x.get("service_profile") in ("NON_FBF", "FBF_AND_NON_FBF"):
            groups[key_of(x.get("brand"), x.get("vertical"))].append(x)

    params, rate_cards, checks, info = [], [], {}, {}
    random.seed(7)
    for key, xs in sorted(groups.items()):
        own = [x for x in xs if x.get("service_profile") == "NON_FBF"] or xs
        # the CLF also depends on the package (weight / size): price the most common package only
        common = Counter(package(x) for x in own).most_common(1)[0][0]
        own = [x for x in own if package(x) == common]
        sample = random.sample(own, min(50, len(own)))
        sc = Scanner(client, tier, [x["listing_id"] for x in sample])
        table = sc.scan()
        sc.scan_cache = table
        checks[key] = sc.check()
        brand, vertical = sample[0].get("brand") or "", sample[0].get("vertical") or ""
        info[key] = {"brand": brand, "category": vertical, "listings": len(xs),
                     "package": "{} kg, {}x{}x{}".format(*common)}
        for r in table:
            params.append({"Key": key, "Brand": brand, "Category": vertical, "SP from": r["from"], "SP to": r["to"],
                           "CLF": r["clf"], "Commission %": r["rate"], "Fixed fee": r["fixed"],
                           "Collection fee": r["collection"], "Shipping fee": r["shipping"], "Product GST %": r["gst"],
                           "Package (kg, cm)": "{} kg, {}x{}x{}".format(*common)})
        log.info("%s: %d slabs, formula = Flipkart at %d of %d prices", key, len(table), checks[key][1], checks[key][0])
        try:
            rc = client.rate_card(sample[0]["product_id"], tier)
            for part, v in rc.items():
                for slab in ((v or {}).get("slabs") or {}).get("asp") or []:
                    ap = slab.get("agreementParameters") or {}
                    rate_cards.append({"Key": key, "Fee": (v or {}).get("displayName") or part,
                                       "Price from": slab.get("start"), "Price to": slab.get("end"),
                                       "Rate / fee": ap.get("fixedRate") or ap.get("prepaid") or ap.get("localFee")})
        except Exception as exc:  # noqa: BLE001 - the rate card is extra; the slab table is what counts
            log.warning("Rate card of %s not read: %s", key, exc)

    # TP TO SP: every FSN of the Final TP file, with Flipkart's exact price for its TP
    tp_rows = []
    try:
        path = Path(args.file) if args.file else fetch_target_file()
        targets = read_targets(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Final TP file not read: %s", exc)
        targets = {}
    by_fsn = defaultdict(list)
    for x in listings:
        by_fsn[str(x.get("product_id") or "").upper()].append(x)
    want = [(x, tp) for fsn, tp in targets.items() for x in by_fsn.get(fsn, [])]
    exact = client.calculator([{"listing_id": x["listing_id"], "type": "reverse", "settlement_value": tp}
                               for x, tp in want], tier) if want else {}
    for x, tp in want:
        a = exact.get(x["listing_id"]) or {}
        tp_rows.append({"FSN": x["product_id"], "SKU": x["sku_id"], "Brand": x.get("brand"), "Category": x.get("vertical"),
                        "MRP": x.get("mrp"), "Final TP": tp, "SP by Flipkart": a.get("selling_price") or None,
                        "Flipkart status": a.get("settlement_status"), "Current SP": x.get("ssp"),
                        "Current settlement": x.get("esp")})
    sp_rows = [{"FSN": x["product_id"], "SKU": x["sku_id"], "Brand": x.get("brand"), "Category": x.get("vertical"),
                "MRP": x.get("mrp"), "Current SP": x.get("ssp"), "Settlement by Flipkart": x.get("esp")}
               for x in sorted(listings, key=lambda x: (x.get("brand") or "", x.get("vertical") or "", x["sku_id"]))]

    slots = slots_of(params)
    by_key = defaultdict(list)
    for p in params:
        by_key[p["Key"]].append(p)
    same = near = known = 0
    for t in tp_rows:
        if t["SP by Flipkart"]:
            known += 1
            d = abs(price_for(t["Final TP"], by_key.get(key_of(t["Brand"], t["Category"]), []), slots)
                    - t["SP by Flipkart"])
            same += d == 0
            near += d <= 1
    # 14 Nov: Flipkart's reverse calculator is itself off by Rs 1 at times (TP 417 -> SP 548, but its
    # forward calculator gives 416 at 548 and 417 at 549): a Rs 1 difference is Flipkart's rounding
    log.info("TP TO SP: formula SP = Flipkart SP for %d, within Rs 1 for %d of %d listings", same, near, known)
    checks["_tp_to_sp"] = (known, same)
    checks["_tp_to_sp_1"] = (known, near)
    out = output_dir("flipkart-calc") / NAME
    write_workbook(out, started, tier, params, rate_cards, checks, tp_rows, sp_rows, info)
    link = ""
    if not args.no_upload:
        link = upload(out)
    total = sum(n for k, (n, _) in checks.items() if not k.startswith("_"))
    good = sum(ok for k, (_, ok) in checks.items() if not k.startswith("_"))
    msg = [f"🧮 <b>Flipkart calculator · {started:%d %b}</b>",
           f"{len(groups)} brand-categories, {len(params)} price slabs (tier {telegram.esc(tier)})",
           f"Formula = Flipkart's calculator at {good:,} of {total:,} prices checked",
           f"TP TO SP: {len(tp_rows):,} listings; formula SP = Flipkart's reverse SP for {same:,}, within Rs 1 for "
           f"{near:,} of {known:,} (Flipkart's reverse is itself Rs 1 off at times)",
           f"SP TO TP: {len(sp_rows):,} listings",
           *([f'<a href="{link}">Flipkart Calculator.xlsx</a>'] if link else [])]
    text = "\n".join(msg)
    if args.no_telegram:
        print(text)
    else:
        telegram.send(text)
    return 0


def upload(path: Path) -> str:
    from ..core.drive import DriveFile, agent_folder
    folder = agent_folder()
    for name in FOLDER:
        folder = folder.subfolder(name, create=True)
    fid = folder.put(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return DriveFile(fid).url


def price_for(tp: int, rows: list[dict], slots: list[dict]) -> int | None:
    """The workbook's TP -> SP (TP TO SP sheet) in Python: per slot the SP whose rounded settlement
    reaches the TP (aiming at TP - 0.5), the first that falls inside its slot."""
    last = None
    for s in slots:
        p = next((r for r in rows if r["SP from"] <= s["start"] <= r["SP to"]), None)
        if p is None:
            continue
        fees = (p["Fixed fee"] + p["Collection fee"] + p["Shipping fee"]) * (1 + GST_ON_FEES)
        div = 1 - p["Commission %"] * (1 + GST_ON_FEES) - TCS_TDS / 1.05
        last = max(s["start"], math.ceil((tp - 0.5 + fees) / div + p["CLF"] - 1e-9))
        if last < s["threshold"]:
            return last
    return last


def slots_of(params: list[dict]) -> list[dict]:
    """The price slots shared by every Brand-Category (the Myntra calculator's P01..P30): every slab
    end of any group starts a new slot, so within a slot every group's fees are constant."""
    ends = sorted({int(p["SP to"]) for p in params if p["SP to"] < 99999})
    out, start = [], 0
    for e in ends:
        out.append({"start": start, "end": e, "label": e, "threshold": e + 1})
        start = e + 1
    out.append({"start": start, "end": 99999, "label": f"{start}+", "threshold": 1e99})
    return out


def write_workbook(out: Path, started, tier, params, rate_cards, checks, tp_rows, sp_rows, info) -> None:
    """The workbook, laid out like the owner's Myntra calculator (PRICING/MYNTRA CAL V2): Summary,
    TP TO SP (P / F / C / L / S slot blocks, SP, then the forward check), SP TO TP, Parameter (CLF),
    Parameter1 (Commission, Fixed_Fee), _Calc_Config (Price_Slots, Price_Thresholds, Slot_Starts)."""
    from xlsxwriter.utility import xl_col_to_name as col

    slots = slots_of(params)
    n = len(slots)
    keys = sorted({p["Key"] for p in params})
    by_key = defaultdict(list)
    for p in params:
        by_key[p["Key"]].append(p)

    def at(key: str, sp: int) -> dict:
        return next(p for p in by_key[key] if p["SP from"] <= sp <= p["SP to"])

    wb = xlsxwriter.Workbook(str(out))
    bold = wb.add_format({"bold": True})
    title = wb.add_format({"bold": True, "font_size": 14})
    head = wb.add_format({"bold": True, "bg_color": "#DDEBF7", "border": 1, "text_wrap": True, "valign": "top"})
    inp = wb.add_format({"bg_color": "#FFF2CC"})
    pct = wb.add_format({"num_format": "0.0%"})
    _num0 = wb.add_format({"num_format": "#,##0"})
    num2 = wb.add_format({"num_format": "#,##0.00"})
    sheets = {name: wb.add_worksheet(name) for name in
              ("Summary", "TP TO SP", "SP TO TP", "Parameter", "Parameter1", "Parameter Rate Card", "_Calc_Config")}

    # _Calc_Config: slot numbers, price points, thresholds (price < threshold), slot starts
    ws = sheets["_Calc_Config"]
    ws.write_row(0, 0, ["Slot", *range(1, n + 1)], bold)
    ws.write(1, 0, "Price Point", bold)
    ws.write(2, 0, "Threshold", bold)
    ws.write(3, 0, "Slot start", bold)
    for i, s in enumerate(slots, start=1):
        ws.write(1, i, s["label"])
        ws.write(2, i, s["threshold"])
        ws.write(3, i, s["start"])
    last = col(n)
    wb.define_name("Price_Slots", f"=_Calc_Config!$B$2:${last}$2")
    wb.define_name("Price_Thresholds", f"=_Calc_Config!$B$3:${last}$3")
    wb.define_name("Slot_Starts", f"=_Calc_Config!$B$4:${last}$4")

    # Parameter: constants + CLF (customer logistics fee) by Brand-Category and slot
    ws = sheets["Parameter"]
    ws.write(0, 0, "TDS_TCS", bold)
    ws.write(0, 1, TCS_TDS / 1.05)
    ws.write(0, 2, "TCS 0.5% + TDS 0.1% of the taxable value (seller price / 1.05, product GST 5%)")
    ws.write(1, 0, "GST_On_Charges", bold)
    ws.write(1, 1, GST_ON_FEES)
    ws.write(1, 2, "GST on commission and fees")
    wb.define_name("TDS_TCS", "=Parameter!$B$1")
    wb.define_name("GST_On_Charges", "=Parameter!$B$2")
    ws.write(3, 0, "Customer logistics fee (CLF, Rs) by price slot: seller price = SP - CLF", bold)
    hdr = ["Brand", "Category", "Vlookup", "Package (kg, cm)", *[s["label"] for s in slots]]
    ws.write_row(4, 0, hdr, head)
    for r, k in enumerate(keys, start=5):
        ws.write_row(r, 0, [info[k]["brand"], info[k]["category"], k, info[k]["package"]])
        ws.write_row(r, 4, [at(k, s["start"])["CLF"] for s in slots])
    r1, r2 = 6, len(keys) + 5
    wb.define_name("CLF_Keys", f"=Parameter!$C${r1}:$C${r2}")
    wb.define_name("CLF_Rates", f"=Parameter!$E${r1}:${col(3 + n)}${r2}")
    ws.set_column(0, 1, 16)
    ws.set_column(2, 2, 28)
    ws.set_column(3, 3, 20)

    # Parameter1: Commission (% of seller price) and Fixed_Fee (Rs, incl. collection + shipping)
    ws = sheets["Parameter1"]
    hdr = ["Brand", "Category", "Vlookup", *[s["label"] for s in slots]]
    ws.write_row(0, 0, hdr, head)
    for r, k in enumerate(keys, start=1):
        ws.write_row(r, 0, [info[k]["brand"], info[k]["category"], k])
        for i, s in enumerate(slots):
            ws.write(r, 3 + i, at(k, s["start"])["Commission %"], pct)
    c1, c2 = 2, len(keys) + 1
    wb.define_name("Commission_Keys", f"=Parameter1!$C${c1}:$C${c2}")
    wb.define_name("Commission_Rates", f"=Parameter1!$D${c1}:${col(2 + n)}${c2}")
    f0 = len(keys) + 3                       # Fixed_Fee header row (0-based)
    ws.write(f0 - 1, 0, "Fixed Fee (Rs, incl. collection fee and shipping fee)", bold)
    ws.write_row(f0, 0, hdr, head)
    for r, k in enumerate(keys, start=f0 + 1):
        ws.write_row(r, 0, [info[k]["brand"], info[k]["category"], k])
        for i, s in enumerate(slots):
            p = at(k, s["start"])
            ws.write(r, 3 + i, p["Fixed fee"] + p["Collection fee"] + p["Shipping fee"])
    wb.define_name("Fixed_Fee_Keys", f"=Parameter1!$C${f0 + 2}:$C${f0 + 1 + len(keys)}")
    wb.define_name("Fixed_Fee_Rates", f"=Parameter1!$D${f0 + 2}:${col(2 + n)}${f0 + 1 + len(keys)}")
    ws.set_column(0, 1, 16)
    ws.set_column(2, 2, 28)

    # TP TO SP: TP, then per slot P (price point), F (fixed fee x 1.18), C (commission x 1.18),
    # L (CLF), S (SP for the TP in that slot); SP = the first slot whose S lies in it; then the check
    ws = sheets["TP TO SP"]
    ids = ["FSN", "Brand", "Category", "SKU", "TP", "Brand-Category"]
    blocks = {b: [f"{b}{i:02d}" for i in range(1, n + 1)] for b in "PFCLS"}
    tail = ["SP", "Sell Price", "Slab Slot", "Slab Price Point", "CLF", "Seller Price", "Comm %", "Comm",
            "Fixed Fee", "GST on Charges", "TDS_TCS", "Payout", "OG TP", "DELTA", "SP by Flipkart",
            "Flipkart Status", "Current SP", "Current Settlement", "MRP", "Discount %", "REMARK"]
    cols = ids + blocks["P"] + blocks["F"] + blocks["C"] + blocks["L"] + blocks["S"] + tail
    ci = {c: i for i, c in enumerate(cols)}
    L = lambda name: col(ci[name])  # noqa: E731
    rows = len(tp_rows)
    ws.write_row(0, 0, cols, head)
    for r, t in enumerate(tp_rows, start=1):
        x = r + 1
        key = f"$F{x}"
        ws.write_row(r, 0, [t["FSN"], t["Brand"], t["Category"], t["SKU"], t["Final TP"]])
        ws.write_formula(r, 5, f'=B{x}&"-"&C{x}')
        for k in range(1, n + 1):
            p, f, c, l_, s = (L(f"{b}{k:02d}") for b in "PFCLS")
            ws.write_formula(r, ci[f"P{k:02d}"], f'=IFERROR(INDEX(Price_Slots,1,{k}),"")')
            ws.write_formula(r, ci[f"F{k:02d}"], f'=IF({p}{x}="","",IFERROR(INDEX(Fixed_Fee_Rates,MATCH({key},Fixed_Fee_Keys,0),{k})*(1+GST_On_Charges),0))')
            ws.write_formula(r, ci[f"C{k:02d}"], f'=IF({p}{x}="","",IFERROR(INDEX(Commission_Rates,MATCH({key},Commission_Keys,0),{k})*(1+GST_On_Charges),0))')
            ws.write_formula(r, ci[f"L{k:02d}"], f'=IF({p}{x}="","",IFERROR(INDEX(CLF_Rates,MATCH({key},CLF_Keys,0),{k}),0))')
            ws.write_formula(r, ci[f"S{k:02d}"], f'=IF({p}{x}="","",IFERROR(MAX(INDEX(Slot_Starts,1,{k}),'
                                                 f'ROUNDUP(($E{x}-0.5+{f}{x})/(1-{c}{x}-TDS_TCS)+{l_}{x},0)),""))')
        s1, sn = L("S01"), L(f"S{n:02d}")
        rng = f"{s1}{x}:{sn}{x}"
        ws.write_formula(r, ci["SP"], f'=IFERROR(INDEX({rng},1,MATCH(1,INDEX(({rng}<Price_Thresholds)*({rng}<>""),0),0)),"")')
        sell, slot, clf_, seller = (f"{L(c)}{x}" for c in ("Sell Price", "Slab Slot", "CLF", "Seller Price"))
        comm, fix, gst, tds = (f"{L(c)}{x}" for c in ("Comm", "Fixed Fee", "GST on Charges", "TDS_TCS"))
        ws.write_formula(r, ci["Sell Price"], f"={L('SP')}{x}")
        ws.write_formula(r, ci["Slab Slot"], f'=IFERROR(MATCH(1,INDEX(({sell}<Price_Thresholds)*(Price_Slots<>""),0),0),"")')
        ws.write_formula(r, ci["Slab Price Point"], f'=IFERROR(INDEX(Price_Slots,1,{slot}),"")')
        ws.write_formula(r, ci["CLF"], f"=IFERROR(INDEX(CLF_Rates,MATCH({key},CLF_Keys,0),{slot}),0)")
        ws.write_formula(r, ci["Seller Price"], f'=IFERROR({sell}-{clf_},"")')
        ws.write_formula(r, ci["Comm %"], f"=IFERROR(INDEX(Commission_Rates,MATCH({key},Commission_Keys,0),{slot}),0)", pct)
        ws.write_formula(r, ci["Comm"], f'=IFERROR({seller}*{L("Comm %")}{x},"")', num2)
        ws.write_formula(r, ci["Fixed Fee"], f"=IFERROR(INDEX(Fixed_Fee_Rates,MATCH({key},Fixed_Fee_Keys,0),{slot}),0)")
        ws.write_formula(r, ci["GST on Charges"], f'=IFERROR(({comm}+{fix})*GST_On_Charges,"")', num2)
        ws.write_formula(r, ci["TDS_TCS"], f'=IFERROR({seller}*TDS_TCS,"")', num2)
        ws.write_formula(r, ci["Payout"], f'=IFERROR(ROUND({seller}-{comm}-{fix}-{gst}-{tds},0),"")')
        ws.write_formula(r, ci["OG TP"], f"=E{x}")
        ws.write_formula(r, ci["DELTA"], f'=IFERROR({L("Payout")}{x}-{L("OG TP")}{x},"")')
        ws.write_row(r, ci["SP by Flipkart"], [t["SP by Flipkart"], t["Flipkart status"], t["Current SP"],
                                               t["Current settlement"], t["MRP"]])
        fk, mrp = f"{L('SP by Flipkart')}{x}", f"{L('MRP')}{x}"
        ws.write_formula(r, ci["Discount %"], f'=IF(OR({sell}="",N({mrp})=0),"",1-{sell}/{mrp})', pct)
        ws.write_formula(r, ci["REMARK"],
                         f'=IF({sell}="","no slab",IF(AND({fk}<>"",ABS(N({fk})-{sell})=1),"Flipkart reverse SP Rs 1 off (its rounding)",'
                         f'IF(AND({fk}<>"",{fk}<>{sell}),"Flipkart SP differs (package / slab)",'
                         f'IF({fk}="","TP in a fee-slab gap",IF({sell}<109,"below Rs 109",'
                         f'IF(N({mrp})>0,IF(1-{sell}/{mrp}>0.9,"over 90% discount",""),""))))))')
    ws.add_table(0, 0, max(rows, 1), len(cols) - 1, {"name": "Table5", "header_row": True, "autofilter": True,
                                                     "style": "Table Style Light 9",
                                                     "columns": [{"header": c} for c in cols]})
    ws.freeze_panes(1, 6)
    ws.set_column(0, 3, 16)
    ws.set_column(ci["P01"], ci[f"S{n:02d}"], 7)
    ws.set_column(ci["SP"], len(cols) - 1, 11)
    ws.set_column(ci["REMARK"], ci["REMARK"], 30)

    # SP TO TP: every live listing; Sell Price is yours to change (yellow), Payout is the settlement
    ws = sheets["SP TO TP"]
    cols = ["FSN", "Brand", "Category", "SKU", "Brand-Category", "MRP", "Sell Price", "Slab Slot", "Slab Price Point",
            "CLF", "Seller Price", "Comm %", "Comm", "Fixed Fee", "GST on Charges", "TDS_TCS", "Payout",
            "Settlement by Flipkart", "Delta", "TP", "Remark"]
    ci = {c: i for i, c in enumerate(cols)}
    ws.write_row(0, 0, cols, head)
    tp_of = {t["FSN"]: t["Final TP"] for t in tp_rows}
    for r, s in enumerate(sp_rows, start=1):
        x = r + 1
        key = f"$E{x}"
        ws.write_row(r, 0, [s["FSN"], s["Brand"], s["Category"], s["SKU"]])
        ws.write_formula(r, 4, f'=B{x}&"-"&C{x}')
        ws.write(r, 5, s["MRP"])
        ws.write(r, 6, s["Current SP"], inp)
        ws.write_formula(r, ci["Slab Slot"], f'=IFERROR(MATCH(1,INDEX((G{x}<Price_Thresholds)*(Price_Slots<>""),0),0),"")')
        ws.write_formula(r, ci["Slab Price Point"], f'=IFERROR(INDEX(Price_Slots,1,H{x}),"")')
        ws.write_formula(r, ci["CLF"], f"=IFERROR(INDEX(CLF_Rates,MATCH({key},CLF_Keys,0),H{x}),0)")
        ws.write_formula(r, ci["Seller Price"], f'=IFERROR(G{x}-J{x},"")')
        ws.write_formula(r, ci["Comm %"], f"=IFERROR(INDEX(Commission_Rates,MATCH({key},Commission_Keys,0),H{x}),0)", pct)
        ws.write_formula(r, ci["Comm"], f'=IFERROR(K{x}*L{x},"")', num2)
        ws.write_formula(r, ci["Fixed Fee"], f"=IFERROR(INDEX(Fixed_Fee_Rates,MATCH({key},Fixed_Fee_Keys,0),H{x}),0)")
        ws.write_formula(r, ci["GST on Charges"], f'=IFERROR((M{x}+N{x})*GST_On_Charges,"")', num2)
        ws.write_formula(r, ci["TDS_TCS"], f'=IFERROR(K{x}*TDS_TCS,"")', num2)
        ws.write_formula(r, ci["Payout"], f'=IFERROR(ROUND(K{x}-M{x}-N{x}-O{x}-P{x},0),"")')
        ws.write(r, ci["Settlement by Flipkart"], s["Settlement by Flipkart"])
        ws.write_formula(r, ci["Delta"], f'=IF(R{x}="","",IFERROR(Q{x}-R{x},""))')
        tpv = tp_of.get(s["FSN"])
        if tpv is not None:
            ws.write(r, ci["TP"], tpv)
        ws.write_formula(r, ci["Remark"], f'=IF(T{x}="","",IF(Q{x}=T{x},"at TP",IF(Q{x}<T{x},"below TP","above TP")))')
    ws.add_table(0, 0, max(len(sp_rows), 1), len(cols) - 1, {"name": "Table4", "style": "Table Style Light 9",
                                                             "columns": [{"header": c} for c in cols]})
    ws.freeze_panes(1, 0)
    ws.set_column(0, 4, 16)
    ws.set_column(5, len(cols) - 1, 11)

    # Parameter Rate Card: what Flipkart's rate card call shows (base rates, for reference)
    ws = sheets["Parameter Rate Card"]
    rc_cols = ["Key", "Fee", "Price from", "Price to", "Rate / fee"]
    ws.write_row(0, 0, rc_cols, head)
    for r, row in enumerate(rate_cards, start=1):
        ws.write_row(r, 0, [row.get(c) for c in rc_cols])
    ws.write(len(rate_cards) + 2, 0, "Flipkart's rate card shows the base commission; the commission charged "
             "(Parameter1) comes from Flipkart's own settlement calculator.")
    ws.set_column(0, 1, 28)
    ws.set_column(2, 4, 14)

    # Summary
    ws = sheets["Summary"]
    ws.write(0, 0, "Flipkart calculator", title)
    lines = [("Built", f"{started:%d %b %Y %H:%M}"), ("Seller tier", tier),
             ("Brand-Categories", len(keys)), ("Price slots", n),
             ("Listings in TP TO SP / SP TO TP", f"{len(tp_rows):,} / {len(sp_rows):,}"),
             ("TP TO SP: formula SP = Flipkart's reverse SP", "{1:,} of {0:,} listings".format(*checks.get("_tp_to_sp", (0, 0)))),
             ("TP TO SP: within Rs 1 of it", "{1:,} of {0:,} listings".format(*checks.get("_tp_to_sp_1", (0, 0)))),
             ("Why Rs 1", "Flipkart's reverse calculator rounds its SP; its own forward calculator then pays Rs 1 "
              "less at times (TP 417: reverse SP 548 pays 416; 549 pays 417). The workbook's SP pays the TP."),
             ("", ""),
             ("How a settlement is made", "Seller price = SP - CLF. Payout = seller price - Comm - Fixed Fee - "
              "GST on Charges (18%) - TDS_TCS (0.6% of seller price / 1.05)."),
             ("Where the rates come from", "Flipkart's own settlement calculator, every Rs 10 from 100 to 3,000 for "
              "each Brand-Category, every change narrowed to the rupee (Parameter, Parameter1, _Calc_Config)."),
             ("TP TO SP", "Type the TP: S01..Snn is the SP for each slot, SP the first that falls in its slot "
              "(as in the Myntra calculator). 'SP by Flipkart' is Flipkart's exact answer for the listing."),
             ("SP TO TP", "Type a Sell Price (yellow): Payout is the settlement.")]
    for i, (a, b) in enumerate(lines, start=2):
        ws.write(i, 0, a, bold)
        ws.write(i, 1, b)
    r0 = len(lines) + 4
    ws.write(r0 - 1, 0, "Brand-Categories", bold)
    shdr = ["Brand", "Category", "Listings", "Package (kg, cm)", "Commission % (low - high)", "CLF Rs (low - high)",
            "Fixed Fee Rs", "Prices checked", "Formula = Flipkart", "%"]
    ws.write_row(r0, 0, shdr, head)
    for i, k in enumerate(keys, start=r0 + 1):
        rows_k = by_key[k]
        cm = [p["Commission %"] for p in rows_k]
        cl = [p["CLF"] for p in rows_k]
        fx = sorted({p["Fixed fee"] + p["Collection fee"] + p["Shipping fee"] for p in rows_k})
        cnt, ok = checks.get(k, (0, 0))
        ws.write_row(i, 0, [info[k]["brand"], info[k]["category"], info[k]["listings"], info[k]["package"],
                            f"{min(cm):.0%} - {max(cm):.0%}", f"{min(cl)} - {max(cl)}",
                            " / ".join(f"{v:g}" for v in fx), cnt, ok])
        ws.write_formula(i, 9, f'=IF(H{i + 1}=0,"",I{i + 1}/H{i + 1})', pct)
    ws.set_column(0, 0, 30)
    ws.set_column(1, 1, 22)
    ws.set_column(2, 9, 16)
    ws.activate()
    wb.close()
    log.info("Written %s", out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py flipkart-calc", description="Flipkart TP / SP calculator workbook")
    p.add_argument("--file", help="the Final TP workbook (default: newest .xlsx in FLIPKART/PRICE UPDATE)")
    p.add_argument("--no-upload", action="store_true", help="keep the workbook in output/, do not put it on Drive")
    p.add_argument("--no-telegram", action="store_true", help="print the report instead of sending it")
    return run_bot("Flipkart calculator", p, run, argv)
