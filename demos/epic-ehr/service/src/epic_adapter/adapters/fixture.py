from __future__ import annotations

import json
from pathlib import Path

from ..models import ClinicalResource, ResourceType, SourceRecord
from ..file_catalog import SAFE_PATIENT_ID


class FixtureEpicAdapter:
    def __init__(self, fixture_root: Path) -> None:
        self._patient_root = fixture_root / "patients"

    def retrieve(
        self, patient_id: str, resources: list[ResourceType]
    ) -> list[ClinicalResource]:
        if not SAFE_PATIENT_ID.fullmatch(patient_id):
            raise ValueError("Invalid patient identifier.")
        path = self._patient_root / f"{patient_id}.json"
        if not path.is_file():
            raise LookupError("Patient was not found in the synthetic fixture set.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        selected: list[ClinicalResource] = []
        for resource_type in resources:
            values = payload.get(resource_type.value, [])
            if isinstance(values, dict):
                values = [values]
            for index, value in enumerate(values):
                selected.append(
                    ClinicalResource(
                        resource_type=resource_type,
                        source_id=str(value.get("id", f"{resource_type.value}-{index}")),
                        data=value,
                        provenance=SourceRecord(source="synthetic-epic-fixture"),
                    )
                )
        return selected
