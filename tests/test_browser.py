"""The browser's safety checks. No browser or network is needed: host lookups are replaced."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ultron.core import browser
from ultron.tools import browser as browser_tool


def resolves_to(address):
    return mock.patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", (address, 0))])


class CheckUrl(unittest.TestCase):
    def setUp(self):
        browser._is_public_host.cache_clear()

    def test_public_address_passes(self):
        with resolves_to("93.184.216.34"):
            self.assertEqual(browser.check_url(" https://example.com/a "), "https://example.com/a")

    def test_private_and_metadata_addresses_are_refused(self):
        for address in ("192.168.0.101", "10.0.0.1", "127.0.0.1", "169.254.169.254", "::1"):
            browser._is_public_host.cache_clear()
            with resolves_to(address), self.assertRaises(browser.BrowserError):
                browser.check_url("http://some-host/")

    def test_other_schemes_are_refused(self):
        for url in ("file:///C:/secret.txt", "chrome://settings", "javascript:alert(1)", "example.com"):
            with self.assertRaises(browser.BrowserError):
                browser.check_url(url)

    def test_unknown_host_is_refused(self):
        with mock.patch("socket.getaddrinfo", side_effect=OSError), self.assertRaises(browser.BrowserError):
            browser.check_url("https://no-such-host.example/")


class Challenge(unittest.TestCase):
    def test_short_page_with_words_or_frame(self):
        self.assertTrue(browser.is_challenge("Please verify you are human", []))
        self.assertTrue(browser.is_challenge("", ["https://www.google.com/recaptcha/api2/anchor"]))
        self.assertTrue(browser.is_challenge("Loading", ["https://challenges.cloudflare.com/x"]))

    def test_full_page_is_not_a_challenge(self):
        long_text = "An article about what a captcha is. " * 100
        self.assertFalse(browser.is_challenge(long_text, ["https://www.google.com/recaptcha/api2/anchor"]))

    def test_plain_short_page_is_not_a_challenge(self):
        self.assertFalse(browser.is_challenge("Example Domain", ["https://example.com/"]))


class Tool(unittest.TestCase):
    PAGE = {"url": "https://example.com/", "title": "Example", "text": "x" * 6001, "links": [("Home", "https://example.com/h")]}

    def test_long_page_comes_in_parts(self):
        with mock.patch.object(browser, "read_page", return_value=self.PAGE):
            self.assertIn("Part 1 of 2", browser_tool.browser_read("https://example.com/"))
            second = browser_tool.browser_read("https://example.com/", part=2)
        self.assertTrue(second.endswith("---\nx"))

    def test_part_out_of_range_is_an_error(self):
        with mock.patch.object(browser, "read_page", return_value=self.PAGE):
            self.assertTrue(browser_tool.browser_read("https://example.com/", part=3).startswith("Error:"))

    def test_links_only_when_asked(self):
        with mock.patch.object(browser, "read_page", return_value=self.PAGE):
            self.assertNotIn("Home", browser_tool.browser_read("https://example.com/"))
            self.assertIn("Home: https://example.com/h", browser_tool.browser_read("https://example.com/", links=True))

    def test_failed_page_is_named_not_shown_empty(self):
        with mock.patch.object(browser, "read_page", side_effect=browser.BrowserError("x shows a CAPTCHA")):
            self.assertEqual(browser_tool.browser_read("https://x.example/"), "Error: x shows a CAPTCHA")


if __name__ == "__main__":
    unittest.main()
