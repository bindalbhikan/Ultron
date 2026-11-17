"""HTML pages read in one place (ultron/core/html.py, docs/libraries/09-selectolax.md): selectolax and the
BeautifulSoup fallback (Android / Termux) give the same answers."""
import pytest

from ultron.core import html as H

PAGE = """<html><body>
<dl><dt>Order :</dt><dd> 123 </dd><dt>Channel</dt>  <dd>Myntra - <b>MAIN</b></dd></dl>
<table id="t"><thead><tr><th>A</th><th>SLA Date</th></tr></thead>
<tbody><tr data-id="9"><td>one</td><td><a href="/orders/view/77">x</a> two <span>three</span></td><td></td></tr></tbody></table>
<ul><li>file ready <a href="/orders/download/5">get</a></li></ul>
<select name="w"><option value="1">One</option><option value="2" selected>Two</option></select>
<script>var a = "not text";</script>
</body></html>"""


@pytest.fixture(params=["lexbor", "bs4"])
def page(request):
    return H.parse(PAGE, engine="" if request.param == "lexbor" else "bs4")


def test_cells_text_and_attributes(page):
    tr = page.select_one("#t tbody > tr")
    assert [H.text_of(td) for td in tr.children("td")] == ["one", "x two three", ""]
    assert [H.text_of(th) for th in page.select("#t thead th")] == ["A", "SLA Date"]
    assert tr.attr("data-id") == "9" and tr.attr("nope") is None and tr.attr("nope", "") == ""
    assert page.select_one('a[href*="/orders/view/"]')["href"] == "/orders/view/77"
    with pytest.raises(KeyError):
        tr["nope"]


def test_dt_dd_parent_and_selected(page):
    pairs = [(H.text_of(dt), H.text_of(dt.next_sibling("dd"))) for dt in page.select("dt")]
    assert pairs == [("Order :", "123"), ("Channel", "Myntra - MAIN")]
    a = page.select_one('a[href*="/orders/download/"]')
    assert H.text_of(a.parent_of("li")) == "file ready get"
    assert page.select_one("option[selected]").attr("value") == "2"
    assert "not text" not in page.text() and H.text_of(None) == ""


def test_lexbor_closes_unclosed_cells_as_browsers_do():
    """html.parser nests an unclosed <td> in the one before; Lexbor (the HTML5 rules) closes it."""
    page = H.parse("<table><tr><td>one<td>two<td></table>")
    if not page._lex:
        pytest.skip("selectolax not installed")
    assert [H.text_of(td) for td in page.select_one("tr").children("td")] == ["one", "two", ""]
