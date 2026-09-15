from __future__ import annotations

import json
from typing import Any

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
    if resource.resource_type in {
        ResourceType.observations,
        ResourceType.ecg,
    }:
        return "Observation"
    return "DocumentReference"
