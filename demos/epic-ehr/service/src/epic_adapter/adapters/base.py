from __future__ import annotations

from typing import Protocol

from ..models import ClinicalResource, ResourceType


class EhrAdapter(Protocol):
    def retrieve(
        self, patient_id: str, resources: list[ResourceType]
    ) -> list[ClinicalResource]:
        """Retrieve normalized read-only resources for one patient."""
