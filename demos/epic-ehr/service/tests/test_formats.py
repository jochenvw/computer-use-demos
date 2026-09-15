import unittest

from epic_adapter.formats import fhir_bundle
from epic_adapter.models import (
    ClinicalBundle,
    ClinicalResource,
    ResourceType,
    SourceRecord,
)


class FhirFormatTests(unittest.TestCase):
    def test_patient_maps_to_fhir_patient(self) -> None:
        bundle = ClinicalBundle(
            patient_id="DEMO-100042",
            resources=[
                ClinicalResource(
                    resource_type=ResourceType.patient,
                    source_id="DEMO-100042",
                    data={
                        "name": [{"family": "Rivera", "given": ["Jamie"]}],
                        "birthDate": "1984-05-17",
                    },
                    provenance=SourceRecord(source="test"),
                )
            ],
            files=[],
        )

        result = fhir_bundle(bundle, "http://example.test/job")

        self.assertEqual("Bundle", result["resourceType"])
        self.assertEqual(
            "Patient", result["entry"][0]["resource"]["resourceType"]
        )


if __name__ == "__main__":
    unittest.main()
