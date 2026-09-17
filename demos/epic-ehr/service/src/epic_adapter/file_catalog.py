from __future__ import annotations

import hashlib
import mimetypes
import re
from io import BytesIO
from pathlib import Path

from .models import FileRecord

ALLOWED_EXTENSIONS = {
    ".dcm": "application/dicom",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".scp": "application/scp-ecg",
    ".xml": "application/xml",
}
SAFE_PATIENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_SKILL_READ_BYTES = 4 * 1024 * 1024
MAX_PDF_PAGES = 50
MAX_SKILL_TEXT_CHARS = 100_000


class FileCatalog:
    def __init__(self, roots: tuple[Path, ...]) -> None:
        self._roots = tuple(root.resolve() for root in roots)

    def find(self, patient_id: str) -> list[FileRecord]:
        if not SAFE_PATIENT_ID.fullmatch(patient_id):
            raise ValueError("patient_id contains unsupported characters.")

        records: list[FileRecord] = []
        for root in self._roots:
            if not root.is_dir():
                raise RuntimeError("An approved file root is missing or inaccessible.")
            patient_root = (root / patient_id).resolve()
            if root not in patient_root.parents:
                raise ValueError("Patient directory escaped the approved root.")
            if not patient_root.is_dir():
                continue
            for path in sorted(patient_root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
                    continue
                resolved = path.resolve()
                if patient_root not in resolved.parents:
                    raise ValueError("A file link escaped the patient directory.")
                digest = hashlib.sha256()
                with resolved.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                records.append(
                    FileRecord(
                        name=resolved.name,
                        media_type=ALLOWED_EXTENSIONS.get(
                            resolved.suffix.lower()
                        ) or mimetypes.guess_type(resolved.name)[0]
                        or "application/octet-stream",
                        size_bytes=resolved.stat().st_size,
                        sha256=digest.hexdigest(),
                        path=str(resolved),
                    )
                )
        return records

    def verify(self, record: FileRecord, patient_id: str) -> Path:
        """Recheck containment and content before serving a previously cataloged file."""
        resolved = self._contained_path(record, patient_id)
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != record.sha256:
            raise RuntimeError("File changed after retrieval; request a new job.")
        return resolved

    def _contained_path(self, record: FileRecord, patient_id: str) -> Path:
        resolved = Path(record.path).resolve(strict=True)
        if any(
            (root / patient_id).resolve() in resolved.parents
            and root in (root / patient_id).resolve().parents
            for root in self._roots
        ):
            return resolved
        raise RuntimeError("File no longer belongs to an approved patient directory.")

    def open_for_skill(self, record: FileRecord, patient_id: str) -> tuple[str | None, bytes | None]:
        path = self._contained_path(record, patient_id)
        with path.open("rb") as stream:
            data = stream.read(MAX_SKILL_READ_BYTES + 1)
        if len(data) > MAX_SKILL_READ_BYTES:
            raise ValueError("File exceeds the skill's 4 MiB read limit; original download is available.")
        if hashlib.sha256(data).hexdigest() != record.sha256:
            raise RuntimeError("File changed while being opened.")
        if record.media_type in {"image/png", "image/jpeg"}:
            return None, data
        if record.media_type in {"application/json", "application/xml"}:
            text = data.decode("utf-8-sig")
        elif record.media_type == "application/pdf":
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted or len(reader.pages) > MAX_PDF_PAGES:
                raise ValueError("Encrypted PDFs and PDFs over 50 pages are not supported.")
            text = "\n".join(page.extract_text() for page in reader.pages)
            if not text.strip():
                raise ValueError("PDF has no extractable text; OCR is not implemented.")
        else:
            return None, None
        if len(text) > MAX_SKILL_TEXT_CHARS:
            raise ValueError("Document text exceeds the skill read limit.")
        return text, None
