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

        files = {f.name: pd.read_excel(f, sheet_name=None) for f in sb.brand_masters(master, tmp / "out")}
        self.assertEqual(len(files), 2)                    # "Other" is not one of the brands
        fashfun = files["MYNTRA GROUPING MASTER - Fashfun.xlsx"]
        murcia = files["MYNTRA GROUPING MASTER - Murcia.xlsx"]
        self.assertEqual(list(fashfun), ["ACC-19170", "ACC-35426", "Summary", "SUBMISSIONS"])
        self.assertEqual(list(murcia), ["ACC-19170", "Summary", "SUBMISSIONS"])
        self.assertEqual(list(fashfun["ACC-35426"].columns), sb.LAYOUT)
        self.assertEqual(fashfun["Summary"].set_index("Account").loc[35426, "NOT DONE"], 2)
        self.assertEqual(len(fashfun["SUBMISSIONS"]), 1)
        self.assertEqual(len(murcia["SUBMISSIONS"]), 1)   # brand taken from its style


if __name__ == "__main__":
    unittest.main()
