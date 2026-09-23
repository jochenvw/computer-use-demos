"""Private operator trace for one skill run: tool calls, errors, timings, screenshots.

Traces stay on the VM (operator-only) and are exposed only through the
authenticated admin endpoint. They are never returned in job error messages.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timezone
from pathlib import Path


class Trace:
    def __init__(self, root: Path | None, skill: str) -> None:
        self._started = time.monotonic()
        self._path = None
        self._shots = None
        if root is None:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        run = root / f"{stamp}-{skill}"
        run.mkdir(parents=True, exist_ok=True)
        self._path = run / "trace.jsonl"
        self._shots = run
        self.event("start", skill=skill)

    def event(self, kind: str, /, **fields) -> None:
        if self._path is None:
            return
        record = {"t": round(time.monotonic() - self._started, 2), "event": kind, **fields}
        with self._path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, default=str) + "\n")

    def screenshot(self, step: int, data_url: str) -> None:
        if self._shots is None:
            return
        try:
            (self._shots / f"step-{step:03d}.jpg").write_bytes(
                base64.b64decode(data_url.split(",", 1)[1])
            )
        except (OSError, ValueError, IndexError):
            pass


def latest(root: Path | None, count: int = 1) -> list[dict]:
    if root is None or not root.is_dir():
        return []
    runs = sorted((p for p in root.iterdir() if p.is_dir()), reverse=True)[:count]
    output = []
    for run in runs:
        trace = run / "trace.jsonl"
        events = []
        if trace.is_file():
            for line in trace.read_text(encoding="utf-8").splitlines()[-200:]:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
        output.append({
            "run": run.name,
            "screenshots": sorted(p.name for p in run.glob("step-*.jpg")),
            "events": events,
        })
    return output
