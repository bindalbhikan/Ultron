"""Accept a return in OMSGuru as Good, the way its Quick Returns screen does (Orders > Quick Returns, manual mode, Accept
Return), and write the ERP date in the order's notes. It never touches Putaways, so OMSGuru's stock does not change.

One AWB at a time: every SKU the ERP booked in under that AWB goes on one form. Nothing is sent when a SKU is not on the form or
the ERP's qty is above what was sent, and the result is read back from the order page.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from ultron.portals.omsguru import BASE_URL, OmsGuruClient

log = logging.getLogger("bindal.erp_oms_return")

ACCEPTED = {"Return Received", "Partial Return Received", "Cancelled Return Received", "Partial Cancelled Return Received"}
CANCELLED = {"Cancelled", "Cancelled Before Shipping"}
STATUS = re.compile(r'class="label label-\w+ status">\s*([^<]+?)\s*</span>')
SKU_ROW = re.compile(r"data\[SkuQty\]\[(\d+)\]\[sku_code\]")
REASON = re.compile(r'"(?:message|msg|error|reason)"\s*:\s*"([^"]+)"')
RETURN_TRACKER = re.compile(r"<dt>Return Tracking Id</dt>\s*<dd>\s*([^&<\s]*)")


@dataclass
class Result:
    awb: str
    outcome: str                    # Accepted, Already accepted, OMS shows cancelled, Not found in OMS, SKU not on the form, Qty above sent, Failed
    order: str = ""
    status: str = ""
    return_awb: str = ""
    note: bool = False
    order_no: str = ""
    order_date: str = ""
    channel: str = ""
    detail: str = ""
    skus: dict = field(default_factory=dict)
    done: set = field(default_factory=set)      # when only some forms went through: the SKUs fully on those forms


def _token(html: str) -> str:
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""


def read_order(client: OmsGuruClient, order_id: str) -> tuple[str, list[str], str]:
    """(the order page, the status of each item, the return AWB)"""
    html = client.get(f"{BASE_URL}/orders/view/{order_id}").text
    tracker = RETURN_TRACKER.search(html)
    return html, [s.strip() for s in STATUS.findall(html)], (tracker.group(1) if tracker else "")


def details(res: Result, html: str) -> None:
    """The order's number, date and channel, as its page shows them."""
    box = BeautifulSoup(html, "html.parser")
    for dt in box.find_all("dt"):
        label, dd = dt.get_text(" ", strip=True).rstrip(":").strip().lower(), dt.find_next_sibling("dd")
        value = dd.get_text(" ", strip=True) if dd else ""
        if label == "order" and not res.order_no:
            res.order_no = value[:60]
        elif label == "order date" and not res.order_date:
            res.order_date = value[:30]
        elif label == "channel" and not res.channel:
            res.channel = value.rsplit(" - ", 1)[-1][:40]


def add_note(client: OmsGuruClient, order_id: str, html: str, note: str) -> bool:
    if note in html:
        return True
    url = f"{BASE_URL}/orders/addInvoiceNote/{order_id}"
    r = client.s.post(url, data={"data[note]": note, "oms_token": _token(html)}, timeout=client.timeout)
    if r.status_code != 200:
        return False
    return note in client.get(f"{BASE_URL}/orders/view/{order_id}").text


def open_form(client: OmsGuruClient, awb: str):
    """The return forms Quick Returns opens for an AWB, in manual mode, Good: searching accepts nothing."""
    url = f"{BASE_URL}/orders/quickReturns"
    page = BeautifulSoup(client.get(url).text, "html.parser")
    form = next(f for f in page.find_all("form") if "quickReturns" in (f.get("action") or ""))
    data = {i.get("name"): i.get("value") or "" for i in form.find_all("input") if i.get("name") and i.get("type") == "hidden"}
    data.update({"data[Invoice][search_value]": awb, "data[Invoice][is_manual]": "1", "data[Invoice][batch_process]": "0",
                 "data[Invoice][batch_return_type]": "good"})
    s = BeautifulSoup(client.s.post(url, data=data, timeout=client.timeout).text, "html.parser")
    return [f for f in s.find_all("form") if (f.get("id") or "").startswith("ReturnForm")]


def rows_of(form) -> dict[str, list[tuple[str, int | None]]]:
    """{SKU in capitals: [(its row on the form, the qty that row takes; None = the form sets no limit)]}"""
    rows: dict[str, list[tuple[str, int | None]]] = {}
    for i in form.find_all("input"):
        m = SKU_ROW.fullmatch(i.get("name") or "")
        if m:
            good = form.find("input", attrs={"name": f"data[SkuQty][{m.group(1)}][good]"})
            top = str((good.get("max") if good else "") or "").strip()
            rows.setdefault((i.get("value") or "").strip().upper(), []).append((m.group(1), int(top) if top.isdigit() else None))
    return rows


def fill(form, wanted: dict[str, int], warehouses: dict[str, str], erp_type: str = "") -> tuple[dict | None, str]:
    """The fields to post for these SKU quantities, spread over the SKU's rows, or (None, why)."""
    body = {}
    for i in form.find_all("input"):
        n = i.get("name")
        if n and i.get("type") not in ("radio", "checkbox", "file", "submit", "button"):
            body[n] = i.get("value") or ""
    for sel in form.find_all("select"):
        if sel.get("name"):
            chosen = sel.find("option", selected=True)
            body[sel["name"]] = chosen.get("value") if chosen else ""
    rows = rows_of(form)
    if [s for s in wanted if s not in rows]:
        return None, "SKU not on the form"
    for sku, on_form in rows.items():
        left = wanted.get(sku, 0)
        for n, room in on_form:
            take = left if room is None else min(left, room)
            body[f"data[SkuQty][{n}][good]"] = str(take)
            body[f"data[SkuQty][{n}][bad]"] = "0"
            left -= take
        if left:
            return None, "Qty above sent"
    text = re.sub(r"\s+", " ", form.get_text(" ", strip=True))
    dispatch = re.search(r"Dispatch Warehouse\s+(Warehouse \d+)", text)
    warehouse = next((k for k, v in warehouses.items() if dispatch and v == dispatch.group(1)), "")
    if not warehouse:
        return None, "No dispatch warehouse on the form"
    body["data[Invoice][return_warehouse_id]"] = warehouse
    # an order OMSGuru has no return on yet (Ready to ship, Delivered ...) asks the type: as the ERP booked it
    if form.find("select", attrs={"name": "data[Invoice][confirm_return_type]"}):
        if not erp_type:
            return None, "Return type needed"
        body["data[Invoice][confirm_return_type]"] = "customer" if "customer" in erp_type.lower() else "courier"
    return body, ""


def refusal(r) -> str:
    """Why OMSGuru refused a posted form; "" when it did not."""
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    if '"result":"Fail"' not in r.text.replace(" ", ""):
        return ""
    m = REASON.search(r.text)
    return m.group(1)[:80] if m else "OMSGuru answered Fail"


def split_on_forms(forms: list, wanted: dict[str, int]) -> tuple[list[tuple], dict[str, int], set[str]]:
    """Each SKU's qty on the forms that have it, up to what each takes: ([(form, part)], qty left, the SKUs on no form).
    An AWB can open several forms (an order split in parts)."""
    plan, left, seen = [], dict(wanted), set()
    for form in forms:
        part = {}
        for sku, on_form in rows_of(form).items():
            seen.add(sku)
            if left.get(sku):
                rooms = [room for _, room in on_form]
                take = left[sku] if None in rooms else min(left[sku], sum(rooms))
                if take:
                    part[sku] = take
                    left[sku] -= take
        if part:
            plan.append((form, part))
    return plan, {s: n for s, n in left.items() if n}, set(wanted) - seen


def accept(client: OmsGuruClient, awb: str, wanted: dict[str, int], note: str, warehouses: dict[str, str], dry_run: bool = False,
           erp_type: str = "") -> Result:
    """Accept one AWB's SKUs as Good. wanted: {SKU in capitals: qty}

    Accepted means OMSGuru refused no form and, read back from the order page, an item's status moved to a received one. An AWB can
    belong to several orders: all of them are read, and each one that moved gets the note."""
    res = Result(awb=awb, outcome="Failed", skus=wanted)
    ids = client.search(awb, "AWB")
    if not ids:
        res.outcome = "Not found in OMS"
        return res
    res.order = ids[0]
    before = {i: read_order(client, i) for i in ids}
    html, first, res.return_awb = before[ids[0]]
    details(res, html)
    res.status = first[0] if first else ""
    statuses = [s for i in ids for s in before[i][1]]
    if statuses and all(s in ACCEPTED for s in statuses):
        if not dry_run:
            res.note = all([add_note(client, i, before[i][0], note) for i in ids])
        res.outcome = "Already accepted"
        return res
    if statuses and all(s in CANCELLED for s in statuses):
        res.outcome = "OMS shows cancelled"
        return res
    forms = open_form(client, awb)
    if not forms:
        res.detail = "no return form"
        return res
    split, left, unknown = split_on_forms(forms, wanted)
    if unknown:
        res.outcome, res.detail = "SKU not on the form", ", ".join(sorted(unknown))[:80]
        return res
    if left:
        res.outcome, res.detail = "Qty above sent", ", ".join(sorted(left))[:80]
        return res
    plan = []
    for form, part in split:
        body, why = fill(form, part, warehouses, erp_type)
        if body is None:
            res.detail = why
            return res
        plan.append((form, body, part))
    if dry_run:
        res.outcome = "Would accept"
        return res
    refused, went, stuck = [], set(), set()
    for form, body, part in plan:
        why = refusal(client.s.post(BASE_URL + form.get("action"), data=body, timeout=client.timeout))
        if why:
            refused.append(why)
            stuck |= set(part)
        else:
            went |= set(part)
    after = {i: read_order(client, i) for i in ids}
    moved = [i for i in ids if after[i][1] != before[i][1] and any(s in ACCEPTED for s in after[i][1])]
    shown = after[moved[0] if moved else ids[0]]
    res.status = shown[1][0] if shown[1] else ""
    res.return_awb = shown[2] or res.return_awb
    if moved:
        res.note = all([add_note(client, i, after[i][0], note) for i in moved])
    if moved and not refused:
        res.outcome = "Accepted"
        return res
    res.detail = "; ".join(refused) or f"status after: {res.status}"
    if moved:
        res.done = went - stuck
    return res
