import json
import os
import tempfile
import time
import unittest
from pathlib import Path

_audit_directory = tempfile.TemporaryDirectory()
os.environ["API_BEARER_TOKEN"] = "unit-test-token"
os.environ["EPIC_BACKEND"] = "fixture"
os.environ["EPIC_AUDIT_PATH"] = str(
    Path(_audit_directory.name) / "audit.jsonl"
)

from fastapi.testclient import TestClient

from epic_adapter.api import app


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.headers = {
            "Authorization": "Bearer unit-test-token",
            "X-Caller-Id": "unit-test",
        }

    def test_retrieval_job_returns_json_fhir_and_file(self) -> None:
        response = self.client.post(
            "/v1/retrieval-jobs",
            headers=self.headers,
            json={
                "patient_id": "DEMO-100042",
                "resources": ["patient", "ecg"],
            },
        )
        self.assertEqual(202, response.status_code)
        job_id = response.json()["job_id"]

        status_payload = {}
        for _ in range(50):
            status_response = self.client.get(
                f"/v1/retrieval-jobs/{job_id}", headers=self.headers
            )
            status_payload = status_response.json()
            if status_payload["status"] in {"complete", "failed"}:
                break
            time.sleep(0.01)
        self.assertEqual("complete", status_payload["status"])

        json_response = self.client.get(
            f"/v1/retrieval-jobs/{job_id}/result?format=json",
            headers=self.headers,
        )
        self.assertEqual(200, json_response.status_code)
        self.assertEqual("DEMO-100042", json_response.json()["patient_id"])
        self.assertEqual(1, len(json_response.json()["files"]))

        fhir_response = self.client.get(
            f"/v1/retrieval-jobs/{job_id}/result?format=fhir",
            headers=self.headers,
        )
        self.assertEqual("application/fhir+json", fhir_response.headers["content-type"])
        self.assertEqual("Bundle", fhir_response.json()["resourceType"])

        file_url = json_response.json()["files"][0]["url"]
        file_response = self.client.get(file_url, headers=self.headers)
        self.assertEqual(200, file_response.status_code)
        self.assertIn(b"SyntheticEcg", file_response.content)

        audit_text = Path(os.environ["EPIC_AUDIT_PATH"]).read_text(
            encoding="utf-8"
        )
        self.assertNotIn("DEMO-100042", audit_text)
        for line in audit_text.splitlines():
            json.loads(line)

    def test_rejects_missing_bearer_token(self) -> None:
        response = self.client.post(
            "/v1/retrieval-jobs",
            json={"patient_id": "DEMO-100042"},
        )
        self.assertEqual(401, response.status_code)

    def test_rejects_unsafe_patient_identifier_before_any_work(self):
        response = self.client.post(
            "/v1/retrieval-jobs", headers=self.headers,
            json={"patient_id": "..\\secret", "source": "files"},
        )
        self.assertEqual(422, response.status_code)

    def test_unknown_source_is_rejected(self):
        response = self.client.post(
            "/v1/retrieval-jobs", headers=self.headers,
            json={"patient_id": "DEMO-100042", "source": "desktop"},
        )
        self.assertEqual(422, response.status_code)

    def test_health_does_not_expose_backend(self):
        self.assertEqual({"status": "ok"}, self.client.get("/healthz").json())


if __name__ == "__main__":
    unittest.main()
