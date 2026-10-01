import unittest
from dataclasses import replace
from unittest.mock import patch

from epic_adapter.readiness import check_readiness
from test_computer_use import settings


class ReadinessTests(unittest.TestCase):
    def test_authenticated_url_prefix_distinguishes_login_page(self):
        config = settings()
        with patch("epic_adapter.readiness._cdp_get") as get:
            get.side_effect = [
                {"Browser": "Edge"},
                [{
                    "type": "page",
                    "url": "https://epic.example.invalid/login",
                }],
            ]
            checks = check_readiness(config)
        self.assertEqual("ready", checks["browser"].status)
        self.assertEqual("not_ready", checks["epic_login"].status)

    def test_configured_chart_prefix_is_ready(self):
        config = replace(
            settings(),
            epic_ready_url_prefix="https://epic.example.invalid/chart",
        )
        with patch("epic_adapter.readiness._cdp_get") as get:
            get.side_effect = [
                {"Browser": "Edge"},
                [{
                    "type": "page",
                    "url": "https://epic.example.invalid/chart/patient",
                }],
            ]
            checks = check_readiness(config)
        self.assertEqual("ready", checks["epic_login"].status)

    def test_origin_wide_prefix_still_rejects_sign_in_pages(self):
        config = replace(settings(), epic_ready_url_prefix="https://epic.example.invalid")
        for url, expected in (
            ("https://epic.example.invalid/cartella/login?", "not_ready"),
            ("https://epic.example.invalid/cartella/logout?timeout=1", "not_ready"),
            ("https://epic.example.invalid/cartella/pazienti", "ready"),
        ):
            with self.subTest(url=url), patch("epic_adapter.readiness._cdp_get") as get:
                get.side_effect = [{"Browser": "Edge"}, [{"type": "page", "url": url}]]
                checks = check_readiness(config)
                self.assertEqual(expected, checks["epic_login"].status)


if __name__ == "__main__":
    unittest.main()
