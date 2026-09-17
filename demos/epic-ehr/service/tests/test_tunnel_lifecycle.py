import io
import socket
import unittest
from unittest.mock import MagicMock, Mock, patch

from rich.panel import Panel

from epic_adapter.console import (
    ensure_port_available, forwarded_tunnel_url, run_with_tunnel, stop_child,
)


class TunnelLifecycleTests(unittest.TestCase):
    def test_only_requested_forwarded_port_url_is_selected(self):
        api_url = "https://example-8000.euw.devtunnels.ms"
        self.assertIsNone(forwarded_tunnel_url(
            "Inspect network activity: https://example.euw.devtunnels.ms", 8000,
        ))
        self.assertIsNone(forwarded_tunnel_url(
            "https://example-9000.euw.devtunnels.ms", 8000,
        ))
        self.assertIsNone(forwarded_tunnel_url(api_url + ".evil.example", 8000))
        self.assertEqual(api_url, forwarded_tunnel_url(
            f"Inspect: https://example.euw.devtunnels.ms Connect: {api_url}", 8000,
        ))
        self.assertEqual(api_url + ":443", forwarded_tunnel_url(api_url + ":443/", 8000))

    def test_launcher_does_not_print_inspector_url_as_api_url(self):
        api, tunnel = Mock(), Mock()
        api.poll.return_value = None
        tunnel.poll.return_value = None
        api_url = "https://example-8000.euw.devtunnels.ms"
        tunnel.stdout = io.StringIO(
            "Inspect network activity: https://example.euw.devtunnels.ms\n"
            f"Connect via browser: {api_url}\n"
        )
        health = MagicMock()
        health.__enter__.return_value.status = 200
        console = Mock()
        with (
            patch("epic_adapter.console.shutil.which", return_value="devtunnel"),
            patch("epic_adapter.console.ensure_port_available"),
            patch("epic_adapter.console.subprocess.Popen", side_effect=[api, tunnel]),
            patch("epic_adapter.console.urlopen", return_value=health),
            patch("epic_adapter.console.stop_child"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Dev tunnel exited"):
                run_with_tunnel(console, 8000)
        panels = [
            call.args[0] for call in console.print.call_args_list
            if isinstance(call.args[0], Panel)
        ]
        self.assertEqual(1, len(panels))
        self.assertEqual(api_url, panels[0].renderable)

    def test_occupied_port_is_rejected(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            with self.assertRaisesRegex(RuntimeError, "already in use"):
                ensure_port_available(occupied.getsockname()[1])

    def test_owned_child_is_terminated_and_killed_after_timeout(self):
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [__import__("subprocess").TimeoutExpired("child", 10), None]
        stop_child(child)
        child.terminate.assert_called_once()
        child.kill.assert_called_once()
