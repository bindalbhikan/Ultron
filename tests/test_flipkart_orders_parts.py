"""A short Flipkart Orders file is asked for again in parts."""
import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ultron.workings.portal_monthly import pipeline as p

FIRST, LAST = date(2026, 10, 1), date(2026, 10, 31)


def lines(*rows):
    return pd.DataFrame(rows, columns=["order_item_id", "order_date"])


class Parts(unittest.TestCase):
    def test_parts_cover_the_month_without_a_gap(self):
        parts = p.month_parts(FIRST, LAST)
        self.assertEqual(parts[0][0], FIRST)
        self.assertEqual(parts[-1][1], LAST)
        self.assertTrue(all((b[0] - a[1]).days == 1 for a, b in zip(parts, parts[1:])))
        self.assertTrue(all((b - a).days < 11 for a, b in parts))

    def test_merge_adds_the_lost_day_once_and_stays_in_the_month(self):
        month = lines(("a", "2026-10-30 10:00:00"))
        parts = [lines(("a", "2026-10-30 10:00:00"), ("b", "2026-10-31 11:00:00")),
                 lines(("b", "2026-10-31 11:00:00"), ("c", "2026-11-01 09:00:00"))]
        merged = p.merge_order_parts(month, parts, FIRST, LAST)
        self.assertEqual(list(merged["order_item_id"]), ["a", "b"])

    def test_month_file_is_kept_when_parts_hold_fewer(self):
        month = lines(("a", "2026-10-29 10:00:00"), ("b", "2026-10-30 10:00:00"))
        merged = p.merge_order_parts(month, [lines(("a", "2026-10-29 10:00:00"))], FIRST, LAST)
        self.assertEqual(len(merged), 2)


if __name__ == "__main__":
    unittest.main()
