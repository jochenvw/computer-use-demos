import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

from epic_adapter.synthetic_portal import Handler


class SyntheticPortalTests(unittest.TestCase):
    def test_portal_is_ready_and_contains_uitslagen_scenario(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(
                f"http://127.0.0.1:{server.server_port}/healthz"
            ) as response:
                self.assertEqual(b'{"status":"ok"}', response.read())
            with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
                page = response.read().decode()
            self.assertIn("SYNTHETIC TRAINING DATA", page)
            self.assertIn("REQUESTED SYNTHETIC PATIENT", page)
            self.assertIn("Patient ID: DEMO-100042", page)
            self.assertIn("DEMO-100042", page)
            self.assertIn("Uitslagen", page)
            self.assertIn("Bloedonderzoek", page)
            self.assertIn("Hemoglobine", page)
            self.assertNotIn("innerHTML", page)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
