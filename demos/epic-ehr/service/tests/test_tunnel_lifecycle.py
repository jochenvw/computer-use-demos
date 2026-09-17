import socket
import unittest
from unittest.mock import Mock

from epic_adapter.console import ensure_port_available, stop_child


class TunnelLifecycleTests(unittest.TestCase):
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
