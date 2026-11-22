"""Flipkart Final TP update: every listing's bank settlement (esp) brought to the owner's Final TP.

The target file (AGENT WORK > FLIPKART > PRICE UPDATE, columns "Flipkart Serial Number" and
"Final TP") is matched FSN-wise with Seller Hub's live listing table. A listing whose settlement
is not its Final TP is moved toward it in steps Flipkart accepts:

* up: at most +20% of the current settlement a step, at most 2 increases a day
* down: at most -30% a step (repeated in one run until the TP is reached)
* the selling price for a settlement comes from Flipkart's own calculator (reverse)
* selling price at least Rs 109 in one step: a step that would go below it stops at 109 first
* discount at most 90%: a TP whose price would be under 10% of MRP is not set, and named

What did not reach its TP today (the increase limit, an error) is reached on the next run.
Every step and every refusal is written to an Excel in output/flipkart-price and on Telegram.
`--dry-run` plans the steps without changing a price.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import zlib
from datetime import datetime
from pathlib import Path

import polars as pl

from ..core import telegram
from ..core.app import run_bot
from ..core.config import num, output_dir
from ..portals.flipkart import FlipkartClient
from ..core import clients

log = logging.getLogger("bindal.flipkart_price")

UP, DOWN = 0.20, 0.2968        # Flipkart: +20% / -30% of the current settlement a time; down is
                               # stepped 0.32 points under the limit (owner, 14 Nov 2026)
UP_10 = 0.0968                 # a listing Flipkart holds to "upto 10%": stepped at 9.68% (owner, 14 Nov)
UPS_A_DAY = 2                  # Flipkart: the settlement can be increased 2 times a day
MIN_SP = 109                   # Flipkart: lowest price a step can reach from above
MAX_DISCOUNT = 0.90            # Flipkart: discount up to 90% of MRP
FOLDER = ("FLIPKART", "PRICE UPDATE")
GAP = 15                       # rupees around a settlement tried when it falls in a fee-slab gap
NEAR = 2                       # a TP in a gap: TP +-1, +-2 tried first (owner, 14 Nov)
TWICE = re.compile(r"2 times (a|per) day", re.I)   # "You can increase the bank settlement 2 times per day"
LIMIT_UP = re.compile(r"revise your settlement upto (\d+)%", re.I)
LIMIT_DOWN = re.compile(r"reduce the Bank Settlement Value by a maximum of (\d+)%", re.I)


def read_targets(path: Path) -> dict[str, int]:
    """FSN -> Final TP (whole rupees) from the target workbook; rows without a number are skipped.
    An FSN listed twice with different TPs raises: the owner has to say which one."""
    df = pl.read_excel(path, engine="calamine", schema_overrides={"Flipkart Serial Number": pl.Utf8}, raise_if_empty=False)
    if not {"Flipkart Serial Number", "Final TP"} <= set(df.columns):
        return {}
    tp = pl.col("Final TP").cast(pl.Utf8).str.strip_chars().cast(pl.Float64, strict=False)
    df = (df.select(pl.col("Flipkart Serial Number").str.strip_chars().str.to_uppercase().alias("fsn"),
                    ((tp + 0.5).floor()).cast(pl.Int64).alias("tp"))
            .filter(pl.col("fsn").is_not_null() & pl.col("tp").is_not_null()))
    clash = df.group_by("fsn").agg(pl.col("tp").n_unique()).filter(pl.col("tp") > 1).sort("fsn")["fsn"].to_list()
    if clash:
        raise RuntimeError(f"Final TP file: FSNs with two different TPs: {', '.join(clash[:10])}")
    return dict(df.iter_rows())


def frame(rows: list[dict]) -> pl.DataFrame:
    """Records as a table: every key a column, in the order the keys first appear."""
    return pl.from_dicts(rows, infer_schema_length=None, strict=False) if rows else pl.DataFrame()


def write_run(out: Path, summary: pl.DataFrame, steps: pl.DataFrame, not_live) -> Path:
    """The run's workbook: Listings, Steps, Not live (core/xlsx.write_sheets)."""
    from ..core.xlsx import write_sheets
    return write_sheets(out, [("Listings", summary.columns, summary.iter_rows()), ("Steps", steps.columns, steps.iter_rows()),
                              ("Not live", ["FSN not live on Flipkart"], [[f] for f in not_live])], bold_header=True)


def read_run(path: Path) -> tuple[pl.DataFrame, pl.DataFrame, list[str]]:
    """A part's workbook back: (Listings, Steps, the FSNs not live)."""
    book = pl.read_excel(path, sheet_name=["Listings", "Steps", "Not live"], engine="calamine", raise_if_empty=False)
    live = book["Not live"]
    gone = live[live.columns[0]].drop_nulls().cast(pl.Utf8).to_list() if live.width else []
    return book["Listings"], book["Steps"], gone


def why(status: pl.Expr) -> pl.Expr:
    """Why a listing is still not at its TP, in words."""
    s, low = status.cast(pl.Utf8).fill_null("None"), status.cast(pl.Utf8).fill_null("None").str.to_lowercase()
    return (pl.when(low.str.contains("increase", literal=True) & (s.str.contains("2 times", literal=True) | s.str.contains("today", literal=True)))
              .then(pl.lit("2 increases done today: continues next run"))
              .when(s.str.contains("fee slab gap", literal=True)).then(pl.lit("TP falls in a fee-slab gap (no exact price)"))
              .when(s.str.contains("discount", literal=True)).then(pl.lit("TP too low for the MRP (over 90% discount)"))
              .when(s.str.contains("dry run", literal=True)).then(pl.lit("dry run"))
              .otherwise(s.str.replace_all("refused: ", "Flipkart refused: ", literal=True).str.slice(0, 80)))


def next_settlement(current: int, target: int, up: float = UP, down: float = DOWN) -> int:
    """The settlement of the next step from current toward target, inside Flipkart's limits."""
    if target > current:
        return min(target, math.floor(current * (1 + up)))
    return max(target, math.ceil(current * (1 - down)))


def limit_in(why: str) -> tuple[str, float] | None:
    """("up" | "down", fraction) when Flipkart refused a step for its size: the limit differs by
    listing (14 Nov: "upto 10% of current value" on one, 20% on others)."""
    m = LIMIT_UP.search(why)
    if m:
        return "up", int(m.group(1)) / 100
    m = LIMIT_DOWN.search(why)
    return ("down", int(m.group(1)) / 100) if m else None


def gap_tries(current: int, nxt: int, target: int, up: float = UP, down: float = DOWN) -> list[int]:
    """Settlements to try, nearest first, when nxt has no price (a fee-slab gap): inside Flipkart's
    step limits from current and not the current settlement itself. On the last step (nxt is the
    TP) the TP +-1, +-2 come first, below the TP too (owner, 14 Nov: "TP must match, try Rs 1-2
    either side"); then the nearest above the TP. Never more than NEAR below the TP."""
    hi = math.floor(current * (1 + up)) if target > current else current - 1
    lo_step = current + 1 if target > current else math.ceil(current * (1 - down))
    out = []
    if nxt == target:
        for k in range(1, NEAR + 1):
            out += [v for v in (target + k, target - k) if max(lo_step, target - NEAR) <= v <= hi]
    lo = max(target, lo_step)
    for k in range(1, GAP + 1):
        out += [v for v in (nxt + k, nxt - k) if lo <= v <= hi and v not in out]
    return out


def forward_search(client: FlipkartClient, tier: str, items: list[dict]) -> dict[int, dict[int, int]]:
    """{id(item): {SP: settlement}} around the price whose settlement (Flipkart's forward calculator)
    crosses the item's "next" settlement: halving between Rs 109 and the MRP, then the prices on
    both sides of the crossing. All items go in the same calls (one price per listing a call)."""
    if not items:
        return {}
    lo = {id(it): MIN_SP for it in items}
    hi = {id(it): max(MIN_SP + 1, int(it["mrp"])) for it in items}
    seen: dict[int, dict[int, int]] = {id(it): {} for it in items}

    def price(todo: list[tuple[dict, int]]) -> None:
        todo = [(it, sp) for it, sp in todo if sp not in seen[id(it)]]
        if todo:
            ans = client.calculator([{"listing_id": it["listing_id"], "selling_price": sp} for it, sp in todo], tier)
            for it, sp in todo:
                sv = (ans.get(it["listing_id"]) or {}).get("settlement_value")
                if sv is not None:
                    seen[id(it)][sp] = int(sv)

    for _ in range(14):
        live = [it for it in items if hi[id(it)] - lo[id(it)] > 1]
        if not live:
            break
        price([(it, (lo[id(it)] + hi[id(it)]) // 2) for it in live])
        for it in live:
            m = (lo[id(it)] + hi[id(it)]) // 2
            sv = seen[id(it)].get(m)
            if sv is None:
                hi[id(it)] = lo[id(it)]          # no answer: give up on this one
            elif sv < it["next"]:
                lo[id(it)] = m
            else:
                hi[id(it)] = m
    price([(it, sp) for it in items for sp in range(lo[id(it)] - 2, hi[id(it)] + 3) if sp >= MIN_SP])
    return seen


def pick(it: dict, prices: dict[int, int]) -> tuple[int, int] | None:
    """(SP, settlement) from the forward search: on the last step the settlement nearest the TP
    within NEAR rupees (exact first, then above); on a middle step the one nearest the step's
    target inside Flipkart's step limits."""
    hi = math.floor(it["esp"] * (1 + it["up"])) if it["tp"] > it["esp"] else it["esp"] - 1
    lo = it["esp"] + 1 if it["tp"] > it["esp"] else math.ceil(it["esp"] * (1 - it["down"]))
    if it["next"] == it["tp"]:
        ok = [(sp, sv) for sp, sv in prices.items() if abs(sv - it["tp"]) <= NEAR and (lo <= sv <= hi)]
    else:
        ok = [(sp, sv) for sp, sv in prices.items() if lo <= sv <= hi]
    if not ok:
        return None
    return min(ok, key=lambda c: (abs(c[1] - it["next"]), c[1] < it["next"], c[0]))


def increases_today(client: FlipkartClient, listing_id: str) -> int:
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
    n = 0
    for h in client.price_history(listing_id, "esp"):
        try:
            if h["timestamp"] >= start and float(h["new_value"]) > float(h["old_value"]):
                n += 1
        except (KeyError, TypeError, ValueError):
            continue
    return n


def plan_step(client: FlipkartClient, tier: str, items: list[dict]) -> None:
    """Give each item (listing + current esp/ssp + target) its next step: esp, sp, or a stop reason."""
    rev = client.calculator([{"listing_id": it["listing_id"], "type": "reverse", "settlement_value": it["next"]}
                             for it in items], tier)
    # a TP inside a fee-slab gap has no price (DELTA_IN_SETTLEMENT_VALUE, price 0), and Flipkart's
    # reverse calculator also fails next to the slab edge: search by price with the forward
    # calculator: the last step takes the settlement nearest the TP within NEAR rupees (owner, 14 Nov:
    # "TP must match, try Rs 1-2 either side"), a middle step the nearest inside the step limits
    missing = [it for it in items if not (rev.get(it["listing_id"]) or {}).get("selling_price")]
    found = forward_search(client, tier, missing)
    for it in missing:
        got = pick(it, found.get(id(it)) or {})
        if got:
            sp, sv = got
            rev[it["listing_id"]] = {"selling_price": sp, "settlement_status": None}
            if sv != it["next"]:
                it["gap_note"] = (f"settlement {it['next']} not reachable (fee slab gap): {sv} set"
                                  + (f" (Rs {sv - it['tp']:+d} from TP)" if it["next"] == it["tp"] else ""))
            it["next"] = sv
    # otherwise the nearest one that stays inside the step limits (intermediate steps, and a TP
    # with nothing within NEAR rupees: the nearest above it)
    for it in items:
        it["tries"] = gap_tries(it["esp"], it["next"], it["tp"], it["up"], it["down"])
    for k in range(2 * GAP):
        gap = [it for it in items if not (rev.get(it["listing_id"]) or {}).get("selling_price") and k < len(it["tries"])]
        if not gap:
            break
        more = client.calculator([{"listing_id": it["listing_id"], "type": "reverse",
                                   "settlement_value": it["tries"][k]} for it in gap], tier)
        for it in gap:
            ans = more.get(it["listing_id"]) or {}
            if ans.get("selling_price"):
                rev[it["listing_id"]] = ans
                it["gap_note"] = f"settlement {it['next']} not reachable (fee slab gap): {it['tries'][k]} set"
                it["next"] = it["tries"][k]
    floor_fwd = []
    for it in items:
        ans = rev.get(it["listing_id"]) or {}
        sp = ans.get("selling_price")
        if not sp:
            d = it["esp"] - it["tp"]
            it["stop"] = (f"at {it['esp']}, Rs {d:+d} from TP {it['tp']}: no closer settlement exists (fee slab gap)"
                          if abs(d) <= NEAR else f"no price for settlement {it['next']} or near it (fee slab gap)")
            continue
        it["sp"], it["new_esp"] = int(sp), it["next"]
        if ans.get("settlement_status") not in (None, "SETTLEMENT_VALUE_ACHIEVED"):
            it["stop"] = f"calculator: {ans.get('settlement_status')} for settlement {it['next']}"
            continue
        if it["sp"] < MIN_SP < it["ssp"]:
            it["sp"] = MIN_SP              # stop at 109 first; the next step goes lower
            floor_fwd.append(it)
        min_sp = math.ceil(it["mrp"] * (1 - MAX_DISCOUNT))
        if it["sp"] < min_sp:
            it["stop"] = f"price {it['sp']} under 10% of MRP {it['mrp']:.0f} (90% discount limit): TP too low for this MRP"
    if floor_fwd:
        fwd = client.calculator([{"listing_id": it["listing_id"], "selling_price": MIN_SP} for it in floor_fwd], tier)
        for it in floor_fwd:
            sv = (fwd.get(it["listing_id"]) or {}).get("settlement_value")
            if sv is None:
                it["stop"] = f"calculator gave no settlement at Rs {MIN_SP}"
            else:
                it["new_esp"] = int(sv)


def run(args) -> int:
    if args.merge:
        return merge(Path(args.merge), args)
    started = datetime.now()
    path = Path(args.file) if args.file else fetch_target_file()
    targets = read_targets(path)
    log.info("Final TP file %s: %d FSNs", path.name, len(targets))

    client = clients.flipkart()
    tier, user = client.tier(), client.seller_name()
    listings = client.listings("ACTIVE")
    by_fsn: dict[str, list[dict]] = {}
    for x in listings:
        by_fsn.setdefault(str(x.get("product_id") or "").upper(), []).append(x)

    log_rows, todo, matched, not_live = [], [], 0, []
    for fsn, tp in targets.items():
        rows = by_fsn.get(fsn)
        if not rows:
            not_live.append(fsn)
            continue
        for x in rows:
            esp, ssp, mrp = x.get("esp"), x.get("ssp"), x.get("mrp")
            if esp is None or ssp is None or not mrp:
                log_rows.append({"FSN": fsn, "SKU": x.get("sku_id"), "Final TP": tp, "Result": "no price on Flipkart"})
                continue
            if int(esp) == tp:
                matched += 1
                continue
            todo.append({"fsn": fsn, "sku": x["sku_id"], "listing_id": x["listing_id"], "vertical": x.get("vertical"),
                         "mrp": float(mrp), "esp": int(esp), "ssp": int(ssp), "start_esp": int(esp),
                         "start_ssp": int(ssp), "tp": tp, "ups": 0, "steps": 0, "up": UP, "down": DOWN})
    log.info("Listings at TP: %d, to change: %d, FSNs not live: %d", matched, len(todo), len(not_live))
    part, parts = args.part
    if parts > 1:                    # GitHub matrix: this job takes its share of the listings only
        todo = [it for it in todo if zlib.crc32(it["listing_id"].encode()) % parts == part - 1]
        log.info("Part %d of %d: %d listings to change", part, parts, len(todo))
    if args.limit:
        todo = todo[:args.limit]
    # today's increases made by hand or an earlier run: Flipkart refuses a 3rd one ("2 times a day"),
    # which stops that listing for today (reading every listing's history first took too long)

    max_steps = num("FK_PRICE_MAX_STEPS", 6)
    active = [it for it in todo if "done" not in it]
    for _ in range(max_steps):
        step = []
        for it in active:
            if it["esp"] == it["tp"]:
                it["done"] = "at TP"
            elif it["tp"] > it["esp"] and it["ups"] >= UPS_A_DAY:
                it["done"] = "2 increases made today: rest on the next run"
            else:
                it["next"] = next_settlement(it["esp"], it["tp"], it["up"], it["down"])
                it.pop("stop", None)
                step.append(it)
        if not step:
            break
        plan_step(client, tier, step)
        for it in step:
            row = {"FSN": it["fsn"], "SKU": it["sku"], "Vertical": it["vertical"], "MRP": it["mrp"],
                   "Final TP": it["tp"], "Settlement before": it["esp"], "Price before": it["ssp"],
                   "Settlement set": None, "Price set": None}
            if "stop" in it:
                it["done"] = it["stop"]
                log_rows.append({**row, "Result": it["stop"]})
                continue
            new_esp, new_sp = it["new_esp"], it["sp"]
            if new_esp == it["esp"]:
                it["done"] = it.get("gap_note") or "nearest reachable settlement already set"
                log_rows.append({**row, "Result": f"no change: {it['done']}"})
                continue
            row.update({"Settlement set": new_esp, "Price set": new_sp})
            if it.get("gap_note"):
                row["Note"] = it["gap_note"]
            if args.dry_run:
                log_rows.append({**row, "Result": "planned (dry run)"})
                it["done"] = "dry run"
                continue
            try:
                ans = client.update_settlement(it["sku"], it["fsn"], it["mrp"], new_sp, new_esp, user)
            except Exception as exc:  # noqa: BLE001 - one listing failing must not stop the rest
                ans = {"status": "FAILURE", "errors": [{"description": str(exc)[:200]}]}
            if ans.get("status") == "SUCCESS":
                if new_esp > it["esp"]:
                    it["ups"] += 1
                it["esp"], it["ssp"] = new_esp, new_sp
                it["steps"] += 1
                log_rows.append({**row, "Result": "updated"})
            else:
                why = " | ".join(e.get("description", "") for e in ans.get("errors") or []) or str(ans)[:200]
                lim = limit_in(why)
                if lim and lim[0] == "up" and abs(lim[1] - 0.10) < 1e-9:
                    lim = ("up", UP_10)      # 10% listings: 9.68% a step (owner)
                elif lim and lim[0] == "down":
                    lim = ("down", lim[1] - 0.0032)
                if lim and len(ans.get("errors") or []) == 1 and lim[1] < it[lim[0]]:
                    it[lim[0]] = lim[1]      # this listing's own limit: the next round steps inside it
                    log_rows.append({**row, "Result": f"refused, retried at {lim[1]:.2%}: {why}"})
                    continue
                if TWICE.search(why):
                    it["ups"] = UPS_A_DAY
                it["done"] = f"refused: {why}"
                log_rows.append({**row, "Result": f"refused: {why}"})
        active = [it for it in active if "done" not in it]
        if args.dry_run:
            break

    reached = sum(1 for it in todo if it["esp"] == it["tp"])
    moved = sum(1 for it in todo if it["steps"] and it["esp"] != it["tp"])
    left = [it for it in todo if it["esp"] != it["tp"]]
    summary = frame([{"FSN": it["fsn"], "SKU": it["sku"], "Vertical": it["vertical"], "MRP": it["mrp"],
                      "Final TP": it["tp"], "Settlement start": it["start_esp"], "Price start": it["start_ssp"],
                      "Settlement now": it["esp"], "Price now": it["ssp"], "Steps": it["steps"],
                      "Status": "at TP" if it["esp"] == it["tp"] else it.get("done", "not reached")}
                     for it in todo])
    tag = f" part {part} of {parts}" if parts > 1 else ""
    out = output_dir("flipkart-price") / f"Flipkart Final TP update {started:%Y-%m-%d %H%M}{tag}.xlsx"
    write_run(out, summary, frame(log_rows), not_live)
    meta = {"started": f"{started:%Y-%m-%d %H:%M}", "file": path.name, "fsns": len(targets), "matched": matched,
            "todo": len(todo), "reached": reached, "moved": moved, "dry_run": bool(args.dry_run), "part": part, "parts": parts}
    out.with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")
    log.info("Written %s", out)
    if parts > 1:                    # the report job (--merge) joins the parts and sends one message
        log.info("Part %d of %d done: %d at TP, %d moved, %d left", part, parts, reached, moved, len(left))
        return 0
    return report([meta], summary, frame(log_rows), not_live, out, args)


def report(metas: list[dict], summary: pl.DataFrame, steps: pl.DataFrame, not_live: list[str],
           out: Path, args) -> int:
    m0 = metas[0]
    dry = m0["dry_run"]
    todo = sum(m["todo"] for m in metas)
    reached = sum(m["reached"] for m in metas)
    if not summary.height:
        summary = pl.DataFrame(schema={"Steps": pl.Int64, "Status": pl.Utf8})
    changed = int((summary["Steps"].fill_null(0) > 0).sum())
    left = summary.filter(pl.col("Status").ne_missing("at TP"))
    untouched = left.filter(pl.col("Steps").fill_null(0) == 0)

    pending_why = (left.group_by(why(pl.col("Status")).alias("why"), maintain_order=True).len()
                       .sort("len", descending=True, maintain_order=True).rows())
    parts = f" · {len(metas)} of {m0['parts']} parts" if m0["parts"] > 1 else ""
    when = f"{m0['started'][8:10]}/{m0['started'][5:7]} {m0['started'][11:]}"
    msg = [f"💸 <b>Flipkart Final TP update · {when}</b>" + (" (dry run: nothing changed)" if dry else ""),
           f"<i>{telegram.esc(m0['file'])}{parts}</i>", "",
           f"✅ <b>At Final TP: {m0['matched'] + reached:,}</b> (today: {reached:,})",
           f"🔄 <b>Price updated today: {changed:,}</b>" if not dry else f"📝 <b>To change: {todo:,}</b>",
           f"⏳ <b>Still pending: {len(left):,}</b>"
           + ("" if dry else f" ({len(left) - len(untouched):,} moved closer, {len(untouched):,} not changed)"),
           *[f"   • {telegram.esc(r)}: {n:,}" for r, n in pending_why[:6]],
           f"❔ Not live on Flipkart: {len(not_live):,}"]
    if m0["parts"] > 1 and len(metas) < m0["parts"]:
        msg += ["", f"⚠️ Only {len(metas)} of {m0['parts']} parts finished: the others are left out (named in the run)"]
    # the master sheet (owner, 14 Nov): FSN | SKU | Final TP | per day Old TP / New TP; it is the file
    # sent on Telegram. A dry run or --no-upload leaves it alone and sends the run's own Excel.
    send = out
    if not dry and not getattr(args, "no_upload", False) and summary.height:
        try:
            from . import master
            day = datetime.strptime(m0["started"][:10], "%Y-%m-%d").date()
            rows = [{"fsn": r["FSN"], "sku": r["SKU"], "tp": int(r["Final TP"]),
                     "old": int(r["Settlement start"]), "new": int(r["Settlement now"])}
                    for r in summary.iter_rows(named=True)]
            send, link = master.sync(day, rows, out.parent)
            msg.append(f'📒 <a href="{link}">TP update master</a>')
        except Exception as exc:  # noqa: BLE001 - the update itself is done; name the miss
            log.warning("TP update master not updated: %s", exc)
            msg.append(f"⚠️ TP update master not updated ({telegram.esc(str(exc)[:80])})")
    text = "\n".join(m for m in msg if m or m == msg[2])
    if args.no_telegram:
        print(text)
    else:
        telegram.send(text)
        telegram.send_document(send, caption="Flipkart TP update master" if send != out else "Flipkart Final TP update")
    return 0


def merge(folder: Path, args) -> int:
    """The report job of the GitHub matrix: join the parts' files found under folder."""
    metas, sums, steps, not_live = [], [], [], set()
    for js in sorted(folder.rglob("Flipkart Final TP update *part*.json")):
        meta = json.loads(js.read_text(encoding="utf-8"))
        xl = js.with_suffix(".xlsx")
        if not xl.exists():
            continue
        metas.append(meta)
        listings, done, gone = read_run(xl)
        sums.append(listings)
        steps.append(done)
        not_live |= set(gone)
    if not metas:
        raise RuntimeError(f"No part results under {folder}: every part of the matrix failed")
    out = output_dir("flipkart-price") / f"Flipkart Final TP update {metas[0]['started'].replace(':', '')}.xlsx"
    summary = pl.concat([x for x in sums if x.width], how="diagonal_relaxed") if any(x.width for x in sums) else pl.DataFrame()
    step_df = pl.concat([x for x in steps if x.width], how="diagonal_relaxed") if any(x.width for x in steps) else pl.DataFrame()
    write_run(out, summary, step_df, sorted(not_live))
    return report(metas, summary, step_df, sorted(not_live), out, args)


def fetch_target_file() -> Path:
    """The newest .xlsx in AGENT WORK > FLIPKART > PRICE UPDATE, downloaded to output/."""
    from ..core.drive import agent_folder
    folder = agent_folder()
    for name in FOLDER:
        folder = folder.subfolder(name)
        if folder is None:
            raise RuntimeError(f"Drive folder AGENT WORK/{'/'.join(FOLDER)} not found")
    files = [(n, m) for n, m in folder.children().items() if n.lower().endswith(".xlsx")]
    if not files:
        raise RuntimeError("No .xlsx Final TP file in AGENT WORK/FLIPKART/PRICE UPDATE")
    name = max(files, key=lambda f: f[1].get("modifiedTime", ""))[0]
    return folder.download(name, output_dir("flipkart-price") / name)


def part_of(text: str) -> tuple[int, int]:
    i, n = (int(v) for v in text.split("/"))
    if not 1 <= i <= n:
        raise argparse.ArgumentTypeError(f"part {text}: I must be 1..N")
    return i, n


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="run.py flipkart-price", description="Flipkart settlement to Final TP")
    p.add_argument("--file", help="the Final TP workbook (default: newest .xlsx in the Drive folder)")
    p.add_argument("--dry-run", action="store_true", help="plan the steps, change no price")
    p.add_argument("--limit", type=int, default=0, help="only the first N listings to change (a test)")
    p.add_argument("--part", type=part_of, default=(1, 1), metavar="I/N",
                   help="GitHub matrix: change only part I of N of the listings (no summary message)")
    p.add_argument("--no-upload", action="store_true", help="leave the TP update master on Drive alone")
    p.add_argument("--merge", metavar="DIR", help="report job: join the parts' results under DIR, send one message")
    p.add_argument("--no-telegram", action="store_true", help="print the report instead of sending it")
    return run_bot("Flipkart Final TP update", p, run, argv)
