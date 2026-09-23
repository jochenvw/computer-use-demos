from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    patient = "patient"
    encounters = "encounters"
    observations = "observations"
    documents = "documents"
    ecg = "ecg"


class OutputFormat(str, Enum):
    json = "json"
    fhir = "fhir"
    omop = "omop"
    ndjson = "ndjson"
    fhir_xml = "fhir-xml"
    hl7 = "hl7"


class RetrievalSource(str, Enum):
    files = "files"
    ehr = "ehr"
    sql = "sql"
    both = "both"


class RetrievalRequest(BaseModel):
    patient_id: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
    )
    source: RetrievalSource = RetrievalSource.both
    resources: list[ResourceType] = Field(
        default_factory=lambda: list(ResourceType), min_length=1, max_length=5
    )
    observation_codes: list[Annotated[str, Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9.-]+$",
    )]] = Field(default_factory=list, max_length=32)
    bypass_cache: bool = False


class SourceRecord(BaseModel):
    source: str
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ClinicalResource(BaseModel):
    resource_type: ResourceType
    source_id: str
    data: dict[str, Any]
    provenance: SourceRecord


class FileRecord(BaseModel):
    file_id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    media_type: str
    size_bytes: int
    sha256: str
    path: str = Field(exclude=True)


class ClinicalBundle(BaseModel):
    patient_id: str
    resources: list[ClinicalResource]
    files: list[FileRecord]


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    complete = "complete"
    failed = "failed"


class CacheStatus(str, Enum):
    hit = "hit"
    miss = "miss"
    bypass = "bypass"


class JobRecord(BaseModel):
    job_id: str = Field(default_factory=lambda: uuid4().hex)
    status: JobStatus = JobStatus.queued
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: datetime | None = None
    error: str | None = None
    cache_status: CacheStatus | None = None
    collected_at: datetime | None = None
    expires_at: datetime | None = None
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    bundle: ClinicalBundle | None = Field(default=None, exclude=True)
