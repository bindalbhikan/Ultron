"""A self-shipped customer return must not remain Delivered in business reporting."""
import polars as pl

from ultron.workings.business_report import ajio


def test_self_ship_without_shipping_charge_respects_quantity_and_return_window():
    orders = pl.DataFrame({
        "Cust Order No": ["A", "B", "C", "D"],
        "Seller SKU": ["TEST-SKU"] * 4,
        "Cust Order Date": ["Thu Oct 01 10:00:00 IST 2026"] * 4,
        "Status": ["Delivered"] * 4,
        "Order Qty": ["1"] * 4,
        "Selling Price": ["100"] * 4,
    })
    rtv = pl.DataFrame({
        "Cust Order No": ["A", "B", "C", "D"],
        "SELLER SKU": ["TEST-SKU"] * 4,
        "Return Type": ["SELF_SHIP_WITHOUT_SHIPPING_CHARGE"] * 3 + ["RTO"],
        "Return QTY": ["1", "0", "1", "1"],
        "Return Created Date": ["Sat Nov 14 23:59:59 IST 2026"] * 2
        + ["Sun Nov 15 00:00:00 IST 2026", "Sat Nov 14 10:00:00 IST 2026"],
        "Cust Return Reason": ["Test reason"] * 4,
        "RETURN ORDER NUMBER": ["RA", "RB", "RC", "RD"],
        "Return Status": ["RETURN_DELIVERED"] * 4,
        "Credit Note Number": ["CA", "CB", "CC", "CD"],
    })
    master = pl.DataFrame(schema={c: pl.Utf8 for c in (
        "Channel Name", "Channel Listing SKU Code", "MY SKU", "FINAL SKU", "FINAL MY SKU", "DESIGN-NO", "Brand"
    )})
    raw = ajio.raw_data(orders, rtv, None, master)
    statuses = raw.set_index("CUST ORDER NO")["FINAL STATUS"].to_dict()
    assert statuses == {"A": "Customer Return", "B": "Delivered", "C": "Delivered", "D": "RTO"}
    assert raw["QTY"].sum() == 4
    assert raw["SALE VALUE"].sum() == 400
    assert ajio.returned_units(raw, rtv).tolist() == [1, 0, 0, 1]
