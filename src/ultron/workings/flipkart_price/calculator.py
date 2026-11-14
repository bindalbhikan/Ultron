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

Sheets: Summary, Calculator (enter brand, category, TP or SP), TP TO SP (every FSN of the Final TP
file), SP TO TP (every live listing), Parameter (the slab table), Rate card (Flipkart's rate card).
Written to Drive AGENT WORK > FLIPKART > CALCULATOR as "Flipkart Calculator.xlsx". Reads only.
"""
from __future__ import annotations

import argparse
import logging
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from ..core import telegram
from ..core.app import run_bot
from ..core.config import env, num, output_dir
from ..portals.flipkart import FlipkartClient
from .pipeline import fetch_target_file, read_targets

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
                ok += abs(settlement(sp, row) - p["settlement"]) <= 1
        return n, ok

    scan_cache: list[dict] | None = None


def run(args) -> int:
    started = datetime.now()
    client = FlipkartClient(env("FLIPKART_EMAIL"), env("FLIPKART_PASSWORD"))
    client.login()
    tier = client.tier()
    listings = client.listings("ACTIVE")
    groups: dict[str, list[dict]] = defaultdict(list)
    for x in listings:
        if x.get("service_profile") in ("NON_FBF", "FBF_AND_NON_FBF"):
            groups[key_of(x.get("brand"), x.get("vertical"))].append(x)

    params, rate_cards, checks = [], [], {}
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

    out = output_dir("flipkart-calc") / NAME
    write_workbook(out, started, tier, params, rate_cards, checks, tp_rows, sp_rows)
    link = ""
    if not args.no_upload:
        link = upload(out)
    total = sum(n for n, _ in checks.values())
    good = sum(ok for _, ok in checks.values())
    msg = [f"🧮 <b>Flipkart calculator · {started:%d %b}</b>",
           f"{len(groups)} brand-categories, {len(params)} price slabs (tier {telegram.esc(tier)})",
           f"Formula = Flipkart's calculator at {good:,} of {total:,} prices checked",
           f"TP TO SP: {len(tp_rows):,} listings · SP TO TP: {len(sp_rows):,}",
           *([f'<a href="{link}">Flipkart Calculator.xlsx</a>'] if link else [])]
    text = "\n".join(msg)
    if args.no_telegram:
        print(text)
    else:
        telegram.send(text)
    return 0


def upload(path: Path) -> str:
    from ..core.config import agent_work_id
    from ..core.drive import DriveFile, DriveFolder
    folder = DriveFolder(agent_work_id())
    for name in FOLDER:
        folder = folder.subfolder(name, create=True)
    fid = folder.put(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return DriveFile(fid).url


def write_workbook(out: Path, started, tier, params, rate_cards, checks, tp_rows, sp_rows) -> None:
    pm = pd.DataFrame(params)
    n = len(pm) + 1                                   # last data row of Parameter
    P = lambda col: f"Parameter!${col}$2:${col}${n}"  # noqa: E731
    KEY, FROM, TO, CLF, RATE, FIX, COLL, SHIP, GST = (P(c) for c in "ADEFGHIJK")

    def row_of(key_cell: str, sp_cell: str) -> str:
        return f"MATCH(1,INDEX(({KEY}={key_cell})*({FROM}<={sp_cell})*({TO}>={sp_cell}),0),0)"

    def settle(key_cell: str, sp_cell: str) -> str:
        r = row_of(key_cell, sp_cell)
        s = f"({sp_cell}-INDEX({CLF},{r}))"
        fees = f"({s}*INDEX({RATE},{r})+INDEX({FIX},{r})+INDEX({COLL},{r})+INDEX({SHIP},{r}))"
        return f"ROUND({s}-{fees}*{1 + GST_ON_FEES}-{s}/(1+INDEX({GST},{r}))*{TCS_TDS},0)"

    def price(key_cell: str, tp_cell: str) -> str:
        """The lowest SP whose settlement reaches the TP: the first slab (by price) that reaches it,
        inverted; at least that slab's start."""
        r = f"MATCH(1,INDEX(({KEY}={key_cell})*(Parameter!$N$2:$N${n}>={tp_cell}),0),0)"
        g = f"(1-INDEX({RATE},{r})*{1 + GST_ON_FEES}-{TCS_TDS}/(1+INDEX({GST},{r})))"
        fx = f"(INDEX({FIX},{r})+INDEX({COLL},{r})+INDEX({SHIP},{r}))*{1 + GST_ON_FEES}"
        return f"MAX(INDEX({FROM},{r}),ROUNDUP(({tp_cell}+{fx})/{g}+INDEX({CLF},{r}),0))"

    with pd.ExcelWriter(out, engine="xlsxwriter") as xw:
        wb = xw.book
        bold = wb.add_format({"bold": True})
        head = wb.add_format({"bold": True, "bg_color": "#DDEBF7", "border": 1, "text_wrap": True})
        inp = wb.add_format({"bg_color": "#FFF2CC", "border": 1})
        pct = wb.add_format({"num_format": "0.0%"})
        money = wb.add_format({"num_format": "#,##0"})

        # Summary
        ws = wb.add_worksheet("Summary")
        lines = [("Flipkart calculator", ""), ("Built", f"{started:%d %b %Y %H:%M}"), ("Seller tier", tier),
                 ("Brand-categories", len(checks)), ("Price slabs", len(pm)), ("", ""),
                 ("How it works", "Seller price = SP - CLF. Settlement = seller price - (commission + fixed + "
                  "collection + shipping) x 1.18 - seller price / (1 + product GST) x 0.6% (TCS + TDS)."),
                 ("", "CLF, commission % and fixed fee change by price slab and by brand + category (Parameter)."),
                 ("", "Slabs read from Flipkart's own calculator every Rs 10 from 100 to 3,000, each change "
                  "narrowed to the rupee."),
                 ("", "TP TO SP: 'SP by Flipkart' is Flipkart's exact answer; 'SP by formula' the workbook's."),
                 ("", ""), ("Check: formula = Flipkart (within Rs 1)", "")]
        for i, (a, b) in enumerate(lines):
            ws.write(i, 0, a, bold)
            ws.write(i, 1, b)
        r0 = len(lines)
        ws.write_row(r0, 0, ["Brand-Category", "Prices checked", "Equal", "%"], head)
        for i, (k, (cnt, ok)) in enumerate(sorted(checks.items()), start=r0 + 1):
            ws.write_row(i, 0, [k, cnt, ok])
            ws.write_formula(i, 3, f"=IF(B{i + 1}=0,\"\",C{i + 1}/B{i + 1})", pct)
        ws.set_column(0, 0, 34)
        ws.set_column(1, 1, 90)

        # Calculator (single entry)
        ws = wb.add_worksheet("Calculator")
        keys = sorted(pm["Key"].unique()) if len(pm) else []
        ws.write_row(0, 0, ["Brand-Category", "TP (settlement wanted)", "SP for that TP", "",
                            "SP (selling price)", "Settlement (TP) for that SP"], head)
        ws.write(1, 0, keys[0] if keys else "", inp)
        ws.data_validation(1, 0, 30, 0, {"validate": "list", "source": f"=Parameter!$P$2:$P${len(keys) + 1}"})
        ws.write(1, 1, 400, inp)
        ws.write(1, 4, 599, inp)
        for i in range(1, 31):
            if i > 1:
                ws.write_blank(i, 0, None, inp)
                ws.write_blank(i, 1, None, inp)
                ws.write_blank(i, 4, None, inp)
            ws.write_formula(i, 2, f'=IF(OR(A{i + 1}="",B{i + 1}=""),"",IFERROR({price(f"A{i + 1}", f"B{i + 1}")},"not reachable"))')
            ws.write_formula(i, 5, f'=IF(OR(A{i + 1}="",E{i + 1}=""),"",IFERROR({settle(f"A{i + 1}", f"E{i + 1}")},"no slab"))')
        ws.write(32, 0, "Yellow cells are yours: pick the Brand-Category, type a TP or an SP.")
        ws.set_column(0, 0, 30)
        ws.set_column(1, 5, 20)

        # TP TO SP
        tp = pd.DataFrame(tp_rows)
        if len(tp):
            tp.insert(4, "Key", [key_of(b, c) for b, c in zip(tp["Brand"], tp["Category"])])
            tp.to_excel(xw, sheet_name="TP TO SP", index=False)
            ws = xw.sheets["TP TO SP"]
            cols = list(tp.columns)
            c_key, c_tp, c_mrp = (chr(65 + cols.index(c)) for c in ("Key", "Final TP", "MRP"))
            base = len(cols)
            ws.write_row(0, base, ["SP by formula", "Discount % at Flipkart SP", "Remark"], head)
            c_fk = chr(65 + cols.index("SP by Flipkart"))
            for i in range(2, len(tp) + 2):
                ws.write_formula(i - 1, base, f'=IFERROR({price(f"{c_key}{i}", f"{c_tp}{i}")},"")')
                ws.write_formula(i - 1, base + 1, f'=IF(OR({c_fk}{i}="",{c_mrp}{i}=0),"",1-{c_fk}{i}/{c_mrp}{i})', pct)
                ws.write_formula(i - 1, base + 2,
                                 f'=IF({c_fk}{i}="","TP in a fee-slab gap: no exact price",'
                                 f'IF({c_fk}{i}<109,"below Rs 109",IF(1-{c_fk}{i}/{c_mrp}{i}>0.9,"over 90% discount","")))')
            ws.set_column(0, base + 2, 16)
            ws.autofilter(0, 0, len(tp), base + 2)
            ws.freeze_panes(1, 0)

        # SP TO TP
        sp = pd.DataFrame(sp_rows)
        if len(sp):
            sp.insert(4, "Key", [key_of(b, c) for b, c in zip(sp["Brand"], sp["Category"])])
            sp.to_excel(xw, sheet_name="SP TO TP", index=False)
            ws = xw.sheets["SP TO TP"]
            cols = list(sp.columns)
            c_key, c_sp = (chr(65 + cols.index(c)) for c in ("Key", "Current SP"))
            base = len(cols)
            ws.write_row(0, base, ["Settlement by formula", "New SP (type)", "Settlement at new SP"], head)
            for i in range(2, len(sp) + 2):
                ws.write_formula(i - 1, base, f'=IFERROR({settle(f"{c_key}{i}", f"{c_sp}{i}")},"")')
                ws.write_blank(i - 1, base + 1, None, inp)
                nc = chr(65 + base + 1)
                ws.write_formula(i - 1, base + 2, f'=IF({nc}{i}="","",IFERROR({settle(f"{c_key}{i}", f"{nc}{i}")},""))')
            ws.set_column(0, base + 2, 16)
            ws.autofilter(0, 0, len(sp), base + 2)
            ws.freeze_panes(1, 0)

        # Parameter (+ settlement at each slab's bounds, used by TP -> SP)
        pm.to_excel(xw, sheet_name="Parameter", index=False)
        ws = xw.sheets["Parameter"]
        ws.write_row(0, 12, ["TP at SP from", "TP at SP to", "", "Brand-Category list"], head)
        for i in range(2, n + 1):
            to = f"MIN(E{i},{HIGH})"
            ws.write_formula(i - 1, 12, f"=ROUND((D{i}-F{i})-((D{i}-F{i})*G{i}+H{i}+I{i}+J{i})*{1 + GST_ON_FEES}"
                                        f"-(D{i}-F{i})/(1+K{i})*{TCS_TDS},0)", money)
            ws.write_formula(i - 1, 13, f"=ROUND(({to}-F{i})-(({to}-F{i})*G{i}+H{i}+I{i}+J{i})*{1 + GST_ON_FEES}"
                                        f"-({to}-F{i})/(1+K{i})*{TCS_TDS},0)", money)
        for i, k in enumerate(keys, start=1):
            ws.write(i, 15, k)
        ws.set_column(6, 6, 12, pct)
        ws.set_column(10, 10, 12, pct)
        ws.set_column(0, 0, 30)
        ws.set_column(15, 15, 30)
        ws.set_column(11, 11, 22)
        ws.freeze_panes(1, 0)

        pd.DataFrame(rate_cards).to_excel(xw, sheet_name="Rate card", index=False)
    log.info("Written %s", out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py flipkart-calc", description="Flipkart TP / SP calculator workbook")
    p.add_argument("--file", help="the Final TP workbook (default: newest .xlsx in FLIPKART/PRICE UPDATE)")
    p.add_argument("--no-upload", action="store_true", help="keep the workbook in output/, do not put it on Drive")
    p.add_argument("--no-telegram", action="store_true", help="print the report instead of sending it")
    return run_bot("Flipkart calculator", p, run, argv)
