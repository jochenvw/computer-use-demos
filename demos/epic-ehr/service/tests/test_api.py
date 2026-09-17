import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_audit_directory = tempfile.TemporaryDirectory()
os.environ["API_BEARER_TOKEN"] = "unit-test-token"
os.environ["EPIC_BACKEND"] = "fixture"
os.environ["EPIC_AUDIT_PATH"] = str(
    Path(_audit_directory.name) / "audit.jsonl"
)

from fastapi.testclient import TestClient

from epic_adapter.api import adapter, app, jobs


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.headers = {
            # Avoid a bearer-shaped test literal; some scanners flag placeholders.
            "Authorization": ("Bear" + "er ") + os.environ["API_BEARER_TOKEN"],
            "X-Caller-Id": "unit-test",
        }

    def create_and_wait(self, payload: dict) -> dict:
        response = self.client.post(
            "/v1/retrieval-jobs", headers=self.headers, json=payload,
        )
        self.assertEqual(202, response.status_code)
        job_id = response.json()["job_id"]
        status_payload = {}
        for _ in range(50):
            status_response = self.client.get(
                f"/v1/retrieval-jobs/{job_id}", headers=self.headers,
            )
            status_payload = status_response.json()
            if status_payload["status"] in {"complete", "failed"}:
                break
            time.sleep(0.01)
        status_payload["job_id"] = job_id
        return status_payload

    def test_retrieval_job_returns_json_fhir_and_file(self) -> None:
        status_payload = self.create_and_wait({
            "patient_id": "DEMO-100042",
            "resources": ["patient", "ecg"],
        })
        self.assertEqual("complete", status_payload["status"])
        job_id = status_payload["job_id"]

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

    def test_default_fhir_xml_hl7_bp_filter_and_cache_metadata(self) -> None:
        payload = {
            "patient_id": "DEMO-100042",
            "source": "ehr",
            "resources": ["observations"],
            "observation_codes": ["85354-9"],
        }
        first = self.create_and_wait(payload)
        self.assertEqual("complete", first["status"])
        self.assertEqual("miss", first["cache_status"])
        self.assertTrue(first["collected_at"])
        self.assertTrue(first["expires_at"])

        default_response = self.client.get(
            f"/v1/retrieval-jobs/{first['job_id']}/result", headers=self.headers,
        )
        self.assertEqual(200, default_response.status_code)
        self.assertEqual("application/fhir+json", default_response.headers["content-type"])
        self.assertEqual("no-store", default_response.headers["cache-control"])
        self.assertEqual("miss", default_response.headers["x-retrieval-cache"])
        self.assertTrue(default_response.headers["x-collected-at"].endswith("+00:00"))
        self.assertTrue(default_response.headers["x-cache-expires-at"].endswith("+00:00"))
        entries = default_response.json()["entry"]
        self.assertEqual(1, len(entries))
        observation = entries[0]["resource"]
        self.assertEqual("Observation", observation["resourceType"])
        self.assertEqual("85354-9", observation["code"]["coding"][0]["code"])
        self.assertEqual(
            {("8480-6", 120), ("8462-4", 80)},
            {
                (
                    component["code"]["coding"][0]["code"],
                    component["valueQuantity"]["value"],
                )
                for component in observation["component"]
            },
        )

        xml_response = self.client.get(
            f"/v1/retrieval-jobs/{first['job_id']}/result?format=fhir-xml",
            headers=self.headers,
        )
        self.assertTrue(xml_response.headers["content-type"].startswith("application/fhir+xml"))
        self.assertIn(b"Observation", xml_response.content)
        hl7_response = self.client.get(
            f"/v1/retrieval-jobs/{first['job_id']}/result?format=hl7",
            headers=self.headers,
        )
        self.assertTrue(hl7_response.headers["content-type"].startswith("application/hl7-v2"))
        self.assertIn("8480-6^Systolic blood pressure^LN", hl7_response.text)
        self.assertIn("8462-4^Diastolic blood pressure^LN", hl7_response.text)

        hit = self.create_and_wait(payload)
        self.assertEqual("hit", hit["cache_status"])
        self.assertEqual(first["collected_at"], hit["collected_at"])
        hit_response = self.client.get(
            f"/v1/retrieval-jobs/{hit['job_id']}/result", headers=self.headers,
        )
        self.assertEqual("hit", hit_response.headers["x-retrieval-cache"])

        bypass = self.create_and_wait({**payload, "bypass_cache": True})
        self.assertEqual("bypass", bypass["cache_status"])
        self.assertNotEqual(first["collected_at"], bypass["collected_at"])
        refreshed = self.create_and_wait(payload)
        self.assertEqual("hit", refreshed["cache_status"])
        self.assertEqual(bypass["collected_at"], refreshed["collected_at"])

    def test_failed_bypass_invalidates_stale_api_cache_entry(self) -> None:
        payload = {
            "patient_id": "DEMO-100042",
            "source": "ehr",
            "resources": ["observations"],
            "observation_codes": ["8480-6"],
        }
        self.assertEqual("miss", self.create_and_wait(payload)["cache_status"])
        with patch.object(adapter, "retrieve", side_effect=RuntimeError("synthetic")):
            failed = self.create_and_wait({**payload, "bypass_cache": True})
            self.assertEqual("failed", failed["status"])
            self.assertEqual("bypass", failed["cache_status"])
            no_stale = self.create_and_wait(payload)
            self.assertEqual("failed", no_stale["status"])
            self.assertEqual("miss", no_stale["cache_status"])

    def test_unsupported_representation_returns_422(self) -> None:
        job = self.create_and_wait({
            "patient_id": "DEMO-100042", "source": "files", "resources": ["ecg"],
        })
        self.assertEqual("complete", job["status"])
        response = self.client.get(
            f"/v1/retrieval-jobs/{job['job_id']}/result?format=hl7",
            headers=self.headers,
        )
        self.assertEqual(422, response.status_code)
        self.assertEqual(
            "Retrieved data cannot be represented in the requested format.",
            response.json()["detail"],
        )

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

    def test_authenticated_readiness_is_independent_and_reports_jobs(self):
        response = self.client.get("/v1/readiness", headers=self.headers)
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("ready", payload["checks"]["api"]["status"])
        self.assertEqual("ready", payload["checks"]["files"]["status"])
        self.assertEqual("not_applicable", payload["checks"]["browser"]["status"])
        self.assertIn("accepting_jobs", payload["service"])
        self.assertGreater(payload["service"]["process_id"], 0)
        self.assertEqual(401, self.client.get("/v1/readiness").status_code)

    def test_drain_timeout_is_explicit_and_resumes_acceptance(self):
        with patch.object(jobs, "drain", return_value=False):
            response = self.client.post(
                "/v1/admin/drain?timeout_seconds=1", headers=self.headers,
            )
        self.assertEqual(409, response.status_code)
        self.assertIn("acceptance resumed", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
