import json
import re
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from epic_adapter.adapters.fixture import FixtureEpicAdapter
from epic_adapter.config import Settings
from epic_adapter.file_catalog import FileCatalog
from epic_adapter.formats import fhir_bundle, normalized_json
from epic_adapter.models import ClinicalBundle, ResourceType
from epic_adapter.tester import make_handler


@unittest.skipUnless(sys.platform == "win32", "Uses an isolated installed Edge browser.")
class TesterBrowserTests(unittest.TestCase):
    def test_presets_pending_cancel_fhir_and_original_download(self):
        from playwright.sync_api import expect, sync_playwright

        config = Settings.from_env()
        bundle = ClinicalBundle(
            patient_id="TUS-2026-0417",
            resources=FixtureEpicAdapter(config.fixture_root).retrieve(
                "TUS-2026-0417", [ResourceType.observations, ResourceType.ecg],
            ),
            files=FileCatalog((config.fixture_root / "files",)).find("TUS-2026-0417"),
        )
        requests = []
        downloads = []
        queued = threading.Event()
        status_seen = threading.Event()
        queued.set()
        job_id = "a" * 32
        base = f"/v1/retrieval-jobs/{job_id}"

        class Upstream(BaseHTTPRequestHandler):
            def send(self, body, media_type="application/json"):
                self.send_response(200)
                self.send_header("Content-Type", media_type)
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(payload)
                self.send(json.dumps({"job_id": job_id, "status": "queued"}).encode())

            def do_GET(self):
                path = urlsplit(self.path)
                if path.path == base:
                    status_seen.set()
                    self.send(json.dumps({
                        "job_id": job_id, "status": "queued" if queued.is_set() else "complete",
                        "cache_status": "bypass" if requests[-1]["bypass_cache"] else "miss",
                    }).encode())
                elif path.path == base + "/result":
                    output_format = parse_qs(path.query).get("format", ["fhir"])[0]
                    payload = normalized_json(bundle, base) if output_format == "json" else fhir_bundle(bundle, base)
                    self.send(json.dumps(payload).encode())
                elif path.path == f"{base}/files/{bundle.files[0].file_id}":
                    downloads.append(path.path)
                    self.send(Path(bundle.files[0].path).read_bytes(), bundle.files[0].media_type)
                else:
                    self.send_error(404)

            def log_message(self, *args):
                pass

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        tester = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("browser-test-csrf", True))
        threads = []
        for server in (upstream, tester):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                try:
                    page = browser.new_page(
                        accept_downloads=True, viewport={"width": 1440, "height": 900}
                    )
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{tester.server_port}")
                    page.locator("#stageToggle").click()
                    expect(page.locator("html")).to_have_class(
                        re.compile(r"\bstage\b")
                    )
                    expect(page.locator("#montalcinoHospital")).to_be_visible()
                    expect(page.locator(".context-banner")).to_be_hidden()
                    expect(page.locator("#pipeline")).to_be_hidden()
                    expect(page.locator("#live")).to_be_hidden()
                    page.locator("#stageToggle").click()
                    expect(page.locator("#scenarios")).to_be_hidden()
                    expect(page.locator("#emrScenario")).to_be_disabled()
                    expect(page.locator("#sanVittoreHospital")).to_be_disabled()
                    expect(page.locator("#santaLuciaHospital")).to_be_disabled()
                    page.keyboard.press("1")
                    self.assertEqual([], requests)
                    page.locator("#montalcinoHospital").click()
                    expect(page.locator("#montalcinoHospital")).to_contain_text(
                        "Connecting"
                    )
                    expect(page.locator("#scenarios")).to_be_visible()
                    expect(page.locator("#hospitals")).to_be_hidden()
                    expect(page.locator(".context-banner")).to_be_visible()
                    expect(page.locator("#pipeline")).to_be_visible()
                    expect(page.locator("#live")).to_be_visible()
                    expect(page.locator("#connectedHospital")).to_contain_text(
                        "Connected to Ospedale di Montalcino"
                    )
                    expect(page.locator("#emrScenario")).to_be_enabled()
                    page.locator("details:not(#skillPanel)").evaluate(
                        "element => element.open = true"
                    )
                    page.locator("#url").fill(f"http://127.0.0.1:{upstream.server_port}")
                    page.locator("#bearer").fill("synthetic-test-token")
                    page.locator("#emrScenario").click()
                    expect(page.locator("#skillName")).to_have_text("emr-browser")
                    expect(page.locator("#skillText")).to_contain_text("Clinician EMR")
                    expect(page.locator("#connectedHospital")).to_be_visible()
                    expect(page.locator("#emrScenario")).to_be_disabled()
                    self.assertTrue(status_seen.wait(8))
                    expect(page.locator("#ask")).to_have_value(
                        "Retrieve all relevant medical information for patient Anna Ricci."
                    )
                    page.wait_for_timeout(1200)
                    expect(page.locator("#emrScenario")).to_be_disabled()
                    expect(page.locator("#pacsScenario")).to_be_disabled()
                    expect(page.locator("#sqlScenario")).to_be_disabled()
                    self.assertNotIn("observation_codes", requests[-1])
                    self.assertTrue(requests[-1]["bypass_cache"])
                    self.assertEqual("TUS-2026-0417", requests[-1]["patient_id"])
                    self.assertEqual(
                        "Retrieve all relevant medical information for patient Anna Ricci.",
                        requests[-1]["instruction"],
                    )
                    page.locator("#cancel").click()
                    expect(page.locator("#state")).to_have_text("Cancelled")
                    expect(page.locator("#emrScenario")).to_be_enabled()
                    expect(page.locator("#handover")).to_be_hidden()

                    queued.clear()
                    page.locator("#codes").fill("")
                    page.locator("#submit").click()
                    expect(page.locator("#state")).to_have_text("Complete")
                    self.assertNotIn("observation_codes", requests[-1])
                    expect(page.locator("#output")).to_contain_text('"resourceType": "Bundle"')
                    expect(page.locator("#output")).to_contain_text('"value": 120')
                    expect(page.locator("#meta")).to_contain_text('"cache_status": "bypass"')
                    expect(page.locator("#handover")).to_contain_text(
                        "MDT dashboard, UMC Utrecht, as FHIR R4 JSON"
                    )
                    page.locator("#source").select_option("pacs")
                    expect(page.locator("#skillName")).to_have_text("pacs-viewer")

                    page.locator("#source").select_option("files")
                    expect(page.locator("#skillName")).to_have_text("local-files")
                    expect(page.locator("#skillText")).to_contain_text(
                        "Approved local files"
                    )
                    page.locator("#resources").select_option(["ecg"])
                    page.locator("#format").select_option("json")
                    page.locator("#submit").click()
                    expect(page.locator("#state")).to_have_text("Complete")
                    self.assertEqual("files", requests[-1]["source"])
                    self.assertEqual(["ecg"], requests[-1]["resources"])
                    with page.expect_download() as download:
                        page.locator("#files a").click()
                    self.assertEqual(Path(bundle.files[0].path).read_bytes(), Path(download.value.path()).read_bytes())
                    self.assertEqual(1, len(downloads))
                    expect(page.locator("#handover")).to_contain_text("as Normalized JSON")
                    page.locator("#clear").click()
                    expect(page.locator("#bearer")).to_have_value("")
                    expect(page.locator("#url")).to_have_value("")
                    expect(page.locator("#state")).to_have_text("Idle")
                    expect(page.locator("#files a")).to_have_count(0)
                    self.assertEqual([], errors)
                finally:
                    browser.close()
        finally:
            for server in (tester, upstream):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=5)
