from pathlib import Path
import threading
import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from epic_adapter.tester import (
    MAX_RESPONSE_BYTES, _ExclusiveServer, fixed_path, make_handler,
    packaged_skill_instructions, request_upstream, upstream_origin,
)


class TesterTests(unittest.TestCase):
    def test_second_tester_cannot_share_an_occupied_port(self):
        first = _ExclusiveServer(("127.0.0.1", 0), make_handler("csrf", True))
        try:
            with self.assertRaises(OSError):
                _ExclusiveServer(first.server_address, make_handler("csrf", True))
        finally:
            first.server_close()

    def test_stage_mode_is_presenter_ready(self):
        page = (Path(__file__).parents[1] / "src/epic_adapter/static/tester.html").read_text()
        for marker in ('id="pipeline"', 'id="nowStep"', 'id="formatChips"', 'id="stageToggle"',
                       'id="detailsToggle"', 'id="receiveGrid"', 'get("mode") === "stage"', "html.compact"):
            self.assertIn(marker, page)
        launcher = (Path(__file__).parents[2] / "start-demo.ps1").read_text(encoding="utf-8")
        self.assertIn("-Stage", launcher)

    def test_custom_schema_defaults_to_editable_snomed_example(self):
        import html
        import re
        page = (Path(__file__).parents[1] / "src/epic_adapter/static/tester.html").read_text()
        match = re.search(r'<textarea id="schema"[^>]*>(.*?)</textarea>', page, re.S)
        self.assertIsNotNone(match)
        self.assertNotIn("readonly", match.group(0).split(">")[0])
        schema = json.loads(html.unescape(match.group(1)))
        self.assertIn("SNOMED CT", schema["standard"])
        self.assertIn("never invent codes", schema["rules"])
        for sctid in ("441689006", "60267001", "40939009", "241622002"):
            self.assertIn(sctid, schema["exampleConcepts"])

    def test_packaged_ui_has_required_safe_request_mapping(self):
        page = (Path(__file__).parents[1] / "src/epic_adapter/static/tester.html").read_text()
        self.assertIn('let csrf="CSRF_TOKEN"', page)
        self.assertIn("bypass_cache", page)
        self.assertIn("TUNNEL_URL_DEFAULT", page)
        self.assertIn("Uses protected local token when blank", page)
        self.assertIn("<b>1 &#xB7; Clinical data from the EMR</b>", page)
        self.assertIn("<b>2 &#xB7; Medical imaging from PACS</b>", page)
        self.assertIn("<b>3 &#xB7; Local Italian database</b>", page)
        self.assertLess(page.index('id="emrScenario"'), page.index('id="pacsScenario"'))
        self.assertLess(page.index('id="pacsScenario"'), page.index('id="sqlScenario"'))
        self.assertIn("<title>Data Retrieval Agent - Ospedale di Montalcino</title>", page)
        self.assertIn("maps it to the requested data standard", page)
        self.assertIn('"Retrieve all relevant medical information for patient Anna Ricci."', page)
        self.assertIn('id="ask"', page)
        self.assertIn('id="handover"', page)
        self.assertIn("MDT dashboard, UMC Utrecht", page)
        for banned in ("portal", "Portal", "Epic", "MyChart", "Mijn Dossier", "fax", "Fax",
                       "SELF", "assets", "Uitslagen"):
            self.assertNotIn(banned, page)
        self.assertIn('class="case"', page)
        self.assertIn("Record for the Dutch MDT", page)
        self.assertIn("renderTimeline(b.timeline)", page)
        self.assertIn("Instruction sent to the agent", page)
        self.assertIn("SKILL_TEXT_DEFAULTS", page)
        self.assertIn("showSkill(source)", page)
        self.assertIn("--cp-chrome:", page)
        self.assertIn("DEMO WORKSPACES", page)
        self.assertIn("Human review required", page)
        self.assertIn('class="context-banner"', page)
        self.assertNotIn("linear-gradient", page)
        self.assertTrue(page.isascii())
        self.assertIn('$("emrScenario").onclick', page)
        self.assertIn('$("pacsScenario").onclick', page)
        self.assertIn('$("sqlScenario").onclick', page)
        self.assertIn('<option value="omop">OMOP CDM JSON</option>', page)
        self.assertIn('$("format").value', page)
        self.assertIn("textContent", page)
        self.assertNotIn("innerHTML", page)

    def test_tester_embeds_the_exact_packaged_text_skills(self):
        skills = packaged_skill_instructions()
        self.assertEqual(
            {"emr-browser", "pacs-viewer", "local-files", "sql-desktop"}, set(skills)
        )
        self.assertIn("Clinician EMR", skills["emr-browser"])
        self.assertIn("Preliminary: transcribed by AI, verify against source.", skills["pacs-viewer"])
        self.assertIn("INFORMATION_SCHEMA", skills["sql-desktop"])
        self.assertIn("ECG", skills["local-files"])
        for text in skills.values():
            # Generic manuals: no patient, path, table or vendor hints.
            for banned in ("TUS-2026-0417", "Anna", "Ricci", "oncologia_demo", "OncologiaDemo",
                           "esame_laboratorio", "SanitaCartella", "Montalcino", "Desktop",
                           "assets", "ecg.jpg", "Epic", "portal", "Uitslagen", "SELF", " 63"):
                self.assertNotIn(banned, text)

    def test_only_permitted_tunnel_origins_and_fixed_paths(self):
        self.assertEqual("https://demo.devtunnels.ms", upstream_origin("https://demo.devtunnels.ms/"))
        self.assertEqual("https://demo.devtunnels.ms", upstream_origin("https://demo.devtunnels.ms:443"))
        for value in ("http://demo.devtunnels.ms", "https://evil.example", "https://user@x.devtunnels.ms", "https://x.devtunnels.ms/no"):
            with self.assertRaises(ValueError):
                upstream_origin(value)
        self.assertEqual("/v1/retrieval-jobs/" + "a" * 32 + "/result?format=hl7", fixed_path("result", "a" * 32, output_format="hl7"))
        self.assertEqual("/v1/retrieval-jobs/" + "a" * 32 + "/result?format=omop", fixed_path("result", "a" * 32, output_format="omop"))
        self.assertEqual("/v1/retrieval-jobs/" + "a" * 32 + "/transform", fixed_path("transform", "a" * 32))
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

    def test_relay_uses_configured_defaults_without_exposing_tokens(self):
        observed = {}

        class Upstream(BaseHTTPRequestHandler):
            def do_POST(self):
                observed["authorization"] = self.headers.get("Authorization")
                observed["tunnel"] = self.headers.get("X-Tunnel-Authorization")
                observed["body"] = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"job_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')

            def log_message(self, *args):
                pass

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        defaults = {
            "tunnel_url": f"http://127.0.0.1:{upstream.server_port}",
            "bearer_token": "stored-api-token",
            "tunnel_token": "stored-tunnel-token",
        }
        relay = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler("csrf", True, defaults)
        )
        threads = [
            threading.Thread(target=server.serve_forever, daemon=True)
            for server in (upstream, relay)
        ]
        for thread in threads:
            thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{relay.server_port}") as response:
                page = response.read().decode()
            with urlopen(
                f"http://127.0.0.1:{relay.server_port}/?scoutTheme=dark"
            ) as response:
                themed_page = response.read().decode()
            self.assertIn(defaults["tunnel_url"], page)
            self.assertEqual(page, themed_page)
            self.assertNotIn("stored-api-token", page)
            self.assertNotIn("stored-tunnel-token", page)
            request = Request(
                f"http://127.0.0.1:{relay.server_port}/api/jobs",
                data=json.dumps({
                    "tunnel_url": "",
                    "bearer_token": "",
                    "tunnel_token": "",
                    "request": {
                        "patient_id": "TUS-2026-0417",
                        "source": "ehr",
                        "resources": ["observations"],
                    },
                }).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-CSRF-Token": "csrf",
                },
                method="POST",
            )
            with urlopen(request) as response:
                self.assertEqual(200, response.status)
            self.assertEqual("Bearer stored-api-token", observed["authorization"])
            self.assertEqual(
                "tunnel stored-tunnel-token", observed["tunnel"]
            )
            self.assertEqual("TUS-2026-0417", observed["body"]["patient_id"])
        finally:
            for server, thread in zip((upstream, relay), threads):
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

    def test_relay_rejects_empty_request_body(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("csrf", True))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/jobs", data=b"",
                headers={"Content-Type": "application/json", "X-CSRF-Token": "csrf"}, method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual("Request body is required.", json.load(error.exception)["error"])
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
