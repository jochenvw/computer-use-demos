import json
from pathlib import Path
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from epic_adapter.tester import MAX_RESPONSE_BYTES, fixed_path, make_handler, request_upstream, upstream_origin


class TesterTests(unittest.TestCase):
    def test_packaged_ui_has_required_safe_request_mapping(self):
        page = (Path(__file__).parents[1] / "src/epic_adapter/static/tester.html").read_text()
        self.assertIn('let csrf="CSRF_TOKEN"', page)
        self.assertIn("bypass_cache", page)
        self.assertIn('$("format").value', page)
        self.assertIn("textContent", page)
        self.assertNotIn("innerHTML", page)

    def test_only_permitted_tunnel_origins_and_fixed_paths(self):
        self.assertEqual("https://demo.devtunnels.ms", upstream_origin("https://demo.devtunnels.ms/"))
        for value in ("http://demo.devtunnels.ms", "https://evil.example", "https://user@x.devtunnels.ms", "https://x.devtunnels.ms/no"):
            with self.assertRaises(ValueError):
                upstream_origin(value)
        self.assertEqual("/v1/retrieval-jobs/" + "a" * 32 + "/result?format=hl7", fixed_path("result", "a" * 32, output_format="hl7"))
        with self.assertRaises(ValueError):
            fixed_path("status", "../etc")

    def test_upstream_does_not_follow_redirects_or_exceed_limit(self):
        class Upstream(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "https://example.invalid/")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"x" * (MAX_RESPONSE_BYTES + 1))

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            status, _, _ = request_upstream(origin, "/redirect", "token", "", None)
            self.assertEqual(302, status)
            with self.assertRaisesRegex(ValueError, "2 MiB"):
                request_upstream(origin, "/large", "token", "", None)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_relay_rejects_missing_csrf_and_host(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("csrf", True))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/jobs", data=b"{}",
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(403, error.exception.code)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
