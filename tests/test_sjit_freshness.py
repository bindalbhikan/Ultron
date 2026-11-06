"""SJIT: a Seller_Orders_Report built from Myntra's old data copy must not count a day it holds in part."""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ultron.workings.portals import myntra as mp
from ultron.workings.sale import sjit

HEAD = "po_type,order line id,created on,order status,cancelled on,packed on\n"


def report(*rows):
    return (HEAD + "".join(",".join(r) + "\n" for r in rows)).encode()


# asked for on 6 Nov at 07:01: its data copy ran to 5 Nov 03:30
STALE = report(("FBM", "1", "2026-11-04 10:00:00", "C", "", ""),
               ("FBM", "2", "2026-11-05 01:00:00", "C", "", "2026-11-05 03:30:00"))
# asked for on 6 Nov at 09:36: its data copy ran to 6 Nov 03:30
FRESH = report(("FBM", "1", "2026-11-04 10:00:00", "F", "2026-11-05 09:00:00", ""),
               ("FBM", "2", "2026-11-05 01:00:00", "C", "", ""),
               ("SJIT", "3", "2026-11-05 22:00:00", "C", "", "2026-11-06 03:30:00"),
               ("PPMP", "4", "2026-11-05 22:00:00", "C", "", ""))

NOV4, NOV5 = date(2026, 11, 4), date(2026, 11, 5)


def ms(text):
    return int(datetime.fromisoformat(text).timestamp() * 1000)


def job(jid, start, end, created):
    return {"id": jid, "reportId": mp.REPORT_ID, "status": "COMPLETED", "successFile": f"f{jid}.csv",
            "createdOn": ms(created), "queryParams": {**mp.QUERY, "reportStartDate": start, "reportEndDate": end}}


class FakePortal(mp.MyntraPortal):
    def __init__(self, jobs, files, new_file):
        self._jobs, self.files, self.new_file, self.asked = jobs, files, new_file, []

    def jobs(self, *_):
        return list(self._jobs)

    def download(self, j):
        return j["successFile"], self.files[j["id"]]

    def schedule(self, start, end, report_id=mp.REPORT_ID, cooldown_wait=0):
        self.asked.append((start, end))
        new = job(99, f"{start}", f"{end}", "2026-11-06 15:30:00")
        self.files[99] = self.new_file
        return new


class FreshnessTests(unittest.TestCase):
    def test_stamp(self):
        self.assertEqual(mp.data_through(mp.data_stamp(STALE.decode())), NOV4)
        self.assertEqual(mp.data_through(mp.data_stamp(FRESH.decode())), NOV5)

    def test_parse_leaves_out_a_day_held_in_part(self):
        gross, _, covered = sjit.parse([("stale.csv", STALE)])
        self.assertIn(NOV4, covered)
        self.assertNotIn(NOV5, covered)

    def test_parse_newest_data_wins_whatever_the_order(self):
        for files in ([("s.csv", STALE), ("f.csv", FRESH)], [("f.csv", FRESH), ("s.csv", STALE)]):
            gross, cancel, covered = sjit.parse(files)
            self.assertEqual((gross[NOV4], gross[NOV5]), (1, 2))  # FBM + SJIT, PPMP left out
            self.assertEqual(cancel[NOV5], 1)
            self.assertTrue({NOV4, NOV5} <= covered)

    def test_reports_asks_again_when_the_portal_report_is_stale(self):
        portal = FakePortal([job(1, "2026-11-04", "2026-11-05", "2026-11-06 07:01:00")], {1: STALE}, FRESH)
        files, covered = portal.reports([NOV4, NOV5], wait_minutes=0, poll_seconds=0)
        self.assertEqual(portal.asked, [(NOV5, NOV5)])
        self.assertEqual(covered, {NOV4, NOV5})
        self.assertEqual(files[0][1], FRESH)  # newest data first


if __name__ == "__main__":
    unittest.main()
