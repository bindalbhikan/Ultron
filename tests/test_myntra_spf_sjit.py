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


def test_sjit_master_items_claims_and_history(tmp_path):
    import polars as pl
    from ultron.workings.myntra_spf import sjit_master
    work = tmp_path / "work"
    (work / "sjit" / "MAIN").mkdir(parents=True)
    (work / "sjit" / "MAIN" / "r.csv").write_text(
        HEAD + f"C1,11,Return,Ret Created,{_day(70)},\n" + f"C2,12,Return,Ret Created,{_day(30)},\n", encoding="utf-8")
    sjit = {"MAIN": [{"ticketId": 501, "factCoreId": "C9", "issueCategory": tickets.SJIT_NOT_SETTLED,
                      "status": "PAYMENT_COMPLETED", "createdOn": "2026-10-01T10:00:00", "compensationAmount": 450}]}
    out = {"MAIN": {"reasons": {"C1": "", "C2": tickets.SJIT_YOUNG},
                    "results": {"C1": {"result": tickets.SJIT_RAISED, "stock": "SHIPPED", "job": 99,
                                       "checked": f"{TODAY:%d-%b-%Y} 10:30"}}}}
    previous = {("MAIN", "C9"): {"ACCOUNT": "MAIN", "FACT CORE ITEM ID": "C9", "ORDER LINE ID": "19",
                                 "RETURN / RTO DATE": "2026-08-01", "BOT RESULT": tickets.SJIT_RAISED}}
    dest = work / sjit_master.SJIT_MASTER
    summary = sjit_master.build(work, TODAY, sjit, out, previous, dest)
    items = {r["FACT CORE ITEM ID"]: r for r in pl.read_excel(dest, sheet_name="ITEMS", infer_schema_length=0)
             .iter_rows(named=True)}
    assert items["C1"]["BOT RESULT"] == tickets.SJIT_RAISED and items["C1"]["BOT JOB"] == "99"
    assert items["C2"]["BOT RESULT"] == tickets.SJIT_YOUNG
    assert items["C9"]["CLAIM STATUS"] == "PAYMENT_COMPLETED" and items["C9"]["TICKET ID"] == "501"
    assert summary["MAIN"]["ITEMS"] == 3 and summary["MAIN"]["PAID"] == 1 and summary["MAIN"]["AMOUNT PAID"] == 450
    assert summary["MAIN"]["RAISED TODAY"] == 1
    again = sjit_master.read_previous(dest)
    assert set(again) == {("MAIN", "C1"), ("MAIN", "C2"), ("MAIN", "C9")}
