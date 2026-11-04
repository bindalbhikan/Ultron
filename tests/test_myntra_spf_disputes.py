"""Which rejected Myntra SPF claims are disputed, and how."""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ultron.workings.myntra_spf import tickets
from ultron.workings.myntra_spf import pipeline

TODAY = date(2026, 11, 20)
ROW = {"STATUS": "REJECT", "REASON": "Not_Eligible_delivered_via_OTC", "LAST UPDATED": "02-Nov-2026 15:54", "TICKET ID": "1"}
OPEN_RETURN = {"status": "DELIVERED", "RETURN POD": ""}


class Due(unittest.TestCase):
    def due(self, row=None, master=OPEN_RETURN, final="", worked=True):
        with mock.patch.object(pipeline, "final_status", return_value=final), \
             mock.patch.object(pipeline, "not_worked", return_value=not worked):
            return tickets.dispute_due({**ROW, **(row or {})}, master, TODAY)

    def test_rejected_and_not_received_is_due(self):
        self.assertTrue(self.due())

    def test_received_or_paid_is_left(self):
        self.assertFalse(self.due(final="Return Received"))
        self.assertFalse(self.due(final="SPF Paid"))

    def test_other_status_or_no_master_row_is_left(self):
        self.assertFalse(self.due({"STATUS": "AWAITING_AGENT_RESPONSE"}))
        self.assertFalse(self.due(master=None))

    def test_pod_sjit_and_replaced_tickets_are_left(self):
        self.assertFalse(self.due(master={"RETURN POD": "YES"}))
        self.assertFalse(self.due(worked=False))
        self.assertFalse(self.due({"REASON": "Rejected due to new NON RBNR ticket creation (New ticket: 85)"}))

    def test_touched_lately_or_no_date_waits(self):
        self.assertFalse(self.due({"LAST UPDATED": "18-Nov-2026 10:00"}))
        self.assertFalse(self.due({"LAST UPDATED": ""}))


class Delayed(unittest.TestCase):
    ROW = {"CATEGORY": tickets.CATEGORY_NAME[tickets.DELAYED]}

    def due(self, created, flag):
        with mock.patch.object(pipeline, "final_status", return_value=""), \
             mock.patch.object(pipeline, "not_worked", return_value=False), \
             mock.patch.dict("os.environ", {"MYNTRA_SPF_DISPUTE_DELAYED": flag}):
            return tickets.dispute_due({**ROW, **self.ROW}, {"RETURN POD": "", "return_created_date": created}, TODAY)

    def test_any_age_once_switched_on(self):
        self.assertFalse(self.due(date(2026, 5, 1), ""))
        self.assertTrue(self.due(date(2026, 10, 1), "1"))
        self.assertTrue(self.due(date(2026, 5, 1), "1"))


class Open(unittest.TestCase):
    def test_off_only_counts(self):
        portal = mock.Mock()
        lines = tickets.open_disputes(portal, "MAIN", ["1", "2"], live=False)
        self.assertIn("2 due", lines[0])
        portal.spf_dispute.assert_not_called()

    def test_live_works_every_one_and_rechecks_the_status(self):
        portal = mock.Mock()
        portal.spf_claim.side_effect = [{"status": "REJECT"}, {"status": "OPEN"}, {"status": "REJECT"}]
        with mock.patch.object(tickets.time, "sleep"):
            lines = tickets.open_disputes(portal, "MAIN", ["1", "2", "3"], live=True)
        self.assertEqual(portal.spf_dispute.call_count, 2)
        self.assertEqual(portal.spf_claim.call_count, 3)
        self.assertIn("2 opened of 3 due", lines[0])

    def test_one_failure_does_not_stop_the_rest(self):
        portal = mock.Mock()
        portal.spf_claim.return_value = {"status": "REJECT"}
        portal.spf_dispute.side_effect = [RuntimeError("refused"), None]
        with mock.patch.object(tickets.time, "sleep"):
            lines = tickets.open_disputes(portal, "MAIN", ["1", "2"], live=True)
        self.assertIn("1 opened of 2 due, 1 failed", lines[0])


if __name__ == "__main__":
    unittest.main()
