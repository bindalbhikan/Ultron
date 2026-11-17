"""WhatsApp alerts never stop a run and never log the key."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ultron.integrations import whatsapp

SET_UP = {"CALLMEBOT_PHONE": "+910000000000", "CALLMEBOT_APIKEY": "test-key"}


class Send(unittest.TestCase):
    def test_not_set_up_sends_nothing(self):
        with mock.patch.dict(os.environ, {"CALLMEBOT_PHONE": "", "CALLMEBOT_APIKEY": ""}), \
             mock.patch("ultron.core.http.get") as get:
            self.assertFalse(whatsapp.send("hello"))
        get.assert_not_called()

    def test_sends_and_cuts_a_long_message(self):
        answer = mock.Mock(status_code=200, text="Message queued.")
        with mock.patch.dict(os.environ, SET_UP), mock.patch("ultron.core.http.get", return_value=answer) as get:
            self.assertTrue(whatsapp.send("x" * 5000))
        sent = get.call_args.kwargs["params"]["text"]
        self.assertLessEqual(len(sent), whatsapp.MAX_LEN)
        self.assertTrue(sent.endswith("(see Telegram)"))

    def test_network_failure_is_false_and_hides_the_key(self):
        with mock.patch.dict(os.environ, SET_UP), \
             mock.patch("ultron.core.http.get", side_effect=httpx.ConnectError("url apikey=test-key")), \
             self.assertLogs("ultron", "WARNING") as logs:
            self.assertFalse(whatsapp.send("hello"))
        self.assertNotIn("test-key", "".join(logs.output))

    def test_refused_key_is_false(self):
        answer = mock.Mock(text="APIKey is invalid", status_code=200)
        with mock.patch.dict(os.environ, SET_UP), mock.patch("ultron.core.http.get", return_value=answer):
            self.assertFalse(whatsapp.send("hello"))


if __name__ == "__main__":
    unittest.main()
