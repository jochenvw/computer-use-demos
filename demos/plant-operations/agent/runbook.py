"""
Structured runbook (SOP-4017): High Compressor Discharge Temperature.

Provides the canonical corrective-action sequence for C-101 thermal exceedances
and a helper to render it as an LLM-ready text block.
"""

RUNBOOK = {
    "sop_id": "SOP-4017",
    "title": "High Compressor Discharge Temperature",
    "revision": "3.2",
    "effective_date": "2025-01-15",
    "symptoms": [
        "C-101 discharge temperature exceeds 155 °C (Warning) or 165 °C (Critical)",
        "Alarm tags: C101-DTEMP-HI (Warning), C101-DTEMP-HH (Critical)",
        "Plant stability score declining below 90",
        "Recommended action panel displays: 'Reduce feed rate by 5%, increase cooling target by 3 °C'",
    ],
    "probable_causes": [
        "Excessive feed rate driving compressor beyond thermal capacity",
        "Insufficient cooling — setpoint too low or heat exchanger fouling",
        "Recycle valve stuck in MANUAL-OPEN (gas not recirculating properly)",
        "Ambient temperature spike (seasonal, not directly controllable)",
    ],
    "corrective_actions": [
        {
            "step": 1,
            "action": "Reduce feed rate by 5%",
            "details": "Open 'Adjust Feed Rate' dialog → enter 95.0 → click Apply",
            "parameter": "feed_rate",
            "target_value": 95.0,
            "unit": "%",
        },
        {
            "step": 2,
            "action": "Increase cooling target by 3 °C",
            "details": "Open 'Set Cooling Target' dialog → enter 38.0 → click Apply",
            "parameter": "cooling_target",
            "target_value": 38.0,
            "unit": "°C",
        },
        {
            "step": 3,
            "action": "Verify recycle valve in AUTO",
            "details": "Check recycle valve state on Overview tab — if MANUAL-OPEN, toggle to AUTO",
        },
    ],
    "verification": [
        "C-101 discharge temperature declining below 160 °C",
        "Alarm downgrades from Critical to Warning, or clears entirely",
        "Stability score rising back above 90",
        "Recommended action changes to 'No action required — system stable'",
    ],
    "escalation": [
        "Temperature exceeds 180 °C → initiate compressor trip immediately",
        "Vibration exceeds 8.0 mm/s → emergency shutdown required",
        "No improvement after 5 minutes → escalate to shift supervisor",
    ],
}


def format_for_prompt() -> str:
    """Render the runbook as a readable text block for inclusion in an LLM system prompt."""
    r = RUNBOOK
    lines: list[str] = []

    lines.append(f"=== RUNBOOK {r['sop_id']} (rev {r['revision']}, {r['effective_date']}) ===")
    lines.append(f"Title: {r['title']}")
    lines.append("")

    lines.append("SYMPTOMS:")
    for item in r["symptoms"]:
        lines.append(f"  • {item}")
    lines.append("")

    lines.append("PROBABLE CAUSES:")
    for item in r["probable_causes"]:
        lines.append(f"  • {item}")
    lines.append("")

    lines.append("CORRECTIVE ACTIONS:")
    for ca in r["corrective_actions"]:
        target = ""
        if "parameter" in ca:
            target = f" [{ca['parameter']} → {ca['target_value']} {ca['unit']}]"
        lines.append(f"  {ca['step']}. {ca['action']}{target}")
        lines.append(f"     {ca['details']}")
    lines.append("")

    lines.append("VERIFICATION:")
    for item in r["verification"]:
        lines.append(f"  • {item}")
    lines.append("")

    lines.append("ESCALATION:")
    for item in r["escalation"]:
        lines.append(f"  ⚠ {item}")

    return "\n".join(lines)
