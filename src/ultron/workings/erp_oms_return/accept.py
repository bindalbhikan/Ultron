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


def fill(form, wanted: dict[str, int], warehouses: dict[str, str], erp_type: str = "") -> tuple[dict | None, str]:
    """The fields to post for these SKU quantities, or (None, why)."""
    body = {}
    for i in form.find_all("input"):
        n = i.get("name")
        if n and i.get("type") not in ("radio", "checkbox", "file", "submit", "button"):
            body[n] = i.get("value") or ""
    for sel in form.find_all("select"):
        if sel.get("name"):
            chosen = sel.find("option", selected=True)
            body[sel["name"]] = chosen.get("value") if chosen else ""
    rows = {}
    for k, v in body.items():
        m = re.fullmatch(r"data\[SkuQty\]\[(\d+)\]\[sku_code\]", k)
        if m:
            rows[v.strip().upper()] = m.group(1)
    missing = [s for s in wanted if s not in rows]
    if missing:
        return None, "SKU not on the form"
    for sku, n in rows.items():
        body[f"data[SkuQty][{n}][good]"] = str(wanted.get(sku, 0))
        body[f"data[SkuQty][{n}][bad]"] = "0"
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


def accept(client: OmsGuruClient, awb: str, wanted: dict[str, int], note: str, warehouses: dict[str, str], dry_run: bool = False,
           erp_type: str = "") -> Result:
    """Accept one AWB's SKUs as Good. wanted: {SKU in capitals: qty}"""
    res = Result(awb=awb, outcome="Failed", skus=wanted)
    ids = client.search(awb, "AWB")
    if not ids:
        res.outcome = "Not found in OMS"
        return res
    res.order = ids[0]
    html, statuses, res.return_awb = read_order(client, res.order)
    details(res, html)
    res.status = statuses[0] if statuses else ""
    if statuses and all(s in ACCEPTED for s in statuses):
        res.note = add_note(client, res.order, html, note) if not dry_run else False
        res.outcome = "Already accepted"
        return res
    if statuses and all(s in CANCELLED for s in statuses):
        res.outcome = "OMS shows cancelled"
        return res
    forms = open_form(client, awb)
    if not forms:
        res.detail = "no return form"
        return res
    # an AWB can open several forms (an order split in parts): each SKU goes on the form that has it
    plan, left = [], dict(wanted)
    for form in forms:
        on_form = {i.get("value", "").strip().upper() for i in form.find_all("input") if re.fullmatch(r"data\[SkuQty\]\[\d+\]\[sku_code\]", i.get("name") or "")}
        part = {s: left.pop(s) for s in list(left) if s in on_form}
        if part:
            body, why = fill(form, part, warehouses, erp_type)
            if body is None:
                res.detail = why
                return res
            plan.append((form, body))
    if left:
        res.outcome, res.detail = "SKU not on the form", ", ".join(sorted(left))[:80]
        return res
    if dry_run:
        res.outcome = "Would accept"
        return res
    for form, body in plan:
        r = client.s.post(BASE_URL + form.get("action"), data=body, timeout=client.timeout)
        if r.status_code != 200:
            res.detail = f"HTTP {r.status_code}"
            return res
        if '"result":"Fail"' in r.text.replace(" ", ""):
            res.detail = r.text[:120]
    html, statuses, res.return_awb = read_order(client, res.order)
    res.status = statuses[0] if statuses else ""
    if any(s in ACCEPTED for s in statuses):
        res.outcome = "Accepted"
        res.note = add_note(client, res.order, html, note)
    else:
        res.detail = f"status after: {res.status}"
    return res
