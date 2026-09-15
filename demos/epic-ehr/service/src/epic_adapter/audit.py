from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


class AuditWriter:
    def __init__(self, path: Path) -> None:
        self._path = path

    def write(
        self,
        *,
        event: str,
        caller_id: str,
        patient_id: str,
        job_id: str,
        outcome: str,
    ) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "caller_id": caller_id,
            "patient_hash": hashlib.sha256(patient_id.encode("utf-8")).hexdigest(),
            "job_id": job_id,
            "outcome": outcome,
        }
        with self._path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
