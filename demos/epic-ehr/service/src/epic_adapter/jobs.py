from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from .adapters.base import EhrAdapter
from .audit import AuditWriter
from .file_catalog import FileCatalog
from .models import ClinicalBundle, JobRecord, JobStatus, RetrievalRequest, RetrievalSource
from .progress import emit

logger = logging.getLogger(__name__)


class JobService:
    def __init__(
        self,
        adapter: EhrAdapter,
        file_catalog: FileCatalog,
        audit: AuditWriter,
    ) -> None:
        self._adapter = adapter
        self._file_catalog = file_catalog
        self._audit = audit
        self._jobs: dict[str, JobRecord] = {}
        self._gui_lock = threading.Lock()
        self._records_lock = threading.Lock()

    def create(self, request: RetrievalRequest, caller_id: str) -> JobRecord:
        job = JobRecord()
        with self._records_lock:
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
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise LookupError("Retrieval job was not found.") from exc

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
        try:
            with self._gui_lock:
                job.status = JobStatus.running
                emit(f"JOB {job_id[:8]}  running")
                resources = []
                files = []
                if request.source in {RetrievalSource.ehr, RetrievalSource.both}:
                    emit("EHR      retrieving requested chart resources")
                    resources = self._adapter.retrieve(
                        request.patient_id, request.resources
                    )
                if request.source in {RetrievalSource.files, RetrievalSource.both}:
                    emit("FILES    searching approved patient directories")
                    files = self._file_catalog.find(request.patient_id)
                    emit(f"FILES    found {len(files)} file(s)")
            bundle = ClinicalBundle(
                patient_id=request.patient_id, resources=resources, files=files,
            )
            self._audit.write(
                event="retrieval-finished", caller_id=caller_id,
                patient_id=request.patient_id, job_id=job_id, outcome="complete",
            )
            job.bundle = bundle
            job.completed_at = datetime.now(timezone.utc)
            job.status = JobStatus.complete
            emit(f"JOB {job_id[:8]}  complete / {len(resources)} resource(s), {len(files)} file(s)")
        except Exception as exc:
            job.error = "Retrieval failed. Contact the service operator with the job ID."
            # Exception messages/tracebacks can contain patient data or model responses.
            logger.error("Retrieval job %s failed (%s)", job_id, type(exc).__name__)
            try:
                self._audit.write(
                    event="retrieval-finished", caller_id=caller_id,
                    patient_id=request.patient_id, job_id=job_id, outcome="failed",
                )
            except OSError:
                logger.error("Audit persistence failed for job %s", job_id)
            job.completed_at = datetime.now(timezone.utc)
            job.status = JobStatus.failed
