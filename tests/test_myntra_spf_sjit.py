"""SJIT / FBM in-transit SPF claims through Myntra's new SJIT tool (25 Nov 2026)."""
from datetime import date, datetime, timedelta

from ultron.workings.myntra_spf import tickets
from ultron.workings.myntra_spf.pipeline import _windows
from ultron.workings.portals import myntra as mp

TODAY = date(2026, 11, 25)
HEAD = "core_item_id,order_line_id,type,status,return_created_date,order_rto_date\n"


def _day(days_ago: int) -> str:
    return f"{TODAY - timedelta(days=days_ago)} 10:00:00"


def test_sjit_returns_window_is_the_in_transit_claim_window():
    w = _windows(TODAY)[mp.SJIT_RETURNS_REPORT_ID]
    assert w[0][0] == TODAY - timedelta(days=120) and w[-1][1] == TODAY - timedelta(days=61)
    assert all((b - a).days <= 29 for a, b in w)


def test_sjit_report_jobs_are_matched_as_sjit():
    assert mp.query_for(mp.SJIT_RETURNS_REPORT_ID)["partnerType"] == "SJIT"
    assert mp.query_for(mp.REPORT_ID)["partnerType"] == "PPMP"
    job = {"reportId": 70, "status": "COMPLETED", "createdOn": datetime(2026, 11, 24).timestamp() * 1000,
           "queryParams": {"storeId": "2297", "partnerType": "SJIT", "reportStartDate": "2026-11-01",
                           "reportEndDate": "2026-11-23"}}
    assert mp.job_range(job, 70) == (date(2026, 11, 1), date(2026, 11, 23))
    assert mp.job_range({**job, "queryParams": {**job["queryParams"], "partnerType": "PPMP"}}, 70) is None


def test_candidates_by_age_ticket_and_master(tmp_path):
    (tmp_path / "r.csv").write_text(
        HEAD
        + f"C1,11,Return,Ret Created,{_day(70)},\n"        # due
        + f"C2,12,RTO,RTO Created,1970-01-01 05:30:00,{_day(90)}\n"   # an RTO: its RTO day counts
        + f"C3,13,Return,Ret Created,{_day(30)},\n"        # too young
        + f"C4,14,Return,Ret Created,{_day(130)},\n"       # too old
        + f"C5,15,Return,Ret Created,{_day(70)},\n"        # SJIT claim on the item
        + f"C6,16,Return,Ret Created,{_day(70)},\n"        # settled on the master
        + f",17,Return,Ret Created,{_day(70)},\n",         # a PPMP line: no core item id
        encoding="utf-8")
    rows = tickets.sjit_returns(tmp_path)
    assert {r["core_item_id"] for r in rows} == {"C1", "C2", "C3", "C4", "C5", "C6"}
    got = tickets.sjit_candidates(rows, TODAY, ticketed={"C5"}, blocked={"16"})
    assert sorted(r["core_item_id"] for r in got) == ["C1", "C2"]


class Portal:
    def __init__(self, items):
        self.items, self.claims = items, []

    def spf_sjit_item(self, core):
        return self.items[core]

    def spf_bulk_claim(self, ids, category, description, model="PPMP", seller=None):
        self.claims.append((list(ids), category, model))
        return 99


ITEMS = {"C1": {"itemStatus": "SHIPPED"}, "C2": {"itemStatus": "STORED"},
         "C3": {"itemStatus": "SHIPPED", "ticketId": 5, "issueCategory": tickets.SJIT_NOT_SETTLED}}
ROWS = [{"core_item_id": c} for c in ("C1", "C2", "C3")]


def test_only_items_still_out_of_stock_without_a_claim_are_raised():
    portal = Portal(ITEMS)
    lines = tickets.raise_sjit_claims(portal, "MAIN", ROWS, live=True)
    assert portal.claims == [(["C1"], tickets.SJIT_NOT_SETTLED, "SJIT")]
    assert "1 raised (job 99)" in lines[0]


def test_counted_only_when_off():
    portal = Portal(ITEMS)
    lines = tickets.raise_sjit_claims(portal, "MAIN", ROWS, live=False)
    assert portal.claims == [] and "1 due of 3 checked" in lines[0]


def test_an_item_that_cannot_be_checked_is_not_claimed():
    class Broken(Portal):
        def spf_sjit_item(self, core):
            raise RuntimeError("timeout")
    portal = Broken(ITEMS)
    lines = tickets.raise_sjit_claims(portal, "MAIN", ROWS, live=True)
    assert portal.claims == [] and "3 not checked" in lines[0]


def test_bulk_claim_file_has_the_models_column():
    import io

    import polars as pl
    sent = {}

    class Http:
        def put(self, url, data, timeout, headers):
            sent["file"] = data
            return type("R", (), {"status_code": 201})()

    portal = object.__new__(mp.MyntraPortal)
    portal.http, portal.timeout = Http(), 5
    portal.partner_id = lambda: 1

    def call(method, url, **kw):
        if "getUploadToken" in url:
            name = kw["params"]["fileNames"]
            return {name: {"sasUrl": "https://blob/x", "fileNameWithPath": "p/x.xlsx"}}
        sent["body"] = kw["json"]
        return {"jobId": 7}
    portal._call = call
    assert portal.spf_bulk_claim(["1028934", "1028935"], tickets.SJIT_NOT_SETTLED, "d", model="SJIT") == 7
    df = pl.read_excel(io.BytesIO(sent["file"]))
    assert df.columns == ["FactCoreId"] and df["FactCoreId"].to_list() == [1028934, 1028935]
    assert sent["body"]["modelType"] == "SJIT" and sent["body"]["issueCategory"] == tickets.SJIT_NOT_SETTLED
    portal.spf_bulk_claim(["11"], tickets.RNR, "d")
    assert pl.read_excel(io.BytesIO(sent["file"])).columns == ["OrderId"]


def test_results_say_what_happened_to_each_item():
    res = {}
    tickets.raise_sjit_claims(Portal(ITEMS), "MAIN", ROWS, live=True, results=res)
    assert res["C1"]["result"] == tickets.SJIT_RAISED and res["C1"]["job"] == 99
    assert res["C2"]["result"] == tickets.SJIT_BACK and res["C2"]["stock"] == "STORED"
    assert res["C3"]["result"] == tickets.SJIT_CLAIMED


def _ppmp_master(path):
    """A small PPMP master: SUBTOTAL row, headers on row 2, PPMP and SJIT / FBM rows."""
    import xlsxwriter
    head = ["seller_id", "model", "order_line_id", "return_created_date", "RETURN MONTH", "type", "status",
            "AGE (DAYS)", "CLAIM STATUS", "CLAIM TYPE", "FINAL RETURN STATUS", "TICKET ID", "CLAIM TAT", "STATUS",
            "REJECTION REASON", "ORDER AMOUNT", "SPF PAID", "UTR NO"]
    d70, d30 = TODAY - timedelta(days=70), TODAY - timedelta(days=30)
    rows = {"MAIN": [[19170, "PPMP", 10, d70, f"{d70:%Y-%m}", "Return", "Ret Created", 70, "ELIGIBLE", "x", None, None, None, None, None, 500, None, None],
                     [19170, "FBM", 11, d70, f"{d70:%Y-%m}", "Return", "Ret Created", 70, "NON ELIGIBLE", "x", None, None, None, None, None, 800, None, None],
                     [19170, "SJIT", 19, d70, f"{d70:%Y-%m}", "Return", "Ret Delivered", 70, "NON ELIGIBLE", "x", "Return Received", None, None, None, None, 300, None, None]],
            "RETURN IN TRANSIT": [[19170, "FBM", 12, d30, f"{d30:%Y-%m}", "Return", "Ret Created", 30, "NON ELIGIBLE", "x", None, None, None, None, None, 200, None, None, "MAIN"]]}
    wb = xlsxwriter.Workbook(str(path))
    for name, data in rows.items():
        ws = wb.add_worksheet(name)
        h = head + (["ACCOUNT"] if name == "RETURN IN TRANSIT" else [])
        ws.write_row(1, 0, h)
        for r, row in enumerate(data, 2):
            for c, v in enumerate(row):
                if hasattr(v, "year"):
                    ws.write_datetime(r, c, datetime(v.year, v.month, v.day))
                elif v is not None:
                    ws.write(r, c, v)
    wb.close()


def test_sjit_master_like_the_ppmp_master(tmp_path):
    from python_calamine import CalamineWorkbook
    from ultron.workings.myntra_spf import sjit_master
    work = tmp_path / "work"
    (work / "sjit" / "MAIN").mkdir(parents=True)
    (work / "sjit" / "MAIN" / "x_SJIT_Customer_Returns_Report_1_2026-08-01_2026-08-30.csv").write_text(
        HEAD + f"C1,11,Return,Ret Created,{_day(70)},\n" + f"C2,12,Return,Ret Created,{_day(30)},\n"
        + f"C3,13,RTO,RTO Created,1970-01-01,{_day(80)}\n", encoding="utf-8")
    ppmp = tmp_path / "ppmp.xlsx"
    _ppmp_master(ppmp)
    sjit = {"MAIN": [{"ticketId": 501, "factCoreId": "C1", "issueCategory": tickets.SJIT_NOT_SETTLED,
                      "status": "PAYMENT_COMPLETED", "createdOn": "2026-11-20T10:00:00", "compensationAmount": 450}]}
    out = {"MAIN": {"reasons": {"C1": tickets.SJIT_CLAIMED, "C2": tickets.SJIT_YOUNG, "C3": ""},
                    "results": {"C3": {"result": tickets.SJIT_DUE, "stock": "SHIPPED", "checked": "25-Nov-2026 10:30"}}}}
    dest = work / sjit_master.SJIT_MASTER
    stats = sjit_master.build(ppmp, work, TODAY, sjit, out, None, dest)
    wb = CalamineWorkbook.from_path(str(dest))
    assert wb.sheet_names == ["SUMMARY", "DATE SUMMARY", "CLAIM TAT", "MAIN", "DBCC", "FMCC", "RETURN IN TRANSIT",
                              "TICKETS", "INPUT LOG"]
    main = wb.get_sheet_by_name("MAIN").to_python()
    head = main[1]
    rows = {int(r[head.index("order_line_id")]): dict(zip(head, r)) for r in main[2:]}
    assert set(rows) == {11, 19, 13}                     # no PPMP row; C3 only in the SJIT report: a short row
    assert rows[11]["CLAIM STATUS"] == "CLAIM DONE" and str(rows[11]["TICKET ID"]) == "501"
    assert rows[11]["STATUS"] == "PAYMENT_COMPLETED" and rows[11]["FACT CORE ITEM ID"] == "C1"
    assert rows[19]["CLAIM STATUS"] == "NON ELIGIBLE" and rows[19]["BOT RESULT"] == sjit_master.NO_CORE
    assert rows[13]["CLAIM STATUS"] == "ELIGIBLE" and rows[13]["MYNTRA STOCK"] == "SHIPPED"
    assert main[0][head.index("ORDER AMOUNT")] == 1100   # the SUBTOTAL row's cached total
    transit = wb.get_sheet_by_name("RETURN IN TRANSIT").to_python()
    th = transit[1]
    assert dict(zip(th, transit[2]))["CLAIM STATUS"] == "UPCOMING CLAIM"
    summary = wb.get_sheet_by_name("SUMMARY").to_python()
    grand = next(r for r in summary if r[0] == "ALL")
    sh = summary[0]
    assert grand[sh.index("TOTAL RETURNS")] == 4 and grand[sh.index("CLAIM DONE")] == 1
    assert grand[sh.index("IN TRANSIT")] == 1 and grand[sh.index("RETURN RECEIVED")] == 1
    tat = wb.get_sheet_by_name("CLAIM TAT").to_python()
    assert next(r for r in tat if r[0] == "ALL")[tat[0].index("SPF PAID AMT")] == 450
    assert stats["MAIN"]["claims"] == 1 and stats["MAIN"]["eligible"] == 1
    log = wb.get_sheet_by_name("INPUT LOG").to_python()
    assert log[1][2] == "2026-08-01"
    # the next run keeps the item ids it learnt, also when the report no longer has them
    again = work / "again.xlsx"
    for f in (work / "sjit" / "MAIN").glob("*"):
        f.unlink()
    sjit_master.build(ppmp, work, TODAY, sjit, {}, dest, again)
    main2 = CalamineWorkbook.from_path(str(again)).get_sheet_by_name("MAIN").to_python()
    rows2 = {int(r[head.index("order_line_id")]): dict(zip(main2[1], r)) for r in main2[2:]}
    assert rows2[11]["FACT CORE ITEM ID"] == "C1" and rows2[13]["MYNTRA STOCK"] == "SHIPPED"
