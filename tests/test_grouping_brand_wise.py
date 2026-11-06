"""Myntra grouping: the master split into one file per brand, in the master's layout."""
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ultron.workings.myntra_grouping import submit as sb


class BrandWiseTests(unittest.TestCase):
    def test_one_file_per_brand(self):
        tmp = Path(tempfile.mkdtemp())
        wb = Workbook()
        wb.remove(wb.active)
        rows = {"ACC-19170": [("001", "Fashfun", 11, "DONE"), ("002", "Murcia", 12, "NOT DONE"), ("003", "Other", 13, "DONE")],
                "ACC-35426": [("001", "Fashfun", 21, "NOT DONE"), ("001", "Fashfun", 22, "NOT DONE")]}
        for title, values in rows.items():
            ws = wb.create_sheet(title)
            ws.append(sb.LAYOUT)
            for uid, brand, sid, remark in values:
                row = dict.fromkeys(sb.LAYOUT)
                row.update({"Unique ID": uid, "Brand": brand, "Style ID": sid, "GROUPING REMARK": remark})
                ws.append([row[c] for c in sb.LAYOUT])
        ws = wb.create_sheet("SUBMISSIONS")
        ws.append(sb.COLS)
        for seller, brand, styles in (("35426", "Fashfun", "21, 22"), ("19170", "", "12")):   # the 2nd: by hand
            row = dict.fromkeys(sb.COLS, "")
            row.update({"SELLER ID": seller, "BRAND": brand, "STYLE IDS": styles})
            ws.append([row[c] for c in sb.COLS])
        master = tmp / "MYNTRA GROUPING MASTER.xlsx"
        wb.save(master)

        book = pd.read_excel(sb.brand_master(master, tmp / "out"), sheet_name=None)
        self.assertEqual(list(book), ["Fashfun", "Murcia", "Summary", "SUBMISSIONS"])   # "Other" is not a brand
        self.assertEqual(list(book["Fashfun"].columns), ["ACCOUNT", *sb.LAYOUT])
        self.assertEqual(book["Fashfun"]["ACCOUNT"].tolist(), ["MAIN", "FMCC", "FMCC"])
        summary = book["Summary"].set_index(["Brand", "Account"])
        self.assertEqual(summary.loc[("Fashfun", "FMCC"), "NOT DONE"], 2)
        self.assertEqual(book["SUBMISSIONS"]["BRANDS"].tolist(), ["Fashfun", "Murcia"])   # the 2nd from its style

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
