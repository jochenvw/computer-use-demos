from pathlib import Path
import threading
import json
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
        self.assertEqual("https://demo.devtunnels.ms", upstream_origin("https://demo.devtunnels.ms:443"))
        for value in ("http://demo.devtunnels.ms", "https://evil.example", "https://user@x.devtunnels.ms", "https://x.devtunnels.ms/no"):
            with self.assertRaises(ValueError):
                upstream_origin(value)
        self.assertEqual("/v1/retrieval-jobs/" + "a" * 32 + "/result?format=hl7", fixed_path("result", "a" * 32, output_format="hl7"))
        with self.assertRaises(ValueError):
            fixed_path("status", "../etc")

    def test_upstream_does_not_follow_redirects_or_exceed_limit(self):
        auth = []
        class Upstream(BaseHTTPRequestHandler):
            def do_GET(self):
                auth.append(self.headers.get("Authorization"))
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
            with self.assertRaisesRegex(ValueError, "redirected"):
                request_upstream(origin, "/redirect", "token", "", None)
            self.assertEqual("Bearer" + " token", auth[0])
            with self.assertRaisesRegex(ValueError, "2 MiB"):
                request_upstream(origin, "/large", "token", "", None)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_relay_rejects_missing_csrf_and_invalid_host(self):
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
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/jobs", data=b"{}",
                headers={"Content-Type": "application/json", "Host": "evil.example", "X-CSRF-Token": "csrf"}, method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(403, error.exception.code)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_relay_downloads_exact_bytes_and_returns_errors_as_json(self):
        requested = []
        class Upstream(BaseHTTPRequestHandler):
            def do_GET(self):
                requested.append(self.path)
                if self.path.endswith("/" + "b" * 32):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.end_headers()
                    self.wfile.write(b"\x00download-bytes")
                else:
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b"denied")

            def log_message(self, *args):
                pass

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        relay = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("csrf", True))
        threads = [threading.Thread(target=x.serve_forever, daemon=True) for x in (upstream, relay)]
        for thread in threads:
            thread.start()
        body = {"tunnel_url": f"http://127.0.0.1:{upstream.server_port}", "bearer_token": "test", "job_id": "a" * 32, "file_id": "b" * 32}
        try:
            request = Request(
                f"http://127.0.0.1:{relay.server_port}/api/file", data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf"}, method="POST",
            )
            with urlopen(request) as response:
                self.assertEqual(b"\x00download-bytes", response.read())
            self.assertEqual([f"/v1/retrieval-jobs/{'a' * 32}/files/{'b' * 32}"], requested)
            body["file_id"] = "invalid"
            request = Request(
                f"http://127.0.0.1:{relay.server_port}/api/file", data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf"}, method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual("Invalid file identifier.", json.load(error.exception)["error"])
        finally:
            for server, thread in zip((upstream, relay), threads):
                server.shutdown()
                thread.join()
                server.server_close()

    def test_relay_rejects_non_object_and_credential_newlines(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("csrf", True))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for body, expected in (([], "Request body must be a JSON object."), ({"tunnel_url": "http://127.0.0.1:1", "bearer_token": "bad\nvalue"}, "API bearer token contains invalid characters.")):
                request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/jobs", data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf"}, method="POST",
                )
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(expected, json.load(error.exception)["error"])
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
