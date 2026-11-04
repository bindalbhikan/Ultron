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

    def test_overlapping_colour_lists_form_one_group(self):
        rows = self.rows({"1": ["2"], "2": ["3"], "3": ["4"], "4": []})
        self.assertEqual([r["GROUPING REMARK"] for r in rows], [e.REMARK_DONE] * 4)

    def test_shared_external_partner_confirms_group(self):
        rows = self.rows({"1": ["9"], "2": ["9"]})
        actual = {str(r["Style ID"]): r["GROUPING REMARK"] for r in rows}
        self.assertEqual(actual, {"1": e.REMARK_DONE, "2": e.REMARK_DONE, "9": e.REMARK_EXTRA})

    def test_two_complete_groups_with_alternative_styles_are_done(self):
        rows = self.rows({"1": ["2"], "2": [], "3": ["4"], "4": []},
                         {"1": "A", "2": "B", "3": "A", "4": "B"})
        self.assertEqual([r["GROUPING REMARK"] for r in rows], [e.REMARK_DONE] * 4)

    def test_template_uses_connected_group_without_false_ungroup_flag(self):
        rows = self.rows({"1": ["2"], "2": ["3"], "3": [], "4": []})
        pending = e.pending_group_styles(rows)
        self.assertEqual(len(pending['001']['style_ids']), 2)
        self.assertIn(4, pending['001']['style_ids'])
        self.assertFalse(any(r['REMARK'] for r in rows))

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
