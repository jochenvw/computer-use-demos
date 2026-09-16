from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree as ET

from .models import ClinicalBundle, ClinicalResource, ResourceType


def normalized_json(bundle: ClinicalBundle, base_url: str) -> dict[str, Any]:
    return {
        "patient_id": bundle.patient_id,
        "resources": [
            resource.model_dump(mode="json") for resource in bundle.resources
        ],
        "files": [
            {
                **file.model_dump(mode="json"),
                "url": f"{base_url}/files/{file.file_id}",
            }
            for file in bundle.files
        ],
    }


def ndjson(bundle: ClinicalBundle) -> str:
    return "\n".join(
        json.dumps(resource.model_dump(mode="json"), separators=(",", ":"))
        for resource in bundle.resources
    )


def fhir_bundle(bundle: ClinicalBundle, base_url: str) -> dict[str, Any]:
    entries = [
        {
            "fullUrl": (
                f"https://example.invalid/fhir/{_resource_name(resource)}/{resource.source_id}"
            ),
            "resource": _to_fhir(resource),
        }
        for resource in bundle.resources
    ]
    entries.extend(
        {
            "fullUrl": f"urn:uuid:{file.file_id}",
            "resource": {
                "resourceType": "DocumentReference",
                "id": file.file_id,
                "status": "current",
                "subject": {"reference": f"Patient/{bundle.patient_id}"},
                "content": [{
                    "attachment": {
                        "contentType": file.media_type,
                        "url": f"{base_url}/files/{file.file_id}",
                        "title": file.name,
                        "size": file.size_bytes,
                    }
                }],
            },
        }
        for file in bundle.files
    )
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": entries,
    }


# Ordered FHIR R4 subset. Unknown elements fail rather than becoming invalid XML.
# A missing type suffix denotes a primitive; complex values name their schema.
_FHIR_FIELDS = {
    "Bundle": "id meta:Meta implicitRules language identifier:Identifier type timestamp total link:Link entry:Entry",
    "Entry": "link:Link fullUrl resource:Resource",
    "Link": "relation url",
    "Meta": "versionId lastUpdated source profile security:Coding tag:Coding",
    "Patient": "id meta:Meta implicitRules language contained:Resource identifier:Identifier active name:HumanName telecom:ContactPoint gender birthDate deceasedBoolean deceasedDateTime address:Address maritalStatus:CodeableConcept multipleBirthBoolean multipleBirthInteger photo:Attachment contact:PatientContact communication:Communication generalPractitioner:Reference managingOrganization:Reference link:PatientLink",
    "PatientContact": "relationship:CodeableConcept name:HumanName telecom:ContactPoint address:Address gender organization:Reference period:Period",
    "Communication": "language:CodeableConcept preferred",
    "PatientLink": "other:Reference type",
    "Encounter": "id meta:Meta implicitRules language contained:Resource identifier:Identifier status statusHistory:StatusHistory class:Coding classHistory:ClassHistory type:CodeableConcept serviceType:CodeableConcept priority:CodeableConcept subject:Reference episodeOfCare:Reference basedOn:Reference participant:Participant appointment:Reference period:Period length:Quantity reasonCode:CodeableConcept reasonReference:Reference diagnosis:Diagnosis account:Reference hospitalization:Hospitalization location:EncounterLocation serviceProvider:Reference partOf:Reference",
    "StatusHistory": "status period:Period",
    "ClassHistory": "class:Coding period:Period",
    "Participant": "type:CodeableConcept period:Period individual:Reference",
    "Diagnosis": "condition:Reference use:CodeableConcept rank",
    "Hospitalization": "preAdmissionIdentifier:Identifier origin:Reference admitSource:CodeableConcept reAdmission:CodeableConcept dietPreference:CodeableConcept specialCourtesy:CodeableConcept specialArrangement:CodeableConcept destination:Reference dischargeDisposition:CodeableConcept",
    "EncounterLocation": "location:Reference status physicalType:CodeableConcept period:Period",
    "Observation": "id meta:Meta implicitRules language contained:Resource identifier:Identifier basedOn:Reference partOf:Reference status category:CodeableConcept code:CodeableConcept subject:Reference focus:Reference encounter:Reference effectiveDateTime effectivePeriod:Period effectiveTiming:Timing effectiveInstant issued performer:Reference valueQuantity:Quantity valueCodeableConcept:CodeableConcept valueString valueBoolean valueInteger valueRange:Range valueRatio:Ratio valueSampledData:SampledData valueTime valueDateTime valuePeriod:Period dataAbsentReason:CodeableConcept interpretation:CodeableConcept note:Annotation bodySite:CodeableConcept method:CodeableConcept specimen:Reference device:Reference referenceRange:ReferenceRange hasMember:Reference derivedFrom:Reference component:Component",
    "DiagnosticReport": "id meta:Meta implicitRules language contained:Resource identifier:Identifier basedOn:Reference status category:CodeableConcept code:CodeableConcept subject:Reference encounter:Reference effectiveDateTime effectivePeriod:Period issued performer:Reference resultsInterpreter:Reference specimen:Reference result:Reference imagingStudy:Reference media:ReportMedia conclusion conclusionCode:CodeableConcept presentedForm:Attachment",
    "ReportMedia": "comment link:Reference",
    "Component": "code:CodeableConcept valueQuantity:Quantity valueCodeableConcept:CodeableConcept valueString valueBoolean valueInteger valueRange:Range valueRatio:Ratio valueSampledData:SampledData valueTime valueDateTime valuePeriod:Period dataAbsentReason:CodeableConcept interpretation:CodeableConcept referenceRange:ReferenceRange",
    "DocumentReference": "id meta:Meta implicitRules language contained:Resource masterIdentifier:Identifier identifier:Identifier status docStatus type:CodeableConcept category:CodeableConcept subject:Reference date author:Reference authenticator:Reference custodian:Reference relatesTo:RelatesTo description securityLabel:CodeableConcept content:Content context:DocumentContext",
    "RelatesTo": "code target:Reference",
    "Content": "attachment:Attachment format:Coding",
    "DocumentContext": "encounter:Reference event:CodeableConcept period:Period facilityType:CodeableConcept practiceSetting:CodeableConcept sourcePatientInfo:Reference related:Reference",
    "Identifier": "use type:CodeableConcept system value period:Period assigner:Reference",
    "HumanName": "use text family given prefix suffix period:Period",
    "ContactPoint": "system value use rank period:Period",
    "Address": "use type text line city district state postalCode country period:Period",
    "CodeableConcept": "coding:Coding text",
    "Coding": "system version code display userSelected",
    "Reference": "reference type identifier:Identifier display",
    "Quantity": "value comparator unit system code",
    "Period": "start end",
    "Range": "low:Quantity high:Quantity",
    "Ratio": "numerator:Quantity denominator:Quantity",
    "SampledData": "origin:Quantity period factor lowerLimit upperLimit dimensions data",
    "Timing": "event code:CodeableConcept",
    "Annotation": "authorReference:Reference authorString time text",
    "ReferenceRange": "low:Quantity high:Quantity type:CodeableConcept appliesTo:CodeableConcept age:Range text",
    "Attachment": "contentType language data url size hash title creation",
}
_FHIR_RESOURCE_TYPES = {
    "Bundle", "Patient", "Encounter", "Observation", "DiagnosticReport", "DocumentReference",
}


def fhir_xml(bundle: ClinicalBundle, base_url: str) -> str:
    """Serialize the supported FHIR R4 subset as application/fhir+xml.

    Uses FHIR element order, repeated elements, resource wrappers and primitive
    value attributes. Unsupported fields (including narrative/extensions and
    primitive metadata) raise ValueError; this is not a general FHIR converter
    or schema validator. File attachments retain their download URLs.
    """
    root = ET.Element("Bundle", xmlns="http://hl7.org/fhir")
    _fhir_xml_fields(root, fhir_bundle(bundle, base_url), "Bundle")
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)


def _fhir_xml_fields(
    element: ET.Element, data: dict[str, Any], schema: str,
) -> None:
    fields = [
        (name, kind or "primitive")
        for field in _FHIR_FIELDS[schema].split()
        for name, _, kind in [field.partition(":")]
    ]
    allowed = {name for name, _ in fields}
    if schema in _FHIR_RESOURCE_TYPES:
        allowed.add("resourceType")
    elif "id" in data:
        if not isinstance(data["id"], str) or not data["id"]:
            raise ValueError("FHIR element id must be a nonempty string")
        _check_xml_text(data["id"])
        element.set("id", data["id"])
        allowed.add("id")
    if data.keys() - allowed:
        raise ValueError(f"Unsupported FHIR XML field in {schema}")
    for name, kind in fields:
        value = data.get(name)
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            child = ET.SubElement(element, name)
            if kind == "primitive":
                if not isinstance(item, (str, bool, int, float)):
                    raise ValueError(f"Unsupported FHIR primitive in {schema}.{name}")
                if isinstance(item, float) and not math.isfinite(item):
                    raise ValueError("FHIR numbers must be finite")
                text = str(item).lower() if isinstance(item, bool) else str(item)
                _check_xml_text(text)
                child.set("value", text)
            else:
                if not isinstance(item, dict):
                    raise ValueError(f"Expected FHIR object in {schema}.{name}")
                if kind == "Resource":
                    resource_type = item.get("resourceType")
                    if not isinstance(resource_type, str) or resource_type not in _FHIR_RESOURCE_TYPES:
                        raise ValueError("Unsupported FHIR XML resource type")
                    child = ET.SubElement(child, resource_type)
                    _fhir_xml_fields(child, item, resource_type)
                else:
                    _fhir_xml_fields(child, item, kind)


def _check_xml_text(value: str) -> None:
    if any(
        not (
            char in "\t\n\r"
            or "\x20" <= char <= "\ud7ff"
            or "\ue000" <= char <= "\ufffd"
            or "\U00010000" <= char <= "\U0010ffff"
        )
        for char in value
    ):
        raise ValueError("Invalid XML character")


def hl7_oru(bundle: ClinicalBundle) -> str:
    r"""Project recorded observations into HL7 v2.5.1 ORU^R01 (UTF-8).

    One OBR per observation/ECG resource; OBX NM for valueQuantity or
    valueInteger, TX for valueString, and separate OBXs for components
    (including BP systolic/diastolic). Codes/units use CE with at most two
    codings; LOINC/UCUM map to LN/UCUM. Text-only codes are permitted.
    ECG DiagnosticReports project their recorded conclusion as TX using the
    report code. Reports with only attachments/result references, coded-only
    conclusions, or mixed Observation values are unsupported.
    Recorded status and optional effectiveDateTime/issued are preserved
    (full timestamps with timezone and at most four fractional second digits).
    Other demographics, references, notes and clinical context are outside
    this projection; non-observation resources and files are not projected.

    Missing/unsupported values, statuses, timing or coding representations
    fail with ValueError, including an empty observation set. Delimiters use
    standard escapes and CR/LF use \X0D\/\X0A\ (not segment breaks).
    ECG PDF/DICOM bytes are never interpreted; only recorded values qualify.
    """
    if not isinstance(bundle.patient_id, str) or not bundle.patient_id.strip():
        raise ValueError("HL7 requires a patient identifier")
    observations = [
        resource for resource in bundle.resources
        if resource.resource_type in {ResourceType.observations, ResourceType.ecg}
    ]
    if not observations:
        raise ValueError("HL7 ORU requires at least one recorded observation")
    msh = [
        "MSH", "^~\\&", "EpicAdapter", "", "", "",
        datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%z"), "",
        "ORU^R01^ORU_R01", uuid4().hex, "P", "2.5.1",
        "", "", "", "", "", "UNICODE UTF-8",
    ]
    segments = ["|".join(msh), f"PID|1||{_hl7_escape(bundle.patient_id)}"]
    for index, resource in enumerate(observations, 1):
        data = resource.data
        if _resource_name(resource) == "DiagnosticReport":
            if any(key.startswith("value") for key in data) or any(
                key in data for key in ("component", "conclusionCode", "dataAbsentReason")
            ):
                raise ValueError("Unsupported HL7 DiagnosticReport values")
            # Project only recorded report text; never resolve attachments as values.
            data = {**data, "valueString": data.get("conclusion")}
        elif "conclusion" in data or "conclusionCode" in data:
            raise ValueError("HL7 conclusion requires an ECG DiagnosticReport")
        code = _hl7_code(data.get("code"))
        status = {
            "registered": "I", "preliminary": "P", "final": "F",
            "amended": "C", "corrected": "C",
        }.get(data.get("status")) if isinstance(data.get("status"), str) else None
        if status is None:
            raise ValueError("Unsupported or missing HL7 observation status")
        if any(key.startswith("effective") and key != "effectiveDateTime" for key in data):
            raise ValueError("HL7 projection supports only effectiveDateTime")
        observed_at = _hl7_timestamp(data.get("effectiveDateTime"))
        issued_at = _hl7_timestamp(data.get("issued"))
        obr = [""] * 23
        obr[0], obr[1], obr[3], obr[4] = (
            "OBR", str(index), _hl7_escape(resource.source_id), code,
        )
        obr[7], obr[22] = observed_at, issued_at
        segments.append("|".join(obr).rstrip("|"))
        components = data.get("component", [])
        if not isinstance(components, list):
            raise ValueError("HL7 observation components must be a list")
        values: list[tuple[dict[str, Any], str]] = []
        if any(key.startswith("value") for key in data) or not components:
            values.append((data, code))
        elif "dataAbsentReason" in data:
            raise ValueError("HL7 projection cannot represent absent values")
        for component in components:
            if not isinstance(component, dict):
                raise ValueError("HL7 observation component must be an object")
            values.append((component, _hl7_code(component.get("code"))))
        for obx_index, (value, value_code) in enumerate(values, 1):
            value_type, result, units = _hl7_value(value)
            obx = [""] * 15
            obx[0:7] = [
                "OBX", str(obx_index), value_type, value_code, str(obx_index),
                result, units,
            ]
            obx[11], obx[14] = status, observed_at
            segments.append("|".join(obx).rstrip("|"))
    return "\r".join(segments) + "\r"


def _hl7_escape(value: str) -> str:
    escapes = {
        "\\": "\\E\\", "|": "\\F\\", "^": "\\S\\",
        "~": "\\R\\", "&": "\\T\\", "\r": "\\X0D\\", "\n": "\\X0A\\",
    }
    return "".join(
        escapes.get(char, f"\\X{ord(char):02X}\\" if ord(char) < 32 or ord(char) == 127 else char)
        for char in value
    )


def _hl7_code(value: Any) -> str:
    if not isinstance(value, dict) or value.keys() - {"coding", "text"}:
        raise ValueError("Unsupported or missing HL7 observation code")
    codings = value.get("coding", [])
    text = value.get("text", "")
    if not isinstance(text, str) or not isinstance(codings, list) or len(codings) > 2:
        raise ValueError("HL7 CE supports text and at most two codings")
    if not codings:
        if not text.strip():
            raise ValueError("HL7 requires a code or recorded code text")
        return f"^{_hl7_escape(text)}"
    parts = []
    for coding in codings:
        if not isinstance(coding, dict) or coding.keys() - {"code", "display", "system"}:
            raise ValueError("Unsupported HL7 coding fields")
        code, display, system = (
            coding.get("code"), coding.get("display", text), coding.get("system", ""),
        )
        if not all(isinstance(item, str) for item in (code, display, system)) or not code:
            raise ValueError("HL7 coding requires a nonempty string code")
        parts.extend([_hl7_escape(code), _hl7_escape(display), _hl7_system(system)])
    return "^".join(parts)


def _hl7_system(system: str) -> str:
    return _hl7_escape({
        "http://loinc.org": "LN", "http://unitsofmeasure.org": "UCUM",
    }.get(system, system))


def _hl7_value(data: dict[str, Any]) -> tuple[str, str, str]:
    keys = [key for key in data if key.startswith("value")]
    if len(keys) != 1 or "dataAbsentReason" in data:
        raise ValueError("HL7 requires exactly one recorded value per OBX")
    kind = keys[0]
    value = data[kind]
    if kind == "valueString":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("HL7 text observations must be nonempty strings")
        return "TX", _hl7_escape(value), ""
    if kind == "valueInteger":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("HL7 valueInteger must be an integer")
        return "NM", str(value), ""
    if kind != "valueQuantity" or not isinstance(value, dict):
        raise ValueError("Unsupported HL7 observation value type")
    if value.keys() - {"value", "unit", "system", "code"}:
        raise ValueError("Unsupported HL7 quantity fields (including comparator)")
    number = value.get("value")
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        raise ValueError("HL7 quantity requires a recorded numeric value")
    if isinstance(number, float) and not math.isfinite(number):
        raise ValueError("HL7 quantity must be finite")
    unit, code, system = (value.get(key, "") for key in ("unit", "code", "system"))
    if not all(isinstance(item, str) for item in (unit, code, system)):
        raise ValueError("HL7 quantity units must be strings")
    if system and not code:
        raise ValueError("HL7 quantity system requires a unit code")
    units = "^".join([_hl7_escape(code), _hl7_escape(unit), _hl7_system(system)])
    # HL7 NM has no exponent notation.
    return "NM", format(Decimal(str(number)), "f"), units if unit or code else ""


def _hl7_timestamp(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("HL7 observation timestamp must be a string")
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,4})?(?:Z|[+-]\d{2}:\d{2})",
        value,
    ):
        raise ValueError("Unsupported HL7 observation timestamp precision or timezone")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Unsupported HL7 observation timestamp") from exc
    if "T" not in value or timestamp.tzinfo is None:
        raise ValueError("HL7 observation timestamps require time and timezone")
    fraction = f".{timestamp.microsecond:06d}".rstrip("0") if timestamp.microsecond else ""
    return timestamp.strftime("%Y%m%d%H%M%S") + fraction + timestamp.strftime("%z")


def _to_fhir(resource: ClinicalResource) -> dict[str, Any]:
    # Preserve documented quantities/components; never fabricate clinical defaults.
    return {
        **{key: value for key, value in resource.data.items() if value is not None},
        "resourceType": _resource_name(resource),
        "id": resource.source_id,
    }


def _resource_name(resource: ClinicalResource) -> str:
    if resource.resource_type == ResourceType.patient:
        return "Patient"
    if resource.resource_type == ResourceType.encounters:
        return "Encounter"
    if resource.resource_type == ResourceType.ecg and (
        resource.data.get("resourceType") == "DiagnosticReport"
        or "conclusion" in resource.data
        or "conclusionCode" in resource.data
    ):
        return "DiagnosticReport"
    if resource.resource_type in {
        ResourceType.observations,
        ResourceType.ecg,
    }:
        return "Observation"
    return "DocumentReference"
