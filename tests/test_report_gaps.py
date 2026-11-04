"""Missing sources are named, never shown as a low figure or a wrong state."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ultron.workings.business_report import pipeline as bp
from ultron.workings.myntra_grouping import engine as e
from ultron.workings.myntra_grouping import pipeline as gp


class NoAnswerStyle(unittest.TestCase):
    def rows(self, cache):
        styles = pd.DataFrame([{"account": "t", "style_id": s, "brand": "B", "article": "Dresses",
                                "my_sku": f"SKU-{s}", "status": "Active"} for s in ("1", "2")])
        return e.build_account_rows("t", [("Dresses", ["SKU-1", "SKU-2"])], styles,
                                    {"final": {}, "style": {}}, {}, None, cache)

    def test_no_answer_is_not_not_live(self):
        rows = self.rows({"1": {"http": 200, "live": True, "colours": []}})
        self.assertEqual(rows[1]["GROUPING REMARK"], e.REMARK_NO_ANSWER)
        self.assertEqual(rows[1]["ACTION"], "CHECK")
        self.assertIn(e.REMARK_NO_ANSWER, e.TEMPLATE_SKIP_REMARKS)

    def test_404_stays_not_live(self):
        rows = self.rows({"1": {"http": 200, "live": True, "colours": []},
                          "2": {"http": 404, "live": False, "colours": []}})
        self.assertEqual(rows[1]["GROUPING REMARK"], e.REMARK_NOT_LIVE)


class SalesMonths(unittest.TestCase):
    def test_month_without_an_account_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            sale = Path(tmp) / "o.csv"
            pd.DataFrame({"seller id": ["19170"], "style id": ["5"], "order status": ["C"],
                          "order line id": ["a"]}).to_csv(sale, index=False)
            loads = {date(2026, 10, 1): [sale], date(2026, 9, 1): []}
            with mock.patch.object(gp.pr, "load", side_effect=lambda _p, m, _k, _d: loads[m]), \
                 mock.patch.object(gp, "date", wraps=date) as today:
                today.today.return_value = date(2026, 11, 1)
                counts, missing = gp.sales_counts({}, Path(tmp), 2, ["19170", "32207"])
        self.assertEqual(counts, {("19170", "5"): 1})
        self.assertEqual(missing, ["Oct-26 (DBCC)", "Sep-26 (MAIN, DBCC)"])


class MyntraReports(unittest.TestCase):
    def test_gaps_per_account(self):
        files = [{"kind": "ORDER", "account": a, "month": date(2026, m, 1)}
                 for a in ("MAIN", "DBCC", "FMCC") for m in (8, 9, 10)]
        files = [f for f in files if not (f["account"] == "DBCC" and f["month"].month == 9)]
        files += [{"kind": "RETURN", "account": a, "month": date(2026, 10, 1)} for a in ("MAIN", "DBCC")]
        self.assertEqual(bp.missing_myntra_reports(files, date(2026, 10, 1)),
                         ["DBCC ORDER: Sep-26", "FMCC RETURN: none"])

    def test_late_start_is_not_a_gap_and_last_month_is(self):
        files = [{"kind": k, "account": a, "month": date(2026, 9, 1)}
                 for k in ("ORDER", "RETURN") for a in ("MAIN", "DBCC", "FMCC")]
        self.assertEqual(bp.missing_myntra_reports(files, date(2026, 9, 1)), [])
        self.assertEqual(len(bp.missing_myntra_reports(files, date(2026, 10, 1))), 6)


if __name__ == "__main__":
    unittest.main()
