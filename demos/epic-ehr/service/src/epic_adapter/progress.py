"""Console and per-job timeline events.

`emit` is the terse technical log. `story` is a short, human-readable line for
the visible demo console and the job timeline (for clinicians following along).
Story text can include model reasoning and observed values; it is shown only on
the VM console and to the authenticated job owner.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("epic_adapter.progress")

KINDS = ("start", "step", "query", "thinking", "agent", "result", "done", "warn", "error", "info")
_MAX_EVENTS = 300
_MAX_TEXT = 700

_lock = threading.Lock()
_timeline: list[dict] | None = None
_started = 0.0
_state: dict = {"job": None, "label": "", "since": 0.0}


def emit(message: str) -> None:
    logger.info(message)


def begin(timeline: list[dict], label: str = "", job_id: str = "") -> None:
    global _timeline, _started
    with _lock:
        _timeline = timeline
        _started = time.monotonic()
        _state.update(job=job_id, label=label, since=_started)


def end() -> None:
    global _timeline
    with _lock:
        _timeline = None
        _state.update(job=None, label="", since=0.0)


def current() -> dict:
    """Snapshot for the console header: active job label and elapsed seconds."""
    with _lock:
        if not _state["job"]:
            return {"job": None}
        return {
            "job": _state["job"], "label": _state["label"],
            "elapsed": time.monotonic() - _state["since"],
        }


def story(kind: str, text: str) -> None:
    kind = kind if kind in KINDS else "info"
    text = " ".join(str(text).split())
    if len(text) > _MAX_TEXT:
        text = text[: _MAX_TEXT - 1] + "…"
    if not text:
        return
    logger.info(text, extra={"story": kind})
    with _lock:
        if _timeline is not None and len(_timeline) < _MAX_EVENTS:
            _timeline.append({
                "t": round(time.monotonic() - _started, 1), "kind": kind, "text": text,
            })
