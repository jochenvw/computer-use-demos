import copy
import json
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from epic_adapter.adapters.fixture import FixtureEpicAdapter
from epic_adapter.formats import (
    fhir_bundle,
    fhir_xml,
    hl7_oru,
    ndjson,
    normalized_json,
    omop_json,
)
from epic_adapter.models import (
    ClinicalBundle,
    ClinicalResource,
    FileRecord,
    ResourceType,
    SourceRecord,
)

BASE_URL = "https://example.test/job"
NS = {"f": "http://hl7.org/fhir"}


def resource(resource_type: ResourceType, data: dict, source_id: str = "record-1") -> ClinicalResource:
    return ClinicalResource(
        resource_type=resource_type,
        source_id=source_id,
        data=data,
        provenance=SourceRecord(source="test"),
    )


def bundle(*resources: ClinicalResource) -> ClinicalBundle:
    return ClinicalBundle(patient_id="DEMO-100042", resources=list(resources), files=[])


def concept(code: str, text: str) -> dict:
    return {"coding": [{"system": "http://loinc.org", "code": code, "display": text}]}


def blood_pressure() -> ClinicalResource:
    return resource(ResourceType.observations, {
        "component": [
            {
                "valueQuantity": {
                    "code": "mm[Hg]", "system": "http://unitsofmeasure.org",
                    "unit": "mmHg", "value": value,
                },
                "code": concept(code, text),
            }
            for code, text, value in [
                ("8480-6", "Systolic blood pressure", 120),
                ("8462-4", "Diastolic blood pressure", 80),
            ]
        ],
        "effectiveDateTime": "2026-09-10T09:10:00+02:00",
        "subject": {"reference": "Patient/DEMO-100042"},
        "code": concept("85354-9", "Blood pressure panel"),
        "status": "final",
    })


def attachment() -> FileRecord:
    return FileRecord(
        file_id="ecg-file", name="ECG & report.pdf", media_type="application/pdf",
        size_bytes=42, sha256="a" * 64, path=r"C:\private\ecg.pdf",
    )


class FhirFormatTests(unittest.TestCase):
    def test_omop_projects_patient_and_measurement_source_values(self) -> None:
        result = omop_json(bundle(blood_pressure()))

        self.assertEqual("5.4", result["cdm_version"])
        self.assertEqual("DEMO-100042", result["tables"]["person"][0]["person_source_value"])
        measurements = result["tables"]["measurement"]
        self.assertEqual(2, len(measurements))
        self.assertEqual(
            {"8480-6", "8462-4"},
            {row["measurement_source_value"] for row in measurements},
        )
        self.assertEqual({120, 80}, {row["value_as_number"] for row in measurements})
        self.assertEqual({"mm[Hg]"}, {row["unit_source_value"] for row in measurements})

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

    def test_original_formats_preserve_data_and_downloads_without_paths(self) -> None:
        record = blood_pressure()
        record.data["optional"] = None
        record.data["resourceType"] = "wrong"
        record.data["id"] = "wrong"
        original = bundle(record)
        original.files.append(attachment())
        before = copy.deepcopy(original.model_dump())

        normalized = normalized_json(original, BASE_URL)
        self.assertEqual(record.model_dump(mode="json"), normalized["resources"][0])
        self.assertEqual(
            {**original.files[0].model_dump(mode="json"), "url": f"{BASE_URL}/files/ecg-file"},
            normalized["files"][0],
        )
        self.assertEqual(
            json.dumps(record.model_dump(mode="json"), separators=(",", ":")),
            ndjson(original),
        )
        fhir = fhir_bundle(original, BASE_URL)
        expected = {key: value for key, value in record.data.items() if value is not None}
        expected.update(resourceType="Observation", id=record.source_id)
        self.assertEqual(expected, fhir["entry"][0]["resource"])
        self.assertEqual("collection", fhir["type"])
        self.assertEqual(
            f"https://example.invalid/fhir/Observation/{record.source_id}",
            fhir["entry"][0]["fullUrl"],
        )
        self.assertEqual(
            f"{BASE_URL}/files/ecg-file",
            fhir["entry"][1]["resource"]["content"][0]["attachment"]["url"],
        )
        for output in (json.dumps(normalized), json.dumps(fhir), ndjson(original)):
            self.assertNotIn("private", output)
            self.assertNotIn('"path"', output)
        self.assertEqual(before, original.model_dump())

    def test_empty_original_formats_remain_supported(self) -> None:
        original = bundle()
        self.assertEqual("", ndjson(original))
        self.assertEqual([], fhir_bundle(original, BASE_URL)["entry"])
        self.assertEqual([], normalized_json(original, BASE_URL)["resources"])
        self.assertEqual("collection", ET.fromstring(fhir_xml(original, BASE_URL))[0].get("value"))

    def test_xml_patient_primitives_order_arrays_and_escaping(self) -> None:
        text = 'Rivera & <Lee> "Quoted"'
        original = bundle(resource(ResourceType.patient, {
            "birthDate": "1984-05-17",
            "name": [{"given": ["Jamie", "Alex"], "family": text}],
            "active": False,
            "identifier": [{"value": "abc&123", "system": "https://example.test/mrn"}],
        }, "patient-1"))
        xml = fhir_xml(original, BASE_URL)
        root = ET.fromstring(xml)
        self.assertEqual("{http://hl7.org/fhir}Bundle", root.tag)
        self.assertEqual(["type", "entry"], [node.tag.split("}")[1] for node in root])
        patient = root.find("f:entry/f:resource/f:Patient", NS)
        self.assertIsNotNone(patient)
        self.assertEqual(
            ["id", "identifier", "active", "name", "birthDate"],
            [node.tag.split("}")[1] for node in patient],
        )
        self.assertEqual("false", patient.find("f:active", NS).get("value"))
        self.assertEqual(text, patient.find("f:name/f:family", NS).get("value"))
        self.assertEqual(
            ["Jamie", "Alex"],
            [node.get("value") for node in patient.findall("f:name/f:given", NS)],
        )
        self.assertIn("&amp;", xml)
        self.assertIn("&lt;Lee&gt;", xml)
        self.assertIn("&quot;", xml)
        self.assertNotIn("<resourceType", xml)
        self.assertIsNone(patient.find("f:name/f:family", NS).text)
        self.assertEqual("patient-1", patient.find("f:id", NS).get("value"))

    def test_xml_observation_components_follow_fhir_order(self) -> None:
        original = bundle(blood_pressure())
        before = copy.deepcopy(original.model_dump())
        root = ET.fromstring(fhir_xml(original, BASE_URL))
        observation = root.find("f:entry/f:resource/f:Observation", NS)
        self.assertEqual(
            ["id", "status", "code", "subject", "effectiveDateTime", "component", "component"],
            [node.tag.split("}")[1] for node in observation],
        )
        components = observation.findall("f:component", NS)
        self.assertEqual(2, len(components))
        for component, expected in zip(components, ("120", "80")):
            self.assertEqual(["code", "valueQuantity"], [node.tag.split("}")[1] for node in component])
            quantity = component.find("f:valueQuantity", NS)
            self.assertEqual(["value", "unit", "system", "code"], [node.tag.split("}")[1] for node in quantity])
            self.assertEqual(expected, quantity.find("f:value", NS).get("value"))
            self.assertEqual("mm[Hg]", quantity.find("f:code", NS).get("value"))
        self.assertEqual(before, original.model_dump())

    def test_xml_encounter_document_ecg_and_download_attachment(self) -> None:
        original = bundle(
            resource(ResourceType.encounters, {
                "period": {"end": "2026-09-10", "start": "2026-09-09"},
                "class": {"code": "AMB", "system": "urn:test"},
                "status": "finished",
            }),
            resource(ResourceType.documents, {
                "description": "Recorded note", "status": "current", "content": [],
            }),
            resource(ResourceType.ecg, {
                "valueString": "Recorded sinus rhythm", "code": {"text": "ECG"}, "status": "final",
            }),
        )
        original.files.append(attachment())
        xml = fhir_xml(original, BASE_URL + "?x=1&y=2")
        root = ET.fromstring(xml)
        wrappers = root.findall("f:entry/f:resource", NS)
        self.assertEqual(
            ["Encounter", "DocumentReference", "Observation", "DocumentReference"],
            [wrapper[0].tag.split("}")[1] for wrapper in wrappers],
        )
        self.assertEqual(["id", "status", "class", "period"], [node.tag.split("}")[1] for node in wrappers[0][0]])
        download = wrappers[3].find("f:DocumentReference/f:content/f:attachment", NS)
        self.assertEqual(["contentType", "url", "size", "title"], [node.tag.split("}")[1] for node in download])
        self.assertEqual("application/pdf", download.find("f:contentType", NS).get("value"))
        self.assertEqual("42", download.find("f:size", NS).get("value"))
        self.assertEqual(BASE_URL + "/files/ecg-file?x=1&y=2", download.find("f:url", NS).get("value"))
        self.assertEqual("ECG & report.pdf", download.find("f:title", NS).get("value"))
        self.assertNotIn("private", xml)
        self.assertNotIn("path", xml)

    def test_xml_contained_resource_wrapper_and_datatype_id_attribute(self) -> None:
        original = bundle(resource(ResourceType.observations, {
            "contained": [{"resourceType": "Patient", "id": "p1", "active": True}],
            "code": {"id": "code1", "text": "Heart rate"},
            "valueInteger": 72,
        }))
        root = ET.fromstring(fhir_xml(original, BASE_URL))
        observation = root.find("f:entry/f:resource/f:Observation", NS)
        self.assertEqual("p1", observation.find("f:contained/f:Patient/f:id", NS).get("value"))
        self.assertEqual("code1", observation.find("f:code", NS).get("id"))
        self.assertIsNone(observation.find("f:code/f:id", NS))

    def test_xml_unsupported_data_fails_explicitly(self) -> None:
        for data in (
            {"customField": "not FHIR"},
            {"_valueString": {"extension": []}},
            {"valueString": {"invalid": "object"}},
            {"valueQuantity": {"value": float("nan")}},
            {"code": "not an object"},
            {"valueString": "bad\x00text"},
            {"contained": [{"resourceType": "Unknown"}]},
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                fhir_xml(bundle(resource(ResourceType.observations, data)), BASE_URL)


class Hl7FormatTests(unittest.TestCase):
    def test_ecg_diagnostic_report_conclusion_preserves_text_and_resource_type(self) -> None:
        text = "Recorded sinus rhythm | QT^summary\r\nNo waveform conversion"
        for declared in (False, True):
            with self.subTest(declared=declared):
                data = {
                    "conclusion": text,
                    "presentedForm": [{
                        "contentType": "application/pdf", "url": "https://example.test/ecg.pdf",
                    }],
                    "result": [{"reference": "Observation/ecg-measurements"}],
                    "effectiveDateTime": "2026-09-10T09:15:00Z",
                    "code": concept("11524-6", "ECG report"),
                    "status": "final",
                }
                if declared:
                    data["resourceType"] = "DiagnosticReport"
                original = bundle(resource(ResourceType.ecg, data))
                before = copy.deepcopy(original.model_dump())
                fhir = fhir_bundle(original, BASE_URL)["entry"][0]
                self.assertEqual("DiagnosticReport", fhir["resource"]["resourceType"])
                self.assertEqual(text, fhir["resource"]["conclusion"])
                self.assertNotIn("valueString", fhir["resource"])
                self.assertTrue(fhir["fullUrl"].endswith("/DiagnosticReport/record-1"))
                report = ET.fromstring(fhir_xml(original, BASE_URL)).find(
                    "f:entry/f:resource/f:DiagnosticReport", NS,
                )
                self.assertIsNotNone(report)
                self.assertEqual(
                    ["id", "status", "code", "effectiveDateTime", "result", "conclusion", "presentedForm"],
                    [node.tag.split("}")[1] for node in report],
                )
                self.assertEqual(text, report.find("f:conclusion", NS).get("value"))
                message = hl7_oru(original)
                obxs = [line.split("|") for line in message.split("\r") if line.startswith("OBX|")]
                self.assertEqual(1, len(obxs))
                self.assertEqual("TX", obxs[0][2])
                self.assertEqual("11524-6^ECG report^LN", obxs[0][3])
                self.assertEqual(
                    "Recorded sinus rhythm \\F\\ QT\\S\\summary\\X0D\\\\X0A\\No waveform conversion",
                    obxs[0][5],
                )
                self.assertNotIn("ecg.pdf", message)
                self.assertEqual(before, original.model_dump())

    def test_diagnostic_report_without_supported_conclusion_fails(self) -> None:
        for values in (
            {}, {"conclusion": ""}, {"conclusion": None},
            {"conclusion": ["not text"]},
            {"presentedForm": [{"contentType": "application/pdf", "url": "ecg.pdf"}]},
            {"result": [{"reference": "Observation/ecg-measurements"}]},
            {"conclusionCode": [{"text": "normal"}]},
            {"conclusion": "normal", "conclusionCode": [{"text": "normal"}]},
            {"conclusion": "normal", "valueString": "conflicting value"},
            {"conclusion": "normal", "component": []},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                hl7_oru(bundle(resource(ResourceType.ecg, {
                    "resourceType": "DiagnosticReport", "status": "final",
                    "code": {"text": "ECG report"}, **values,
                })))

    def test_bp_panel_has_two_numeric_obx_with_codes_units_and_timestamp(self) -> None:
        original = bundle(blood_pressure())
        before = copy.deepcopy(original.model_dump())
        message = hl7_oru(original)
        segments = [line.split("|") for line in message.rstrip("\r").split("\r")]
        self.assertEqual(["MSH", "PID", "OBR", "OBX", "OBX"], [line[0] for line in segments])
        msh, pid, obr, systolic, diastolic = segments
        self.assertEqual("^~\\&", msh[1])
        self.assertEqual("ORU^R01^ORU_R01", msh[8])
        self.assertEqual("2.5.1", msh[11])
        self.assertEqual("UNICODE UTF-8", msh[17])
        self.assertTrue(msh[9])
        self.assertEqual(original.patient_id, pid[3])
        self.assertEqual("85354-9^Blood pressure panel^LN", obr[4])
        self.assertEqual("20260910091000+0200", obr[7])
        for obx, code, value in ((systolic, "8480-6", "120"), (diastolic, "8462-4", "80")):
            self.assertEqual("NM", obx[2])
            self.assertEqual(code, obx[3].split("^")[0])
            self.assertEqual("LN", obx[3].split("^")[2])
            self.assertEqual(value, obx[5])
            self.assertEqual("mm[Hg]^mmHg^UCUM", obx[6])
            self.assertEqual("F", obx[11])
            self.assertEqual("20260910091000+0200", obx[14])
        self.assertTrue(message.endswith("\r"))
        self.assertNotIn("\n", message)
        self.assertEqual(before, original.model_dump())

    def test_recorded_ecg_text_and_all_delimiters_are_escaped(self) -> None:
        text = "Sinus | rhythm^with~text&slash\\\r\nnext"
        original = bundle(resource(ResourceType.ecg, {
            "status": "final", "code": {"text": "ECG|summary"},
            "valueString": text,
        }, "ecg|1"))
        original.patient_id = "patient|^~&\\"
        original.files.append(attachment())
        message = hl7_oru(original)
        segments = message.rstrip("\r").split("\r")
        self.assertEqual(4, len(segments))
        self.assertEqual("patient\\F\\\\S\\\\R\\\\T\\\\E\\", segments[1].split("|")[3])
        self.assertEqual("ecg\\F\\1", segments[2].split("|")[3])
        obx = segments[3].split("|")
        self.assertEqual("TX", obx[2])
        self.assertEqual("^ECG\\F\\summary", obx[3])
        self.assertEqual("Sinus \\F\\ rhythm\\S\\with\\R\\text\\T\\slash\\E\\\\X0D\\\\X0A\\next", obx[5])
        self.assertNotIn("\n", message)
        self.assertNotIn("private", message)
        self.assertNotIn("pdf", message)

    def test_integer_text_and_exponent_quantity_values(self) -> None:
        for value, expected_type, expected_value in (
            ({"valueInteger": 0}, "NM", "0"),
            ({"valueQuantity": {"value": 1e-7}}, "NM", "0.0000001"),
            ({"valueString": "72 beats/minute"}, "TX", "72 beats/minute"),
        ):
            with self.subTest(value=value):
                original = bundle(resource(ResourceType.observations, {
                    "status": "preliminary", "code": {"text": "Recorded observation"}, **value,
                }))
                obx = hl7_oru(original).rstrip("\r").split("\r")[-1].split("|")
                self.assertEqual(expected_type, obx[2])
                self.assertEqual(expected_value, obx[5])
                self.assertEqual("P", obx[11])
                self.assertEqual("", obx[6])

    def test_alternate_coding_units_and_issued_timestamp(self) -> None:
        original = bundle(resource(ResourceType.observations, {
            "status": "corrected",
            "code": {"coding": [
                {"code": "8867-4", "display": "Heart rate", "system": "http://loinc.org"},
                {"code": "hr|local", "display": "Rate^local", "system": "urn:local"},
            ]},
            "issued": "2026-09-10T09:10:00.1234Z",
            "valueQuantity": {"value": 72, "unit": "beats/min"},
        }))
        segments = hl7_oru(original).rstrip("\r").split("\r")
        self.assertEqual("20260910091000.1234+0000", segments[2].split("|")[22])
        obx = segments[3].split("|")
        self.assertEqual("8867-4^Heart rate^LN^hr\\F\\local^Rate\\S\\local^urn:local", obx[3])
        self.assertEqual("^beats/min^", obx[6])
        self.assertEqual("C", obx[11])

    def test_no_observations_or_file_only_ecg_fails(self) -> None:
        for original in (bundle(), bundle(resource(ResourceType.patient, {}))):
            original.files.append(attachment())
            with self.subTest(original=original), self.assertRaisesRegex(ValueError, "at least one"):
                hl7_oru(original)

    def test_unsupported_or_missing_observation_data_fails(self) -> None:
        invalid = [
            {}, {"valueString": ""}, {"valueString": None},
            {"valueBoolean": True}, {"valueInteger": True},
            {"valueCodeableConcept": {"text": "normal"}},
            {"valueSampledData": {"data": "1 2 3"}},
            {"valueQuantity": {}}, {"valueQuantity": {"value": "120"}},
            {"valueQuantity": {"value": True}},
            {"valueQuantity": {"value": float("nan")}},
            {"valueQuantity": {"value": float("inf")}},
            {"valueQuantity": {"value": 120, "comparator": "<"}},
            {"valueQuantity": {"value": 120, "system": "urn:unit"}},
            {"valueString": "ok", "valueInteger": 1},
            {"valueString": "ok", "dataAbsentReason": {"text": "unknown"}},
            {"valueString": "ok", "status": "unknown"},
            {"valueString": "ok", "status": []},
            {"valueString": "ok", "code": {}},
            {"valueString": "ok", "code": {"coding": [{"code": "x", "version": "1"}]}},
            {"valueString": "ok", "code": {"coding": [{"code": "x"}] * 3}},
            {"valueString": "ok", "effectivePeriod": {"start": "2026-09-10"}},
            {"valueString": "ok", "effectiveDateTime": "2026-09-10"},
            {"valueString": "ok", "effectiveDateTime": "2026-09-10T09:10:00"},
            {"valueString": "ok", "effectiveDateTime": "2026-09-10T09:10:00.123456Z"},
            {"valueString": "ok", "issued": "bad"},
            {"component": []}, {"component": {}},
            {"component": ["invalid"]},
            {"component": [{"code": {"text": "Systolic"}}]},
        ]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                hl7_oru(bundle(resource(ResourceType.observations, {
                    "status": "final", "code": {"text": "Observation"}, **data,
                })))

    def test_unsupported_observation_is_not_silently_omitted(self) -> None:
        original = bundle(blood_pressure(), resource(ResourceType.ecg, {
            "status": "final", "code": {"text": "ECG PDF"}, "attachment": {"url": "ecg.pdf"},
        }))
        with self.assertRaises(ValueError):
            hl7_oru(original)

    def test_missing_patient_identifier_fails(self) -> None:
        original = bundle(blood_pressure())
        original.patient_id = ""
        with self.assertRaisesRegex(ValueError, "patient identifier"):
            hl7_oru(original)


class FixtureFormatTests(unittest.TestCase):
    def test_actual_fixture_all_resources_and_ecg_only_support_all_formats(self) -> None:
        adapter = FixtureEpicAdapter(Path(__file__).resolve().parents[2] / "fixtures")
        for types in (list(ResourceType), [ResourceType.ecg]):
            with self.subTest(types=types):
                original = ClinicalBundle(
                    patient_id="DEMO-100042",
                    resources=adapter.retrieve("DEMO-100042", types),
                    files=[],
                )
                before = copy.deepcopy(original.model_dump())
                normalized = normalized_json(original, BASE_URL)
                lines = ndjson(original).splitlines()
                fhir = fhir_bundle(original, BASE_URL)
                xml = ET.fromstring(fhir_xml(original, BASE_URL))
                message = hl7_oru(original)
                self.assertEqual(len(original.resources), len(normalized["resources"]))
                self.assertEqual(
                    normalized["resources"], [json.loads(line) for line in lines],
                )
                self.assertEqual(len(original.resources), len(fhir["entry"]))
                self.assertEqual(len(original.resources), len(xml.findall("f:entry", NS)))
                report = xml.find("f:entry/f:resource/f:DiagnosticReport", NS)
                self.assertIsNotNone(report)
                ecg = next(record for record in original.resources if record.resource_type == ResourceType.ecg)
                self.assertEqual(ecg.data["conclusion"], report.find("f:conclusion", NS).get("value"))
                obxs = [line.split("|") for line in message.split("\r") if line.startswith("OBX|")]
                self.assertEqual(1, sum(obx[5] == ecg.data["conclusion"] for obx in obxs))
                if types == [ResourceType.ecg]:
                    self.assertEqual(1, len(obxs))
                    self.assertEqual("TX", obxs[0][2])
                else:
                    numeric = [obx for obx in obxs if obx[2] == "NM"]
                    self.assertEqual(2, len(numeric))
                    self.assertEqual(
                        {("8480-6", "120", "mm[Hg]^mmHg^UCUM"), ("8462-4", "80", "mm[Hg]^mmHg^UCUM")},
                        {(obx[3].split("^")[0], obx[5], obx[6]) for obx in numeric},
                    )
                self.assertTrue(message.endswith("\r"))
                self.assertNotIn("\n", message)
                self.assertEqual(before, original.model_dump())


if __name__ == "__main__":
    unittest.main()
