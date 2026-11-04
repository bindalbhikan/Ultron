"""Live colour-group classification, including asymmetric product responses."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ultron.workings.myntra_grouping import engine as e


class ColourGroupingTests(unittest.TestCase):
    def rows(self, links, skus=None):
        skus = skus or {sid: f"SKU-{sid}" for sid in links}
        styles = pd.DataFrame([
            {"account": "test", "style_id": sid, "brand": "Test", "article": "Dresses",
             "my_sku": skus[sid], "status": "Active"}
            for sid in links
        ])
        cache = {sid: {"live": True, "colours": [{"styleId": other} for other in others]}
                 for sid, others in links.items()}
        return e.build_account_rows("test", [("Dresses", list(dict.fromkeys(skus.values())))],
                                    styles, {"final": {}, "style": {}}, {}, None, cache)

    def test_asymmetric_group_members_are_done(self):
        rows = self.rows({"1": ["2"], "2": ["1"], "3": ["1", "2"]})
        self.assertEqual([r["GROUPING REMARK"] for r in rows], [e.REMARK_DONE] * 3)
        self.assertEqual(e.pending_group_styles(rows), {})
        # Preserve the raw per-page evidence even when the group membership is confirmed.
        self.assertEqual(rows[0]["PORTAL GROUP"], "1, 2")

    def test_ungrouped_style_stays_pending(self):
        rows = self.rows({"1": ["2"], "2": ["1"], "3": []})
        self.assertEqual([r["GROUPING REMARK"] for r in rows],
                         [e.REMARK_DONE, e.REMARK_DONE, e.REMARK_NOT_DONE])

    def test_member_with_empty_own_list_is_done_when_partner_lists_it(self):
        rows = self.rows({"1": [], "2": ["1"]})
        self.assertEqual([r["GROUPING REMARK"] for r in rows], [e.REMARK_DONE] * 2)
        self.assertEqual(e.pending_group_styles(rows), {})

    def test_two_empty_lists_remain_pending(self):
        rows = self.rows({"1": [], "2": []})
        self.assertEqual([r["GROUPING REMARK"] for r in rows], [e.REMARK_NOT_DONE] * 2)

    def test_separate_smaller_group_stays_pending(self):
        rows = self.rows({"1": ["2", "3"], "2": ["1", "3"], "3": ["1", "2"],
                          "4": ["5"], "5": ["4"]})
        self.assertEqual([r["GROUPING REMARK"] for r in rows],
                         [e.REMARK_DONE] * 3 + [e.REMARK_NOT_DONE] * 2)

    def test_ungrouped_duplicate_is_not_marked_done(self):
        rows = self.rows({"1": ["2"], "2": ["1"], "3": []},
                         {"1": "A", "2": "B", "3": "A"})
        remarks = {str(r["Style ID"]): r["GROUPING REMARK"] for r in rows}
        self.assertEqual(remarks["3"], e.REMARK_DUPLICATE)

    def test_extra_style_keeps_remove_flag(self):
        rows = self.rows({"1": ["2", "9"], "2": ["1", "9"]})
        extra = next(r for r in rows if str(r["Style ID"]) == "9")
        self.assertEqual(extra["GROUPING REMARK"], e.REMARK_EXTRA)
        self.assertEqual(extra["ACTION"], "REMOVE")


if __name__ == "__main__":
    unittest.main()
