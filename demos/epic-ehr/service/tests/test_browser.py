import unittest
from unittest.mock import Mock

from epic_adapter.browser import BrowserSession, origin_of
from test_computer_use import settings


class BrowserGuardTests(unittest.TestCase):
    def setUp(self):
        self.session = BrowserSession(settings())
        self.page = Mock()
        self.page.url = "https://epic.example.invalid/chart"
        self.page.is_closed.return_value = False
        self.page.evaluate.return_value = {"width": 1000, "height": 700}
        self.session._page = self.page

    def test_off_origin_tab_is_rejected(self):
        self.page.url = "https://other.invalid"
        with self.assertRaises(RuntimeError):
            self.session.execute("click", {"x": 10, "y": 10})
        self.page.mouse.click.assert_not_called()

    def test_off_viewport_click_is_rejected(self):
        with self.assertRaises(ValueError):
            self.session.execute("click", {"x": -1, "y": 10})

    def test_shortcuts_are_rejected(self):
        with self.assertRaises(ValueError):
            self.session.execute("press_key", {"key": "Control+L"})

    def test_cross_origin_navigation_is_blocked(self):
        route = Mock()
        route.request.is_navigation_request.return_value = True
        route.request.url = "https://epic.example.invalid.attacker.test/chart"
        self.session._guard_navigation(route)
        route.abort.assert_called_once()
        route.continue_.assert_not_called()

    def test_screenshot_uses_css_pixels(self):
        self.page.screenshot.return_value = b"synthetic"
        self.assertTrue(self.session.screenshot().startswith("data:image/jpeg;base64,"))
        self.assertEqual("css", self.page.screenshot.call_args.kwargs["scale"])

    def test_origin_includes_nonstandard_port(self):
        self.assertEqual("https://example.invalid:8443", origin_of("https://example.invalid:8443/chart"))
