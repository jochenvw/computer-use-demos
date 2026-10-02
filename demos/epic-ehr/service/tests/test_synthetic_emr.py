import re
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

from epic_adapter import synthetic_emr
from epic_adapter.synthetic_emr import SYNTHETIC_NOTICE, Handler
from epic_adapter.synthetic_portal import Handler as ShimHandler

ANNA = "TUS-2026-0417"


class SyntheticEmrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def get(self, path):
        with urlopen(self.base + path) as response:
            return response.status, dict(response.headers), response.read().decode()

    def assert_clean(self, page):
        self.assertIn(SYNTHETIC_NOTICE, page)
        self.assertNotIn("SYNTHETIC TRAINING DATA", page)
        self.assertNotIn('class="synthetic"', page)
        for banned in ("Epic", "MyChart", "Mijn Dossier", "portal", "Portal", "fax",
                       "<script", "innerHTML", "http://", "https://"):
            self.assertFalse(banned in page, banned)

    def test_shim_and_health(self):
        self.assertIs(ShimHandler, Handler)
        status, headers, body = self.get("/healthz")
        self.assertEqual((200, '{"status":"ok"}'), (status, body))

    def test_worklist_lists_several_patients_with_constant_title(self):
        status, headers, page = self.get("/")
        self.assertEqual(200, status)
        self.assert_clean(page)
        self.assertIn("<title>Ospedale di Montalcino - Postazione clinica</title>", page)
        self.assertIn("SanitaCartella", page)
        self.assertIn("Lista di lavoro", page)
        self.assertGreaterEqual(page.count('href="/paziente/'), 5)
        self.assertIn("RICCI, Anna", page)
        self.assertIn("RICCI, Antonio", page)
        self.assertIn('href="/pacs"', page)
        csp = headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertNotIn("script-src", csp)
        self.assertEqual("nosniff", headers["X-Content-Type-Options"])
        self.assertEqual("no-store", headers["Cache-Control"])

    def test_search_by_name_and_id_and_escapes_query(self):
        _, _, page = self.get("/?q=ricci")
        self.assertIn("RICCI, Anna", page)
        self.assertIn("RICCI, Antonio", page)
        self.assertNotIn("CONTI", page)
        _, _, page = self.get("/?q=" + quote("Anna Ricci"))
        self.assertIn("RICCI, Anna", page)
        self.assertNotIn("RICCI, Antonio", page)
        _, _, page = self.get("/?q=" + ANNA)
        self.assertIn("(1 pazienti)", page)
        _, _, page = self.get("/?q=" + quote("<b>x"))
        self.assertIn("&lt;b&gt;x", page)
        self.assertIn("Nessun paziente trovato", page)

    def test_anna_chart_views_and_tabs(self):
        _, _, onc = self.get(f"/paziente/{ANNA}")
        self.assert_clean(onc)
        for text in ("RICCI, ANNA", "14/03/1971", "55 anni", "Chirurgia Generale",
                     "UMC Utrecht", "Vista Oncologia - quadro oncologico",
                     "Adenocarcinoma del sigma", "cT3 cN1 M1", "153.3"):
            self.assertIn(text, onc)
        _, _, sur = self.get(f"/paziente/{ANNA}?vista=chirurgia")
        self.assertIn("Vista Chirurgia - valutazione chirurgica", sur)
        self.assertIn("ASA II", sur)
        self.assertIn("120/80", sur)
        self.assertNotIn("quadro oncologico", sur)
        _, _, labs = self.get(f"/paziente/{ANNA}?scheda=esami")
        for text in ("Emoglobina", "8.1", "10.2", "Ferritina", "CEA", "18.4", "CA 19-9"):
            self.assertIn(text, labs)
        _, _, notes = self.get(f"/paziente/{ANNA}?scheda=note")
        self.assertIn("Lettera di trasferimento", notes)
        self.assertIn("Verbale Pronto Soccorso", notes)
        _, _, imaging = self.get(f"/paziente/{ANNA}?scheda=imaging")
        self.assertIn('href="/pacs/studio/MTL-26-08817"', imaging)
        self.assertIn("RM fegato", imaging)

    def test_other_patient_has_no_oncology_story(self):
        _, _, page = self.get("/paziente/TUS-2026-0419")
        self.assertIn("RICCI, ANTONIO", page)
        self.assertNotIn("Adenocarcinoma", page)
        self.assertIn("Nessun percorso oncologico attivo", page)

    def test_pacs_list_viewer_and_report(self):
        _, _, studies = self.get("/pacs?q=" + ANNA)
        self.assert_clean(studies)
        self.assertIn("MontalcinoPACS", studies)
        self.assertIn("RM fegato", studies)
        self.assertNotIn("RX torace", studies)
        _, _, view = self.get("/pacs/studio/MTL-26-08817?serie=2&img=6")
        self.assert_clean(view)
        for text in ("Referto", "segmento VII", "22 x 19 mm", "14 mm",
                     "compatibili con localizzazioni secondarie",
                     "Dott.ssa Elena Fabbri", "immagine 6/12",
                     '/pacs/img/MTL-26-08817/2/6.svg'):
            self.assertIn(text, view)
        _, _, clamped = self.get("/pacs/studio/MTL-26-08817?serie=9&img=abc")
        self.assertIn("immagine 6/12", clamped)

    def test_synthetic_mri_slices(self):
        status, headers, svg = self.get("/pacs/img/MTL-26-08817/2/6.svg")
        self.assertEqual(200, status)
        self.assertEqual("image/svg+xml", headers["Content-Type"])
        self.assertIn("SYNTHETIC PHANTOM - NOT A REAL SCAN", svg)
        self.assertIn("RICCI^ANNA", svg)
        self.assertNotIn("<script", svg)
        self.assertIn('stroke="#e6e6e6"', svg)  # rim-enhancing lesion, T1 post
        _, _, no_lesion = self.get("/pacs/img/MTL-26-08817/1/12.svg")
        self.assertEqual(0, len(re.findall(r"<circle[^>]*r=\"1[0-6]\.\d\"", no_lesion)))
        self.assertEqual(synthetic_emr.synthetic_image("MTL-26-08817", 1, 6),
                         synthetic_emr.synthetic_image("MTL-26-08817", 1, 6))

    def test_unknown_routes_return_404(self):
        for path in ("/paziente/TUS-0000", "/pacs/studio/NOPE", "/pacs/img/MTL-26-08817/1/99.svg",
                     "/pacs/img/MTL-26-08817/x/1.svg", "/login", "/admin"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                urlopen(self.base + path)
            self.assertEqual(404, caught.exception.code)
            caught.exception.close()

    def test_no_route_looks_signed_out(self):
        for patient in synthetic_emr.PATIENTS:
            for marker in ("login", "logout", "timeout"):
                self.assertNotIn(marker, patient.lower())


if __name__ == "__main__":
    unittest.main()
