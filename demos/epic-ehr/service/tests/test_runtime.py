"""Loopback-only smoke checks. No Epic, model, or tunnel connection is made."""

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import Request, urlopen

from epic_adapter.browser import BrowserSession
from epic_adapter.config import Settings


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(url, process):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Child process exited before startup.")
        try:
            with urlopen(url, timeout=1) as response:
                return json.load(response)
        except (URLError, TimeoutError):
            time.sleep(0.1)
    raise RuntimeError("Child process did not become responsive.")


class RuntimeTests(unittest.TestCase):
    def test_console_serves_authenticated_file_retrieval_over_http(self):
        port = free_port()
        token = secrets.token_urlsafe(32)
        with tempfile.TemporaryDirectory() as directory:
            env = {
                **os.environ, "EPIC_BACKEND": "fixture", "API_BEARER_TOKEN": token,
                "EPIC_AUDIT_PATH": str(Path(directory) / "audit.jsonl"),
            }
            process = subprocess.Popen(
                [sys.executable, "-m", "epic_adapter.console", "--port", str(port)],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                base = f"http://127.0.0.1:{port}"
                self.assertEqual({"status": "ok"}, wait_for(base + "/healthz", process))
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                with urlopen(Request(
                    base + "/v1/retrieval-jobs",
                    data=json.dumps({"patient_id": "DEMO-100042", "source": "files"}).encode(),
                    headers=headers,
                ), timeout=5) as response:
                    self.assertEqual(202, response.status)
                    job = json.load(response)
                for _ in range(100):
                    with urlopen(Request(base + job["status_url"], headers=headers), timeout=5) as response:
                        status = json.load(response)["status"]
                    if status in {"complete", "failed"}:
                        break
                    time.sleep(0.01)
                self.assertEqual("complete", status)
                with urlopen(Request(base + job["result_url"], headers=headers), timeout=5) as response:
                    result = json.load(response)
                self.assertEqual([], result["resources"])
                self.assertEqual(1, len(result["files"]))
            finally:
                process.terminate()
                process.wait(timeout=10)

    @unittest.skipUnless(sys.platform == "win32", "Smoke test uses installed Microsoft Edge.")
    def test_browser_attaches_and_controls_only_synthetic_tab(self):
        edge = Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe"
        self.assertTrue(edge.is_file(), "Install Edge to run the real browser smoke test.")

        class PageHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                page = b'<html><title>Synthetic chart</title><input aria-label="Patient search"><button onclick="document.title=\'Clicked\'">Search</button></html>'
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(page)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), PageHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = free_port()
        origin = f"http://127.0.0.1:{server.server_port}"
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen([
                str(edge), "--headless=new", "--no-first-run",
                f"--user-data-dir={directory}", f"--remote-debugging-port={port}",
                "--remote-debugging-address=127.0.0.1",
                origin,
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                wait_for(f"http://127.0.0.1:{port}/json/version", process)
                # Production Settings.validate rejects HTTP; this test connects only to loopback.
                config = replace(
                    Settings.from_env(), epic_origin=origin,
                    browser_cdp_url=f"http://127.0.0.1:{port}", browser_window_title="",
                )
                with BrowserSession(config) as browser:
                    self.assertTrue(browser.screenshot().startswith("data:image/jpeg;base64,"))
                    browser.execute("click", {"x": 30, "y": 18})
                    browser.execute("type_text", {"text": "DEMO-100042"})
                    self.assertEqual("DEMO-100042", browser._page.locator("input").input_value())
                    browser.execute("press_key", {"key": "Tab"})
                    browser.execute("press_key", {"key": "Enter"})
                    self.assertEqual("Clicked", browser._page.title())
                    browser._page.context.browser.close()
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
