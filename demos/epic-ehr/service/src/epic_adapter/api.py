from __future__ import annotations

import secrets
import hashlib

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse, Response

from .adapters.computer_use import ComputerUseEpicAdapter
from .adapters.fixture import FixtureEpicAdapter
from .audit import AuditWriter
from .config import Settings
from .file_catalog import FileCatalog
from .formats import fhir_bundle, ndjson, normalized_json
from .jobs import JobService
from .models import JobStatus, OutputFormat, RetrievalRequest

settings = Settings.from_env()
settings.validate()
adapter = (
    ComputerUseEpicAdapter(settings)
    if settings.backend == "computer-use"
    else FixtureEpicAdapter(settings.fixture_root)
)
jobs = JobService(
    adapter=adapter,
    file_catalog=FileCatalog(settings.file_roots),
    audit=AuditWriter(settings.audit_path),
)
app = FastAPI(
    title="Epic EHR Data Adapter Demo",
    version="0.2.0",
    description="Read-only clinical data retrieval through an opaque backend.",
)


def authorize(
    authorization: str | None = Header(default=None),
) -> str:
    if not settings.bearer_token or settings.bearer_token.startswith("replace-"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured.",
        )
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        token, settings.bearer_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
        )
    # One trusted operator principal in the demo, not a spoofable caller header.
    return hashlib.sha256(settings.bearer_token.encode()).hexdigest()[:16]


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/retrieval-jobs", status_code=status.HTTP_202_ACCEPTED)
def create_job(
    payload: RetrievalRequest,
    request: Request,
    caller_id: str = Depends(authorize),
) -> dict[str, str]:
    try:
        job = jobs.create(payload, caller_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    # Relative URLs also work through a tunnel that rewrites Host/proxy headers.
    base = ""
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "status_url": f"{base}/v1/retrieval-jobs/{job.job_id}",
        "result_url": f"{base}/v1/retrieval-jobs/{job.job_id}/result",
    }


@app.get("/v1/retrieval-jobs/{job_id}")
def get_job(job_id: str, caller_id: str = Depends(authorize)) -> dict:
    del caller_id
    try:
        return jobs.get(job_id).model_dump(mode="json")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/retrieval-jobs/{job_id}/result")
def get_result(
    job_id: str,
    request: Request,
    output_format: OutputFormat = Query(
        default=OutputFormat.json, alias="format"
    ),
    caller_id: str = Depends(authorize),
) -> Response:
    del caller_id
    try:
        job = jobs.get(job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if job.status != JobStatus.complete or job.bundle is None:
        raise HTTPException(status_code=409, detail=f"Job is {job.status.value}.")

    base = f"/v1/retrieval-jobs/{job_id}"
    if output_format == OutputFormat.fhir:
        return JSONResponse(
            fhir_bundle(job.bundle, base),
            media_type="application/fhir+json",
        )
    if output_format == OutputFormat.ndjson:
        return Response(ndjson(job.bundle), media_type="application/x-ndjson")
    return JSONResponse(normalized_json(job.bundle, base))


@app.get("/v1/retrieval-jobs/{job_id}/files/{file_id}")
def get_file(
    job_id: str,
    file_id: str,
    caller_id: str = Depends(authorize),
) -> FileResponse:
    del caller_id
    try:
        path, media_type = jobs.file_path(job_id, file_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=409, detail="Retrieved file is no longer available.") from exc
    return FileResponse(path, media_type=media_type, filename=path.name)
