"""Myntra grouping: the master split into one file per brand, in the master's layout."""
import sys
import tempfile
import unittest
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ultron.workings.myntra_grouping import submit as sb


class BrandWiseTests(unittest.TestCase):
    def test_one_file_per_brand(self):
        tmp = Path(tempfile.mkdtemp())
        rows = {"ACC-19170": [("001", "Fashfun", 11, "DONE"), ("002", "Murcia", 12, "NOT DONE"), ("003", "Other", 13, "DONE")],
                "ACC-35426": [("001", "Fashfun", 21, "NOT DONE"), ("001", "Fashfun", 22, "NOT DONE")]}
        from ultron.workings.myntra_grouping.engine import write_tables
        sheets = []
        for title, values in rows.items():
            out = []
            for uid, brand, sid, remark in values:
                row = dict.fromkeys(sb.LAYOUT)
                row.update({"Unique ID": uid, "Brand": brand, "Style ID": sid, "GROUPING REMARK": remark})
                out.append([row[c] for c in sb.LAYOUT])
            sheets.append((title, sb.LAYOUT, out))
        subs = []
        for seller, brand, styles in (("35426", "Fashfun", "21, 22"), ("19170", "", "12")):   # the 2nd: by hand
            row = dict.fromkeys(sb.COLS, "")
            row.update({"SELLER ID": seller, "BRAND": brand, "STYLE IDS": styles})
            subs.append([row[c] for c in sb.COLS])
        sheets.append(("SUBMISSIONS", sb.COLS, subs))
        master = tmp / "MYNTRA GROUPING MASTER.xlsx"
        write_tables(master, sheets)

        book = pl.read_excel(sb.brand_master(master, tmp / "out"), sheet_id=0, engine="calamine")
        self.assertEqual(list(book), ["Fashfun", "Murcia", "Summary", "SUBMISSIONS"])   # "Other" is not a brand
        self.assertEqual(book["Fashfun"].columns, ["ACCOUNT", *sb.LAYOUT])
        self.assertEqual(book["Fashfun"]["ACCOUNT"].to_list(), ["MAIN", "FMCC", "FMCC"])
        summary = book["Summary"].filter((pl.col("Brand") == "Fashfun") & (pl.col("Account") == "FMCC"))
        self.assertEqual(summary["NOT DONE"].item(), 2)
        self.assertEqual(book["SUBMISSIONS"]["BRANDS"].to_list(), ["Fashfun", "Murcia"])   # the 2nd from its style

    def test_again_sends_rejected_but_not_waiting(self):
        from datetime import date
        jobs = [{"seller": "19170", "styles": {"1", "2"}, "status": "REJECTED", "day": "2026-11-05"},
                {"seller": "19170", "styles": {"3", "4"}, "status": "IN_PROGRESS", "day": "2026-11-05"}]
        today = date(2026, 11, 6)
        self.assertTrue(sb.skip_reason("19170", ["1", "2"], jobs, today))
        self.assertEqual(sb.skip_reason("19170", ["1", "2"], jobs, today, again=True), "")
        self.assertEqual(sb.skip_reason("19170", ["3", "4"], jobs, today, again=True), "waiting on Myntra")

if __name__ == "__main__":
    unittest.main()
