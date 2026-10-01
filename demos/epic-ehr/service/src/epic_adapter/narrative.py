"""Readable one-liners for clinicians watching the demo (console + timeline)."""

from __future__ import annotations

from typing import Any

from .models import ClinicalResource, ResourceType

STOP_REASONS = {
    "session_expired": "the EMR session has expired – please sign in again",
    "rdp_minimized": "the remote desktop window is minimized or disconnected, so the screen cannot be used",
}


def describe_step(skill: str, name: str, values: dict[str, Any], files: dict | None = None,
                  first_observe: bool = False) -> tuple[str, str] | None:
    """Return (kind, text) for a tool call, or None when nothing useful to say."""
    if name == "finish":
        return "step", "Checking the collected data against the request"
    if name == "stop":
        reason = str(values.get("reason", ""))
        return "warn", "Agent stopped: " + STOP_REASONS.get(reason, reason.replace("_", " "))
    if name == "list_patient_files":
        return "step", "Searching the approved clinical file folders on this workstation"
    if name == "open_patient_file":
        record = (files or {}).get(values.get("file_id"))
        label = f"'{record.name}'" if record is not None else "a file"
        return "step", f"Opening {label} on screen and reading it with vision"
    if name == "run_query":
        sql = " ".join(str(values.get("sql", "")).split())
        return "query", f"Writing and running SQL in SSMS: {sql}"
    surface = {"sql-desktop": "SSMS", "pacs-viewer": "PACS"}.get(skill, "the EMR")
    if name == "observe":
        if skill == "sql-desktop" and first_observe:
            return "step", "Opening SQL Server Management Studio on database OncologiaDemo"
        return "step", f"Looking at the screen in {surface}"
    if name == "click":
        return "step", f"Clicking in {surface} to navigate"
    if name == "scroll":
        direction = "down" if int(values.get("delta_y", 0)) >= 0 else "up"
        return "step", f"Scrolling {direction} in {surface} to see more"
    if name == "press_key":
        return "step", f"Pressing {values.get('key')} in {surface}"
    if name == "type_text":
        return "step", "Typing the patient name or identifier into the search box"
    return None


def _concept(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    if value.get("text"):
        return str(value["text"])
    for coding in value.get("coding") or []:
        if isinstance(coding, dict) and (coding.get("display") or coding.get("code")):
            return str(coding.get("display") or coding.get("code"))
    return ""


def _value(data: dict) -> str:
    quantity = data.get("valueQuantity")
    if isinstance(quantity, dict) and quantity.get("value") is not None:
        unit = quantity.get("unit") or quantity.get("code") or ""
        return f"{quantity['value']} {unit}".strip()
    for key in ("valueString", "valueInteger", "valueBoolean"):
        if data.get(key) is not None:
            return str(data[key])
    concept = _concept(data.get("valueCodeableConcept"))
    if concept:
        return concept
    parts = []
    for component in data.get("component") or []:
        if isinstance(component, dict):
            parts.append(f"{_concept(component.get('code'))} {_value(component)}".strip())
    return ", ".join(part for part in parts if part)


def summarize(resource: ClinicalResource) -> str:
    data = resource.data
    kind = resource.resource_type
    if kind == ResourceType.patient:
        name = ""
        for entry in data.get("name") or []:
            if isinstance(entry, dict):
                name = entry.get("text") or " ".join(
                    [*(entry.get("given") or []), entry.get("family") or ""]
                ).strip()
                if name:
                    break
        bits = [name or resource.source_id, data.get("gender"), data.get("birthDate")]
        return "Patient: " + " · ".join(str(bit) for bit in bits if bit)
    if kind == ResourceType.observations:
        label = _concept(data.get("code")) or resource.source_id
        when = str(data.get("effectiveDateTime") or "")[:10]
        text = f"{label}: {_value(data) or 'see source'}"
        return f"{text} ({when})" if when else text
    if kind == ResourceType.imaging:
        study = _concept(data.get("code"))
        conclusion = str(data.get("conclusion") or "recorded")
        return f"Imaging report ({study}): {conclusion}" if study else f"Imaging report: {conclusion}"
    if kind == ResourceType.ecg:
        return "ECG report: " + str(data.get("conclusion") or _concept(data.get("code")) or "recorded")
    if kind == ResourceType.encounters:
        return "Encounter: " + (_concept((data.get("type") or [{}])[0]) or resource.source_id)
    if kind == ResourceType.documents:
        return "Document: " + str(data.get("description") or _concept(data.get("type")) or resource.source_id)
    return f"{kind.value}: {resource.source_id}"
