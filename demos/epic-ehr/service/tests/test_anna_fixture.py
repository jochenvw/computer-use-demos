import json
import re
import unittest
from pathlib import Path

from epic_adapter.adapters.fixture import FixtureEpicAdapter
from epic_adapter.formats import fhir_bundle, omop_json
from epic_adapter.models import ClinicalBundle, ResourceType
from epic_adapter.synthetic_emr import ANNA_ID, PATIENTS, STUDIES

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"


class AnnaFixtureTests(unittest.TestCase):
    def setUp(self):
        self.adapter = FixtureEpicAdapter(FIXTURES)
        self.resources = self.adapter.retrieve(ANNA_ID, list(ResourceType))

    def by_type(self, kind):
        return [item for item in self.resources if item.resource_type == kind]

    def test_identity_matches_the_story(self):
        [patient] = self.by_type(ResourceType.patient)
        self.assertEqual("TUS-2026-0417", patient.source_id)
        self.assertEqual([{"family": "Ricci", "given": ["Anna"]}], patient.data["name"])
        self.assertEqual(("female", "1971-03-14"),
                         (patient.data["gender"], patient.data["birthDate"]))
        [encounter] = self.by_type(ResourceType.encounters)
        self.assertTrue(encounter.data["period"]["start"].startswith("2026-09-18"))
        self.assertIn("UMC Utrecht",
                      encounter.data["hospitalization"]["dischargeDisposition"]["text"])

    def test_every_resource_belongs_to_anna(self):
        for item in self.resources:
            if item.resource_type != ResourceType.patient:
                self.assertEqual("Patient/TUS-2026-0417", item.data["subject"]["reference"])
            self.assertEqual("synthetic-fixture", item.provenance.source)

    def test_fixture_values_match_the_synthetic_emr(self):
        labs = {
            (coding["code"], item.data["valueQuantity"]["value"])
            for item in self.by_type(ResourceType.observations)
            if "valueQuantity" in item.data
            for coding in item.data["code"]["coding"]
        }
        self.assertLessEqual({("718-7", 8.1), ("718-7", 10.2), ("2039-6", 18.4),
                              ("24108-3", 41), ("2276-4", 6), ("8867-4", 104)}, labs)
        emr_values = {(test, value) for _, test, value, *_ in PATIENTS[ANNA_ID]["labs"]}
        self.assertLessEqual({("Emoglobina", "8.1"), ("CEA", "18.4"), ("CA 19-9", "41")},
                             emr_values)

    def test_imaging_is_preliminary_transcription_without_own_diagnosis(self):
        reports = self.by_type(ResourceType.imaging)
        self.assertEqual({"imaging-anna-mri", "imaging-anna-ct"},
                         {item.source_id for item in reports})
        for report in reports:
            self.assertEqual("preliminary", report.data["status"])
            self.assertTrue(report.data["conclusion"].endswith(
                "Preliminary: transcribed by AI, verify against source."))
            accession = report.data["identifier"][0]["value"]
            self.assertEqual(ANNA_ID, STUDIES[accession]["patient"])
        mri = next(item for item in reports if item.source_id == "imaging-anna-mri")
        self.assertIn("segment VII 22 mm", mri.data["conclusion"])
        bundle = ClinicalBundle(patient_id=ANNA_ID, resources=reports, files=[])
        entries = fhir_bundle(bundle, "/x")["entry"]
        self.assertEqual({"DiagnosticReport"}, {e["resource"]["resourceType"] for e in entries})
        self.assertEqual(2, len(omop_json(bundle)["tables"]["note"]))

    def test_no_legacy_or_real_person_data_in_fixtures(self):
        text = "\n".join(path.read_text(encoding="utf-8")
                         for path in FIXTURES.rglob("*") if path.is_file())
        for banned in ("DEMO-100042", "Rivera", "Jamie", "1984-05-17", "Bianchi"):
            self.assertNotIn(banned, text)
        self.assertIsNone(re.search(r"\b63\b", text))
        self.assertEqual(["TUS-2026-0417.json"],
                         sorted(path.name for path in (FIXTURES / "patients").iterdir()))
        json.loads((FIXTURES / "patients" / "TUS-2026-0417.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
