from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .adapters.base import EhrAdapter
from .audit import AuditWriter
from .cache import RetrievalCache
from .file_catalog import FileCatalog
from .models import (
    CacheStatus,
    ClinicalBundle,
    JobRecord,
    JobStatus,
    ResourceType,
    RetrievalRequest,
    RetrievalSource,
)
from .progress import begin, emit, end, story

logger = logging.getLogger(__name__)

SCENARIO_LABELS = {
    RetrievalSource.ehr: "1 - Clinical data from the EMR",
    RetrievalSource.pacs: "2 - Medical imaging from PACS",
    RetrievalSource.sql: "3 - Local Italian database (unknown schema)",
    RetrievalSource.files: "Fallback - ECG file on this workstation",
    RetrievalSource.both: "EMR + local files",
}
HANDOVER = (
    "Handing over to the MDT dashboard, UMC Utrecht, in the requested standard: "
    "FHIR, OMOP or a custom schema"
)


class ServiceDrainingError(RuntimeError):
    pass


class JobService:
    def __init__(
        self,
        adapter: EhrAdapter,
        file_catalog: FileCatalog,
        audit: AuditWriter,
        *,
        cache: RetrievalCache | None = None,
        backend_scope: str = "fixture",
        file_retriever: Callable[[str, list[ResourceType], FileCatalog], ClinicalBundle] | None = None,
        database_retriever: Callable[..., ClinicalBundle] | None = None,
        pacs_retriever: Callable[..., ClinicalBundle] | None = None,
    ) -> None:
        self._adapter = adapter
        self._file_catalog = file_catalog
        self._audit = audit
        self._cache = cache if cache is not None else RetrievalCache()
        self._backend_scope = backend_scope
        self._file_retriever = file_retriever
        self._database_retriever = database_retriever
        self._pacs_retriever = pacs_retriever
        self._jobs: dict[str, JobRecord] = {}
        self._gui_lock = threading.Lock()
        self._records_lock = threading.Lock()
        self._idle = threading.Condition(self._records_lock)
        self._accepting = True

    def create(self, request: RetrievalRequest, caller_id: str) -> JobRecord:
        job = JobRecord()
        with self._idle:
            if not self._accepting:
                raise ServiceDrainingError(
                    "Service is draining for an update and is not accepting new jobs."
                )
            pending = sum(
                item.status in {JobStatus.queued, JobStatus.running}
                for item in self._jobs.values()
            )
            if pending >= 8 or len(self._jobs) >= 128:
                raise RuntimeError("Demo job capacity reached; retrieve results and restart the service.")
            self._audit.write(
                event="retrieval-created",
                caller_id=caller_id,
                patient_id=request.patient_id,
                job_id=job.job_id,
                outcome="queued",
            )
            self._jobs[job.job_id] = job
        emit(f"JOB {job.job_id[:8]}  queued / source={request.source.value}")
        thread = threading.Thread(
            target=self._run,
            args=(job.job_id, request, caller_id),
            daemon=True,
        )
        thread.start()
        return job

    def get(self, job_id: str) -> JobRecord:
        with self._records_lock:
            try:
                return self._jobs[job_id]
            except KeyError as exc:
                raise LookupError("Retrieval job was not found.") from exc

    def service_status(self) -> dict[str, int | bool]:
        with self._records_lock:
            active = sum(
                item.status in {JobStatus.queued, JobStatus.running}
                for item in self._jobs.values()
            )
            return {
                "accepting_jobs": self._accepting,
                "active_jobs": active,
                "process_id": os.getpid(),
            }

    def drain(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        with self._idle:
            self._accepting = False
            while any(
                item.status in {JobStatus.queued, JobStatus.running}
                for item in self._jobs.values()
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._accepting = True
                    self._idle.notify_all()
                    return False
                self._idle.wait(remaining)
            return True

    def file_path(self, job_id: str, file_id: str) -> tuple[Path, str]:
        job = self.get(job_id)
        if job.status != JobStatus.complete or job.bundle is None:
            raise RuntimeError("Retrieval job is not complete.")
        record = next(
            (item for item in job.bundle.files if item.file_id == file_id),
            None,
        )
        if record is None:
            raise LookupError("File was not found in this retrieval job.")
        return self._file_catalog.verify(record, job.bundle.patient_id), record.media_type

    def _run(
        self,
        job_id: str,
        request: RetrievalRequest,
        caller_id: str,
    ) -> None:
        job = self._jobs[job_id]
        started = time.monotonic()
        label = SCENARIO_LABELS.get(request.source, request.source.value)
        try:
            with self._gui_lock:
                with self._idle:
                    job.status = JobStatus.running
                begin(job.timeline, label, job_id)
                emit(f"JOB {job_id[:8]}  running")
                if request.instruction:
                    story("task", request.instruction)
                story("start", f"New request · {label} · patient {request.patient_id} · "
                      f"asking for: {', '.join(r.value for r in request.resources)}")
                key = self._cache.key(request, caller_id, self._backend_scope)
                if request.bypass_cache:
                    self._cache.invalidate(key)
                entry = None if request.bypass_cache else self._cache.get(key)
                job.cache_status = (
                    CacheStatus.bypass if request.bypass_cache
                    else CacheStatus.hit if entry else CacheStatus.miss
                )
                emit(f"CACHE    {job.cache_status.value}")
                if entry is not None:
                    story("info", "Reusing the result collected earlier (cache hit)")
                else:
                    story("info", "Starting the computer-use agent with the matching skill")
                if entry is None:
                    resources = []
                    files = []
                    extra = {
                        key: value for key, value in {
                            "instruction": request.instruction,
                            "patient_name": request.display_name(),
                        }.items() if value
                    }
                    if request.source in {RetrievalSource.ehr, RetrievalSource.both}:
                        emit("EMR      retrieving requested chart resources")
                        resources = self._adapter.retrieve(
                            request.patient_id, request.resources, **extra,
                        )
                    for source, retriever, tag in (
                        (RetrievalSource.sql, self._database_retriever, "SQL"),
                        (RetrievalSource.pacs, self._pacs_retriever, "PACS"),
                    ):
                        if request.source != source:
                            continue
                        if retriever is None:
                            raise RuntimeError(f"{tag} retrieval is not configured.")
                        emit(f"{tag:<8} navigating the approved local workspace")
                        found = retriever(request.patient_id, request.resources, **extra)
                        if found.patient_id != request.patient_id:
                            raise ValueError(f"{tag} retrieval patient mismatch.")
                        resources.extend(found.resources)
                        files.extend(found.files)
                    if request.source in {RetrievalSource.files, RetrievalSource.both}:
                        if self._file_retriever is not None:
                            local = self._file_retriever(
                                request.patient_id, request.resources, self._file_catalog,
                                **extra,
                            )
                            if local.patient_id != request.patient_id:
                                raise ValueError("Local-file retrieval patient mismatch.")
                            resources.extend(local.resources)
                            files = local.files
                        else:
                            emit("FILES    searching approved patient directories")
                            files = self._file_catalog.find(request.patient_id)
                    if request.observation_codes:
                        codes = set(request.observation_codes)
                        resources = [
                            resource for resource in resources
                            if resource.resource_type != ResourceType.observations
                            or _observation_has_code(resource.data, codes)
                        ]
                    bundle = ClinicalBundle(
                        patient_id=request.patient_id, resources=resources, files=files,
                    )
                else:
                    bundle = entry.bundle
                self._audit.write(
                    event="retrieval-finished", caller_id=caller_id,
                    patient_id=request.patient_id, job_id=job_id, outcome="complete",
                )
                if entry is None:
                    entry = self._cache.put(key, bundle)
                job.bundle = bundle
                job.collected_at = entry.collected_at
                job.expires_at = entry.expires_at
                job.completed_at = datetime.now(timezone.utc)
                with self._idle:
                    job.status = JobStatus.complete
                    self._idle.notify_all()
                emit(f"JOB {job_id[:8]}  complete / {len(bundle.resources)} resource(s), {len(bundle.files)} file(s)")
                story("done", f"Done in {time.monotonic() - started:.0f} s · "
                      f"{len(bundle.resources)} clinical item(s) collected")
                story("handover", HANDOVER)
                end()
        except Exception as exc:
            job.error = "Retrieval failed. Contact the service operator with the job ID."
            reason = str(exc)
            if reason.startswith("Skill stopped without verified data: "):
                # Fixed enum values only; safe to show the caller.
                job.error = reason
                if reason.endswith("session_expired."):
                    job.error += " Sign in to the EMR in the VM's Edge window, then retry."
                elif reason.endswith("rdp_minimized."):
                    job.error += (
                        " The VM screen is not rendering: restore or reconnect the RDP"
                        " window (or run infra\\keep-session-alive.ps1), then retry."
                    )
            elif isinstance(exc, TimeoutError):
                job.error = "Retrieval timed out; see operator diagnostics."
            # Exception messages/tracebacks can contain patient data or model responses.
            logger.error("Retrieval job %s failed (%s)", job_id, type(exc).__name__)
            story("error", f"Stopped after {time.monotonic() - started:.0f} s · {job.error}")
            end()
            try:
                self._audit.write(
                    event="retrieval-finished", caller_id=caller_id,
                    patient_id=request.patient_id, job_id=job_id, outcome="failed",
                )
            except OSError:
                logger.error("Audit persistence failed for job %s", job_id)
            job.completed_at = datetime.now(timezone.utc)
            with self._idle:
                job.status = JobStatus.failed
                self._idle.notify_all()


def _observation_has_code(data: dict, codes: set[str]) -> bool:
    concepts = []
    root_code = data.get("code")
    if isinstance(root_code, dict):
        concepts.append(root_code)
    components = data.get("component")
    if isinstance(components, list):
        for component in components:
            if isinstance(component, dict) and isinstance(component.get("code"), dict):
                concepts.append(component["code"])
    for concept in concepts:
        codings = concept.get("coding")
        if not isinstance(codings, list):
            continue
        for coding in codings:
            if isinstance(coding, dict) and str(coding.get("code", "")) in codes:
                return True
    return False
