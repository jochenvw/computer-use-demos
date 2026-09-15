from __future__ import annotations

import hashlib
import mimetypes
import re
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
        resolved = Path(record.path).resolve(strict=True)
        if not any(
            (root / patient_id).resolve() in resolved.parents
            and root in (root / patient_id).resolve().parents
            for root in self._roots
        ):
            raise RuntimeError("File no longer belongs to an approved patient directory.")
        digest = hashlib.sha256()
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != record.sha256:
            raise RuntimeError("File changed after retrieval; request a new job.")
        return resolved
