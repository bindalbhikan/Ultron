"""Retry the listings selected on each warehouse's Failed tab."""
import re

from ultron.core.html import parse, text_of
from ultron.portals.omsguru import BASE_URL, OmsGuruError

PAGE = BASE_URL + "/channel_listings/failed"
ACTION = BASE_URL + "/channel_listings/process_failed_listings/1"
FIELD = "data[ChannelCompanySkusWarehouse][][id]"
COMMAND = "Retry Push Inventory for Selected Listings"


def retry_failed(client, dry_run=False):
    warehouses = client.warehouses()
    if not warehouses:
        raise OmsGuruError("Cannot identify warehouses for the Failed tab")
    processed = 0
    for warehouse in warehouses:
        client.set_warehouse(warehouse)
        seen = set()
        page = 1
        while True:
            url = PAGE if page == 1 else f"{PAGE}/page:{page}"
            soup = parse(client.get(url).text)
            count = re.search(r"showing [0-9,]+ records out of ([0-9,]+) total", soup.text(), re.I)
            form = soup.select_one(f'form[action="{ACTION}"]')
            if not count or not form or form.attr("method", "").lower() != "post":
                raise OmsGuruError("Failed listing count or retry form unavailable")
            rows = [i["value"] for i in soup.select('input.channel_listings_cb_select') if i.attr("name") == FIELD]
            if not rows and int(count[1].replace(",", "")):
                raise OmsGuruError("Failed listings could not be read")
            ids = [value for value in rows if value not in seen]
            if ids and not dry_run:
                data = {i["name"]: i.attr("value", "") for i in form.select("input[name]")}
                if data.get("data[Click][command]") != COMMAND or not all(x.isdigit() for x in ids):
                    raise OmsGuruError("Failed listing retry form changed")
                data[FIELD] = ids
                response = client.s.post(ACTION, data=data, timeout=client.timeout,
                                         headers={"Referer": url, "Origin": BASE_URL})
                notice = text_of(parse(response.text).select_one("#flashMessage, .alert"))
                if response.status_code != 200 or "marked to retry inventory push successfully" not in notice.lower():
                    raise OmsGuruError(f"Retry unconfirmed after {processed} accepted listings")
            processed += len(ids)
            seen.update(ids)
            if ids and not dry_run:
                # Accepted rows usually leave the queue immediately. Read this page again before advancing.
                continue
            if not soup.select_one(f'a[href$="/failed/page:{page + 1}"]'):
                break
            page += 1
    return processed
