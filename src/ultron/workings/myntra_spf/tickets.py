"""Myntra SPF claims raised by the bot, on the policy's timelines (SPF POLICY v5, Annexure 1).

Two kinds, both raised the way the portal's bulk upload does it (Support > Seller Protection
Fund > Create New Claim > "Here"): an xlsx of order line ids per issue category.

  Return Not Received  (RTS_ORDER_WAS_NEVER_DELIVERED)
      Myntra shows the return delivered to us, but it never reached the warehouse. Policy:
      within 7 days of the delivery date. Raised from day MYNTRA_SPF_RNR_AFTER_DAYS (4) after
      delivery, so the GRN / OMSGuru have had time to book a return that did arrive.
  Return Not Received, in transit  (RTS_ORDER_WAS_NEVER_DELIVERED, description "Return Pending")
      Still in transit, or no return tracking at all, 61 (MYNTRA_SPF_DELAY_AFTER_DAYS) to 120 days
      from the return / RTO creation date. Until 30 Oct 2026 these went in as Delayed Returns
      (DELAYED_DELIVERED_RETURN): Myntra rejected all 906 of those ("Not_eligible_tat_less_than_120_days",
      whatever the age), while 83 in-transit returns claimed as Return Not Received at 61-113
      days were paid or accepted. One claim per order line, so a rejected one is lost for good.
      MYNTRA_SPF_TRANSIT_CATEGORY=DELAYED brings the old category back.

SJIT / FBM returns (owner, 25 Nov 2026; Myntra's new SJIT SPF tool, tickets through the old ticketing portal
not considered after 30 Nov 2026): claimed per item (Fact Core Item ID = the SJIT returns report's core_item_id)
with the SJIT bulk upload (Create New Claim > SJIT > "Here"), see sjit_candidates / raise_sjit_claims.

A row is claimed only when nothing says it is settled: no ticket on it (master TICKET ID or
any ticket on the portal for that order line, any status - the policy allows one claim per
order and treats repeat tickets as fraud), FINAL RETURN STATUS blank (not received in the ERP /
OMSGuru / manual sheet, no SPF payout, no clean settlement), not an SJIT / FBM order, and no
RETURN POD from the courier (a signed return handover).

Every ticket on the portal is also written into the work folder as a ticket report, so the
master's TICKET ID / STATUS columns follow the portal. A claim just raised gets
TICKET ID "BOT JOB <job id>" until its real ticket turns up on the next run.
"""
from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..core.config import env, num

log = logging.getLogger(__name__)

RNR = "RTS_ORDER_WAS_NEVER_DELIVERED"
DELAYED = "DELAYED_DELIVERED_RETURN"
TRANSIT = "RNR_TRANSIT"        # ours only: claimed on Myntra as RNR, with its own description
ISSUE = {TRANSIT: RNR}
CATEGORY_NAME = {RNR: "Return Not Received", DELAYED: "Delayed Returns", TRANSIT: "Return Not Received (in transit)"}
# The SJIT tool's bulk categories (its Issue Category list, 25 Nov 2026)
SJIT_INWARD = "INWARD_REJECTIONS_DELAY_IN_RETURNS"
SJIT_SHORT = "SHORTAGE_IN_RSTN"
SJIT_NOT_SETTLED = "STN_GRN_AT_WAREHOUSE_NOT_SETTLED_NOR_RETURNED"
CATEGORY_NAME.update({SJIT_INWARD: "Inward Rejections - Delay in Returns", SJIT_SHORT: "Shortage in RSTN",
                      SJIT_NOT_SETTLED: "STN GRN'd at the Warehouse but not settled nor returned"})
SJIT_DESCRIPTION = ("Return Pending: customer return / RTO not received back at the Myntra warehouse, "
                    "item neither settled (paid) nor returned to us")
DESCRIPTION = {
    RNR: "RETURN DELIVERED BUT PHYSICAL RETURN PARCEL NOT RECEIVED YET",
    DELAYED: "RETURN SHOWING IN TRANSIT, KINDLY CHECK AND RETURN THE PARCEL ASAP",
    TRANSIT: "Return Pending",       # the wording of the in-transit claims Myntra paid
}
# The ticket report the engine reads (kind TICKET: ticketId + orderLineId columns)
TICKET_FILE = "SPF Tickets (portal).xlsx"
BOT_FILE = "SPF Tickets (raised by bot).xlsx"
TICKET_HEADER = ["ticketId", "orderLineId", "returnId", "issueCategory", "status", "createdOn", "validationReason"]
# Tickets the bot just raised whose real ticket turned up in the same run (see resolve_raised)
NEW_FILE = "SPF Tickets (new).xlsx"

# The master's TICKETS sheet: every claim of the last MYNTRA_SPF_DETAIL_DAYS (120) days and any older
# one still open, as its portal page shows it, with Seller Support's replies.
DETAIL_SHEET = "TICKETS"
DETAIL_COLS = ["ACCOUNT", "TICKET ID", "ORDER LINE ID", "RETURN ID", "ORDER ID", "CATEGORY", "STATUS",
               "NEEDS OUR REPLY", "CREATED", "LAST UPDATED", "STATUS HISTORY", "REASON", "COMPENSATION",
               "UTR", "PAYMENT INITIATED", "DESCRIPTION", "SUPPORT TICKET", "REPLIES", "LAST REPLY BY",
               "LAST REPLY AT", "LAST REPLY"]
FINAL_STATUSES = {"REJECT", "PAYMENT_COMPLETED", "CLOSED"}
AWAITING_US = "AWAITING_SELLER_RESPONSE"
IST = timedelta(hours=5, minutes=30)


def _day(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def _blank(v) -> bool:
    return v is None or str(v).strip() == ""


def claim_of(r: dict, today: date, ticketed: set[str]) -> str | None:
    """The category to claim this master row under today, or None."""
    from .pipeline import not_worked, resolved
    from .engine import norm, is_delivered_status
    oli = norm(r.get("order_line_id"))
    if not oli or oli in ticketed or not _blank(r.get("TICKET ID")):
        return None
    if not_worked(r) or resolved(r):           # Payment Received is still claimed
        return None
    if str(r.get("RETURN POD") or "").strip().upper() == "YES":
        return None
    delivered = _day(r.get("deliver_to_seller_date"))
    if delivered or is_delivered_status(r.get("status")):
        if not delivered:
            return None                          # delivered without a date: the TAT cannot be told
        age = (today - delivered).days
        lo, hi = num("MYNTRA_SPF_RNR_AFTER_DAYS", 4), num("MYNTRA_SPF_RNR_MAX_DAYS", 7)
        return RNR if lo <= age <= hi else None
    created = _day(r.get("return_created_date"))
    if not created:
        return None
    age = (today - created).days
    lo, hi = num("MYNTRA_SPF_DELAY_AFTER_DAYS", 61), num("MYNTRA_SPF_DELAY_MAX_DAYS", 120)
    if not lo <= age <= hi:
        return None
    return DELAYED if str(env("MYNTRA_SPF_TRANSIT_CATEGORY", "")).upper() == "DELAYED" else TRANSIT


def candidates(path: Path, today: date, ticketed: dict[str, set[str]], skip: set[tuple] = frozenset(),
               blocked: dict[str, set[str]] | None = None) -> dict[str, dict[str, list[str]]]:
    """account -> category -> order line ids to claim, from the master's account sheets.
    ticketed: account -> order lines with a portal ticket. skip: (order_line_id, return_id)
    keys known to be received (OMSGuru) since the master was written. blocked (filled when
    given): account -> order lines that already have a ticket, are received / settled or have a
    courier POD, which an SJIT claim leaves alone too."""
    from openpyxl import load_workbook
    from .engine import SHEETS, master_rows, norm
    wb = load_workbook(path, read_only=True)
    out: dict[str, dict[str, list[str]]] = {}
    for name in SHEETS:          # the account sheet and its rows on the RETURN IN TRANSIT sheet
        seen: set[str] = set()
        for r in master_rows(wb, name):
            key = (norm(r.get("order_line_id")), norm(r.get("return_id")))
            if blocked is not None and (key in skip or not _blank(r.get("TICKET ID")) or _settled(r)):
                blocked.setdefault(name, set()).add(key[0])
            if key in skip:
                continue
            cat = claim_of(r, today, ticketed.get(name, set()))
            oli = norm(r.get("order_line_id"))
            if cat and oli not in seen:
                seen.add(oli)
                out.setdefault(name, {}).setdefault(cat, []).append(oli)
    wb.close()
    return out


def _settled(r: dict) -> bool:
    """Received / settled on the master, or the courier's POD says it was handed back."""
    from .pipeline import resolved
    return resolved(r) or str(r.get("RETURN POD") or "").strip().upper() == "YES"


# ------------------------------------------------------------------ SJIT / FBM claims (new SJIT tool)

def _sjit_created(r: dict) -> date | None:
    """A return's creation day, an RTO's RTO day (an RTO's return_created_date is 1970-01-01)."""
    cols = ("order_rto_date", "return_created_date") if str(r.get("type")).upper() == "RTO" \
        else ("return_created_date", "order_rto_date")
    for col in cols:
        try:
            d = date.fromisoformat(str(r.get(col) or "")[:10])
        except ValueError:
            continue
        if d.year > 2000:
            return d
    return None


def sjit_returns(folder: Path) -> list[dict]:
    """The SJIT_Customer_Returns_Report rows in folder that carry a core_item_id (its PPMP lines have none),
    one per item: core_item_id, order_line_id, type, created (return / RTO day), status."""
    import io
    import zipfile
    import polars as pl
    out: dict[str, dict] = {}
    for f in sorted(folder.glob("*")) if folder.exists() else []:
        data = f.read_bytes()
        if data[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(data))
            data = z.read(z.namelist()[0])
        df = pl.read_csv(data, infer_schema=False)
        if "core_item_id" not in df.columns:
            continue
        for r in df.filter(pl.col("core_item_id").str.strip_chars().fill_null("") != "").iter_rows(named=True):
            core = str(r["core_item_id"]).strip()
            out[core] = {"core_item_id": core, "order_line_id": str(r.get("order_line_id") or "").strip(),
                         "type": r.get("type"), "created": _sjit_created(r), "status": r.get("status")}
    return list(out.values())


# Why an SJIT / FBM item is not claimed (the SJIT master's BOT RESULT); "" = a candidate
SJIT_CLAIMED = "CLAIM ON IT"
SJIT_SETTLED = "TICKETED / SETTLED ON THE MASTER"
SJIT_NO_DATE = "NO RETURN DATE"
SJIT_YOUNG = "TOO YOUNG"
SJIT_OLD = "TOO OLD"
SJIT_BACK = "BACK IN MYNTRA STOCK"
SJIT_RAISED = "RAISED"
SJIT_DUE = "DUE (claims off)"
SJIT_FAILED = "NOT CHECKED (lookup failed)"
SJIT_CAPPED = "NOT CHECKED (next run)"
SJIT_NOT_RAISED = "DUE, RAISE FAILED"


def sjit_window() -> tuple[int, int]:
    """(first, last) age in days of an SJIT in-transit claim: MYNTRA_SPF_SJIT_AFTER_DAYS / _MAX_DAYS, else the
    PPMP in-transit claims' 61 / 120."""
    return (num("MYNTRA_SPF_SJIT_AFTER_DAYS", num("MYNTRA_SPF_DELAY_AFTER_DAYS", 61)),
            num("MYNTRA_SPF_SJIT_MAX_DAYS", num("MYNTRA_SPF_DELAY_MAX_DAYS", 120)))


def sjit_reason(r: dict, today: date, ticketed: set[str], blocked: set[str]) -> str:
    """Why the item is not a candidate today, or "": an SJIT claim on the item (ticketed: core ids and order
    lines), its order line ticketed / received / settled / POD'd on the master (blocked), or its age outside
    sjit_window()."""
    oli = r["order_line_id"]
    if r["core_item_id"] in ticketed or (oli and oli in ticketed):
        return SJIT_CLAIMED
    if oli and oli in blocked:
        return SJIT_SETTLED
    if not r["created"]:
        return SJIT_NO_DATE
    lo, hi = sjit_window()
    age = (today - r["created"]).days
    return SJIT_YOUNG if age < lo else SJIT_OLD if age > hi else ""


def sjit_candidates(rows: list[dict], today: date, ticketed: set[str], blocked: set[str]) -> list[dict]:
    """The SJIT / FBM returns to claim as in transit today (sjit_reason ""). Whether the item is still out of
    Myntra's warehouse is asked live (raise_sjit_claims)."""
    return [r for r in rows if not sjit_reason(r, today, ticketed, blocked)]


def sjit_category() -> str:
    """MYNTRA_SPF_SJIT_CATEGORY (one of the tool's three), else not settled nor returned."""
    cat = str(env("MYNTRA_SPF_SJIT_CATEGORY", "") or SJIT_NOT_SETTLED).strip().upper()
    return cat if cat in (SJIT_INWARD, SJIT_SHORT, SJIT_NOT_SETTLED) else SJIT_NOT_SETTLED


def raise_sjit_claims(portal, account: str, rows: list[dict], live: bool,
                      results: dict[str, dict] | None = None) -> list[str]:
    """Each candidate item is looked up on the SJIT tool first (spf_sjit_item): claimed only while it is still
    SHIPPED (out of Myntra's warehouse: the return never came back) with no claim on it. Raised live in bulk
    jobs of SPF_BULK_MAX (model SJIT, FactCoreId file), or only counted. Lines for the report; results (when
    given): core id -> {result, stock (itemStatus), checked, job} for the SJIT master."""
    from ..portals.myntra import SPF_BULK_MAX
    cap = num("MYNTRA_SPF_SJIT_CHECK_MAX", 1000)
    todo, rest = rows[:cap], max(0, len(rows) - cap)
    failed: list[str] = []
    res = results if results is not None else {}
    stamp = f"{datetime.now():%d-%b-%Y %H:%M}"
    for r in rows[cap:]:
        res[r["core_item_id"]] = {"result": SJIT_CAPPED}

    def check(r):
        core = r["core_item_id"]
        try:
            item = portal.spf_sjit_item(core)
        except Exception as exc:  # noqa: BLE001 - not claimed on a guess
            failed.append(str(exc)[:60])
            res[core] = {"result": SJIT_FAILED, "checked": stamp}
            return None
        stock = str(item.get("itemStatus") or "").upper()
        res[core] = {"stock": stock or "UNKNOWN TO THE TOOL", "checked": stamp}
        if stock != "SHIPPED":
            res[core]["result"] = SJIT_BACK              # back in stock, or unknown to the tool
            return None
        if not (_blank(item.get("ticketId")) and _blank(item.get("issueCategory"))):
            res[core]["result"] = SJIT_CLAIMED           # a claim is already on the item
            return None
        res[core]["result"] = SJIT_DUE
        return core

    with ThreadPoolExecutor(max_workers=num("MYNTRA_SPF_SJIT_WORKERS", 4)) as pool:
        due = [c for c in pool.map(check, todo) if c]
    cat = sjit_category()
    name = f"{account} SJIT/FBM {CATEGORY_NAME[cat]}"
    more = (f", {rest} left for the next run" if rest else "") + (f", {len(failed)} not checked" if failed else "")
    if not due:
        return [f"{name}: none due of {len(todo)} checked (back in Myntra's stock or claimed){more}"]
    if not live:
        return [f"{name}: {len(due)} due of {len(todo)} checked (not raised: MYNTRA_SPF_SJIT_TICKETS is off){more}"]
    lines, jobs, raised = [], [], 0
    for i in range(0, len(due), SPF_BULK_MAX):
        part = due[i:i + SPF_BULK_MAX]
        try:
            jobs.append(portal.spf_bulk_claim(part, cat, SJIT_DESCRIPTION, model="SJIT"))
            raised += len(part)
            for core in part:
                res[core].update(result=SJIT_RAISED, job=jobs[-1], category=cat)
        except Exception as exc:  # noqa: BLE001 - the next part / account still goes
            log.exception("%s SJIT claim failed", account)
            lines.append(f"{name}: {len(part)} NOT raised: {str(exc)[:80]}")
            for core in part:
                res[core]["result"] = SJIT_NOT_RAISED
    if jobs:
        lines.append(f"{name}: {raised} raised (job {', '.join(map(str, jobs))}){more}")
    return lines


def sjit_ticketed(rows: list[dict]) -> set[str]:
    """The core item ids and order lines of the account's SJIT claims (portal.spf_tickets(model="SJIT"))."""
    out = set()
    for t in rows:
        out.update(str(t.get(k)).strip() for k in ("factCoreId", "orderLineId") if not _blank(t.get(k)))
    return out


def write_ticket_file(path: Path, rows: list[dict]) -> None:
    """xlsx, not CSV: ticket ids then stay numbers in the master, as from the hand export."""
    from openpyxl import Workbook
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("tickets")
    ws.append(TICKET_HEADER)
    for t in rows:
        ws.append([t.get(c) for c in TICKET_HEADER])
    wb.save(path)


def portal_tickets(portal, account: str, dest: Path, cached: dict | None = None,
                   details: dict | None = None, replies: list | None = None) -> set[str]:
    """Every ticket of the account into dest/<account>/TICKET_FILE; the order lines they cover.
    With `details` (account -> TICKETS rows), the recent / open claims are read in full too
    (ticket_details, reusing `cached` rows of unchanged tickets) and a rejection's reason goes
    into the ticket file, so the master's REJECTION REASON shows it."""
    from .engine import norm
    rows = portal.spf_tickets()
    if details is not None:
        # The full list is 35 pages and the portal's order can shift while they are read (on
        # 23 Oct 2026 one read missed 900 of MAIN's 2,288 recent claims): the recent ones are
        # read again on their own with the claim date filter, a short and steady list.
        since = datetime.combine(date.today() - timedelta(days=num("MYNTRA_SPF_DETAIL_DAYS", 120)), datetime.min.time())
        seen = set()
        rows = [t for t in rows + portal.spf_tickets(since=since)
                if not (t.get("ticketId") in seen or seen.add(t.get("ticketId")))]
        details[account] = ticket_details(portal, account, rows, cached or {})
        reason = {d["TICKET ID"]: d["REASON"] for d in details[account] if d.get("REASON")}
        for t in rows:
            t["validationReason"] = reason.get(str(t.get("ticketId")))
    write_ticket_file(dest / account / TICKET_FILE, rows)
    if replies is not None:     # claims waiting on our reply (MYNTRA_SPF_REPLY=1 sends them)
        replies += reply_waiting(portal, account, rows, live=num("MYNTRA_SPF_REPLY", 0) == 1)
    log.info("%s: %d SPF tickets on the portal", account, len(rows))
    return {norm(t.get("orderLineId")) for t in rows if t.get("orderLineId")}


# ------------------------------------------------------------------ replies to claims waiting on us

# A claim that turns AWAITING_SELLER_RESPONSE closes by itself after the portal's autoCloseTAT (4 days):
# the reply is chosen from Myntra's last message, as the QUIRY SPF bulk reply tool does
# (tools/myntra-spf-bulk-reply.js); the first rule that matches wins, else the default.
REPLY_RULES = [
    (re.compile(r"shipping label|label (photo|image|proof)", re.I),
     "The shipping label photograph is already attached to this ticket. "
     "Kindly re-check the uploaded proof and let us know if anything else is needed."),
    (re.compile(r"(share|provide|upload|attach).{0,40}(proof|photo|image|document|pod)", re.I),
     "The available proofs are already attached to this ticket. "
     "Please confirm exactly which document is still required so we can upload it."),
    (re.compile(r"return (has been|was) delivered|delivered to (the )?seller", re.I),
     "The return has not been received at our warehouse. Kindly share the POD for the delivery, "
     "or process the claim."),
    (re.compile(r"working on (it|this|your)|will (get back|update)|under (review|process)", re.I),
     "Requesting an update on this claim. Kindly share the current status."),
]
DEFAULT_REPLY = ("Requesting an update on this claim. The return has still not been received at our end. "
                 "Kindly re-check and share the current status.")
OURS = re.compile(r"vendor|bindal", re.I)   # our side signs "<name> - Vendor"; Myntra "Sellersupport", agents


def reply_for(comments: list[dict]) -> tuple[str, str] | None:
    """(rule, reply) for a claim's support thread (newest first); None when we spoke last."""
    if comments and OURS.search(str(comments[0].get("user") or "")):
        return None
    theirs = next((c for c in comments if not OURS.search(str(c.get("user") or ""))), {})
    text = plain(theirs.get("comment"))
    for i, (pattern, reply) in enumerate(REPLY_RULES, 1):
        if pattern.search(text):
            return f"rule {i}", reply
    return "default", DEFAULT_REPLY


def reply_waiting(portal, account: str, rows: list[dict], live: bool) -> list[str]:
    """Answer the account's claims waiting on us (live), or list what would be sent. Lines for
    the report."""
    lines = []
    for t in [t for t in rows if t.get("status") == AWAITING_US]:
        tid = t.get("ticketId")
        try:
            claim = portal.spf_claim(tid)
            fw = claim.get("fwTicketId")
            if claim.get("status") != AWAITING_US or not fw or not claim.get("description"):
                continue
            pick = reply_for(portal.spf_comments(fw))
            if not pick:
                lines.append(f"{account} SPF {tid}: we replied last, left")
                continue
            rule, reply = pick
            if live:
                portal.spf_reply(claim, reply)
                time.sleep(1.2)
            lines.append(f"{account} SPF {tid} waiting on us: {'replied' if live else 'would reply'} ({rule})")
        except Exception as exc:  # noqa: BLE001 - the next ticket still goes
            log.warning("%s SPF %s reply failed: %s", account, tid, exc)
            lines.append(f"{account} SPF {tid} waiting on us: reply failed ({str(exc)[:60]})")
    return lines


# ------------------------------------------------------------------ disputes on rejected claims

# Owner's rule (4 Nov 2026): a claim stays alive until the return is received or the SPF is paid.
DISPUTE_TEXT = ("Hi Team, this return has not been physically received at our warehouse and we have no proof of "
                "delivery for it. Kindly re-check and approve the claim.")
SUPERSEDED = re.compile(r"new .*ticket", re.I)     # rejected because a newer ticket took its place


def dispute_due(row: dict, master: dict | None, today: date) -> bool:
    """A rejected claim to dispute today: on the master, not received or settled, no courier POD, a
    worked order, not replaced by a newer ticket, and untouched for MYNTRA_SPF_DISPUTE_DAYS (7)."""
    from .pipeline import not_worked, resolved
    if row.get("STATUS") != "REJECT" or master is None or SUPERSEDED.search(str(row.get("REASON") or "")):
        return False
    if not_worked(master) or resolved(master) or str(master.get("RETURN POD") or "").strip().upper() == "YES":
        return False
    if row.get("CATEGORY") == CATEGORY_NAME[DELAYED] and env("MYNTRA_SPF_DISPUTE_DELAYED") != "1":
        return False
    try:
        updated = datetime.strptime(str(row.get("LAST UPDATED"))[:11], "%d-%b-%Y").date()
    except ValueError:
        return False
    return (today - updated).days >= num("MYNTRA_SPF_DISPUTE_DAYS", 7)


def disputes(path: Path, today: date, details: dict[str, list[dict]], skip: set[tuple] = frozenset()) -> dict[str, list[str]]:
    """account -> ticket ids to dispute. skip: (order_line_id, return_id) keys known to be received."""
    from openpyxl import load_workbook
    from .engine import SHEETS, master_rows, norm
    wb = load_workbook(path, read_only=True)
    out: dict[str, list[str]] = {}
    for name in SHEETS:
        rows = {norm(r.get("order_line_id")): r for r in master_rows(wb, name)
                if (norm(r.get("order_line_id")), norm(r.get("return_id"))) not in skip}
        due = [d["TICKET ID"] for d in details.get(name, []) if dispute_due(d, rows.get(norm(d.get("ORDER LINE ID"))), today)]
        if due:
            out[name] = due
    wb.close()
    return out


def open_disputes(portal, account: str, ids: list[str], live: bool) -> list[str]:
    """Dispute every one of them (live; owner's rule, no cap), or count them. Lines for the report."""
    if not live:
        return [f"{account} SPF disputes: {len(ids)} due, none opened (MYNTRA_SPF_DISPUTE is off)"]
    done, failed, again = 0, 0, []
    for tid in ids:
        try:
            claim = portal.spf_claim(tid)
            if claim.get("status") != "REJECT":
                continue
            if claim.get("fwTicketId"):
                # disputed once already (its Seller Support ticket) and rejected again: the portal takes no second
                # dispute (createFwTicket fails, 17 Nov 2026); named for the owner, the claim stays alive
                again.append(str(tid))
                continue
            portal.spf_dispute(claim, DISPUTE_TEXT)
            done += 1
            time.sleep(1.2)
        except Exception as exc:  # noqa: BLE001 - the next ticket still goes
            log.warning("%s SPF %s dispute failed: %s", account, tid, exc)
            failed += 1
    lines = [f"{account} SPF disputes: {done} opened of {len(ids)} due" + (f", {failed} failed" if failed else "")]
    if again:
        lines.append(f"{account} SPF: {len(again)} rejected again after a dispute (the portal takes no second one; "
                     f"Partner Support): {', '.join(again[:20])}" + (" ..." if len(again) > 20 else ""))
    return lines


# ------------------------------------------------------------------ ticket details

def _utc(v) -> datetime | None:
    try:
        return datetime.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S") + IST
    except (TypeError, ValueError):
        return None


def _ist(v) -> datetime | None:
    """The portal's MM-DD-YYYY HH:MM:SS (IST) times."""
    try:
        return datetime.strptime(str(v)[:19], "%m-%d-%Y %H:%M:%S")
    except (TypeError, ValueError):
        return None


def _when(d: datetime | None) -> str:
    return f"{d:%d-%b-%Y %H:%M}" if d else ""


def plain(html) -> str:
    t = re.sub(r"<[^>]+>", " ", str(html or "")).replace("&nbsp;", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip().lstrip(": ").strip()


def history_text(history) -> str:
    """{"OPEN": "09-30-2026 17:28:03", "REJECT": "10-01-2026 18:37:21"} -> OPEN 30-Sep 17:28 > REJECT 01-Oct 18:37"""
    try:
        h = json.loads(history) if isinstance(history, str) else (history or {})
    except ValueError:
        return str(history or "")
    steps = sorted(((_ist(v), k) for k, v in h.items()), key=lambda s: s[0] or datetime.min)
    return " > ".join(f"{k} {d:%d-%b %H:%M}" if d else k for d, k in steps)


def detail_row(account: str, t: dict, claim: dict, comments: list[dict]) -> dict:
    """One TICKETS row from the ticket list entry, its claim page and its Seller Support replies."""
    last = comments[0] if comments else {}
    status = claim.get("status") or t.get("status")
    reason = claim.get("rejectReasonDescription") or claim.get("rejectReason") or claim.get("validationReason")
    return {
        "ACCOUNT": account, "TICKET ID": str(t.get("ticketId")), "ORDER LINE ID": str(t.get("orderLineId") or ""),
        "RETURN ID": str(t.get("returnId") or claim.get("returnId") or ""),
        "ORDER ID": str(t.get("orderId") or claim.get("orderId") or ""),
        "CATEGORY": CATEGORY_NAME.get(t.get("issueCategory"), t.get("issueCategory")), "STATUS": status,
        "NEEDS OUR REPLY": "YES" if status == AWAITING_US else "",
        "CREATED": _when(_utc(t.get("createdOn"))), "LAST UPDATED": _when(_utc(t.get("lastModifiedOn"))),
        "STATUS HISTORY": history_text(claim.get("history")), "REASON": reason or "",
        "COMPENSATION": claim.get("compensationAmount"), "UTR": claim.get("utr") or "",
        "PAYMENT INITIATED": str(claim.get("paymentInitiatedOn") or ""),
        "DESCRIPTION": claim.get("description") or "", "SUPPORT TICKET": str(claim.get("fwTicketId") or ""),
        "REPLIES": len(comments), "LAST REPLY BY": last.get("user") or "",
        "LAST REPLY AT": _when(_ist(last.get("createdOn"))), "LAST REPLY": plain(last.get("comment"))[:2000],
    }


def ticket_details(portal, account: str, rows: list[dict], cached: dict[str, dict]) -> list[dict]:
    """TICKETS rows of the account: claims created in the last MYNTRA_SPF_DETAIL_DAYS (120) days
    and older ones not settled yet. A ticket whose LAST UPDATED is the cached row's is not read
    again; at most MYNTRA_SPF_DETAIL_MAX (3000) claim pages a run, the rest keep the cached row
    (or the list's own fields) until the next run."""
    since = datetime.combine(date.today() - timedelta(days=num("MYNTRA_SPF_DETAIL_DAYS", 120)), datetime.min.time())
    keep = [t for t in rows if (_utc(t.get("createdOn")) or datetime.min) >= since
            or t.get("status") not in FINAL_STATUSES]
    todo, out = [], {}
    for t in keep:
        key, c = str(t.get("ticketId")), cached.get(str(t.get("ticketId")))
        if c and c.get("LAST UPDATED") == _when(_utc(t.get("lastModifiedOn"))):
            out[key] = {**c, "ACCOUNT": account}
        else:
            todo.append(t)
    cap = num("MYNTRA_SPF_DETAIL_MAX", 3000)

    def one(t):
        try:
            claim = portal.spf_claim(t["ticketId"])
            fw = claim.get("fwTicketId")
            return detail_row(account, t, claim, portal.spf_comments(fw) if fw else [])
        except Exception as exc:  # noqa: BLE001 - the cached row / the list's fields stand
            log.warning("%s ticket %s not read: %s", account, t.get("ticketId"), str(exc)[:100])
            return cached.get(str(t.get("ticketId"))) or detail_row(account, t, {}, [])

    with ThreadPoolExecutor(max_workers=num("MYNTRA_SPF_DETAIL_WORKERS", 6)) as pool:
        for row in pool.map(one, todo[:cap]):
            out[row["TICKET ID"]] = row
    for t in todo[cap:]:
        out[str(t["ticketId"])] = cached.get(str(t["ticketId"])) or detail_row(account, t, {}, [])
    # a claim already on the sheet stays there, even when this run's list missed it
    for key, c in cached.items():
        if key not in out and c.get("ACCOUNT") == account:
            out[key] = c
    log.info("%s: %d claims on the TICKETS sheet (%d read now, %d unchanged)", account, len(out),
             min(len(todo), cap), len(keep) - len(todo))
    return sorted(out.values(), key=lambda d: d["TICKET ID"], reverse=True)


def read_details(path: Path) -> dict[str, dict]:
    """The previous master's TICKETS rows by ticket id (none when the sheet is not there)."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    try:
        if DETAIL_SHEET not in wb.sheetnames:
            return {}
        rows = wb[DETAIL_SHEET].iter_rows(values_only=True)
        head = [str(h or "") for h in next(rows, [])]
        out = {}
        for v in rows:
            r = {h: ("" if x is None else x) for h, x in zip(head, v)}
            if r.get("TICKET ID"):
                r["TICKET ID"] = str(r["TICKET ID"])
                out[r["TICKET ID"]] = r
        return out
    finally:
        wb.close()


def resolve_raised(portal, account: str, olis: list[str], since: datetime, cats: dict[str, str]) -> list[dict]:
    """The real tickets of claims just raised (a bulk job creates them a minute or so later):
    the account's tickets created since `since`, asked every 20 s for up to
    MYNTRA_SPF_RESOLVE_MINUTES (2) minutes - they turn up within 2 - until every order line has one."""
    from .engine import norm
    want, found = set(olis), {}
    deadline = time.time() + 60 * num("MYNTRA_SPF_RESOLVE_MINUTES", 2)
    while True:
        try:
            for t in portal.spf_tickets(since=since - timedelta(minutes=10), page_size=200):
                oli = norm(t.get("orderLineId"))
                if oli in want and (oli not in found or str(t.get("issueCategory")) == cats.get(oli)):
                    found[oli] = t
        except Exception as exc:  # noqa: BLE001 - asked again, or the BOT JOB rows stay
            log.warning("%s new tickets not read: %s", account, str(exc)[:100])
        if len(found) == len(want) or time.time() > deadline:
            break
        time.sleep(20)
    log.info("%s: %d of %d claims just raised have their ticket", account, len(found), len(want))
    return list(found.values())


def raise_claims(portal, account: str, wanted: dict[str, list[str]], dest: Path, live: bool,
                 seller: int | None = None, details: list[dict] | None = None) -> list[str]:
    """Raise this account's claims (live) or only list them. The real tickets are waited for
    (resolve_raised) and written as NEW_FILE, so the master shows their ticket ids at once; a
    claim whose ticket has not turned up yet is in the bot's file as "BOT JOB <job id>" until
    the next run. Their TICKETS rows go into `details`. One line per category for the report."""
    from ..portals.myntra import SPF_BULK_MAX
    cap = num("MYNTRA_SPF_TICKET_MAX", SPF_BULK_MAX)
    lines, raised = [], []
    started = datetime.now()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for cat in (RNR, TRANSIT, DELAYED):
        ids = wanted.get(cat) or []
        if not ids:
            continue
        todo, rest = ids[:cap], len(ids) - min(len(ids), cap)
        more = f", {rest} left for the next run" if rest else ""
        if not live:
            lines.append(f"{account} {CATEGORY_NAME[cat]}: {len(todo)} due (not raised: tickets off){more}")
            continue
        jobs = []
        for i in range(0, len(todo), SPF_BULK_MAX):
            part = todo[i:i + SPF_BULK_MAX]
            try:
                job = portal.spf_bulk_claim(part, ISSUE.get(cat, cat), DESCRIPTION[cat], seller=seller)
            except Exception as exc:  # noqa: BLE001 - the other category / account still go
                log.exception("%s %s claim failed", account, cat)
                lines.append(f"{account} {CATEGORY_NAME[cat]}: {len(part)} NOT raised: {str(exc)[:80]}")
                continue
            jobs.append(job)
            raised += [{"ticketId": f"BOT JOB {job}", "orderLineId": o, "issueCategory": ISSUE.get(cat, cat),
                        "status": "RAISED BY BOT", "createdOn": now, "_ours": cat} for o in part]
        if jobs:
            n = sum(1 for t in raised if t["_ours"] == cat)
            lines.append(f"{account} {CATEGORY_NAME[cat]}: {n} raised (job {', '.join(map(str, jobs))}){more}")
    if raised:
        real = resolve_raised(portal, account, [t["orderLineId"] for t in raised], started,
                              {t["orderLineId"]: t["issueCategory"] for t in raised})
        from .engine import norm
        got = {norm(t.get("orderLineId")) for t in real}
        write_ticket_file(dest / account / NEW_FILE, real)
        write_ticket_file(dest / account / BOT_FILE, [t for t in raised if t["orderLineId"] not in got])
        if details is not None:
            details += [detail_row(account, t, {}, []) for t in real]
        if len(got) < len(raised):
            lines.append(f"{account}: {len(raised) - len(got)} claims raised but no ticket id yet (BOT JOB, next run)")
    return lines
