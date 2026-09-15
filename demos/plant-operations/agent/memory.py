"""
Persistent incident memory for the SRE agent.

Stores a JSON log of past incidents so the agent can detect recurring
patterns and recommend maintenance. File is append-only and survives
across agent restarts.
"""

import json
import os
import time

_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")


def _load() -> list[dict]:
    """Load the incident log from disk."""
    if not os.path.exists(_MEMORY_FILE):
        return []
    try:
        with open(_MEMORY_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(incidents: list[dict]):
    """Write the incident log to disk."""
    with open(_MEMORY_FILE, "w") as f:
        json.dump(incidents, f, indent=2)


def record_incident(summary: dict):
    """Append an incident from an agent run to the memory file.

    Only records runs where the agent actually took action (steps > 0).
    """
    if summary.get("steps_taken", 0) == 0:
        return

    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "goal": summary.get("goal", ""),
        "steps_taken": summary.get("steps_taken", 0),
        "parameter_changes": summary.get("parameter_changes", 0),
        "done_reason": summary.get("done_reason", ""),
        "abort_reason": summary.get("abort_reason"),
        "actions": [
            {"action": a["action"], "description": a["description"]}
            for a in summary.get("actions", [])
        ],
    }

    incidents = _load()
    incidents.append(entry)
    _save(incidents)
    print(f"  [memory] Incident #{len(incidents)} recorded.")


def format_history_for_prompt(max_recent: int = 10) -> str:
    """Format recent incident history as text for the system prompt.

    Returns empty string if no history exists.
    """
    incidents = _load()
    if not incidents:
        return ""

    recent = incidents[-max_recent:]
    total = len(incidents)

    # Count recurring alarm types
    alarm_counts: dict[str, int] = {}
    for inc in incidents:
        goal = inc.get("goal", "unknown")
        alarm_counts[goal] = alarm_counts.get(goal, 0) + 1

    lines = [
        f"INCIDENT HISTORY ({total} total incident(s) on record):",
        "",
    ]

    # Flag recurring issues
    for alarm, count in alarm_counts.items():
        if count >= 3:
            lines.append(
                f"  !! RECURRING: '{alarm}' has occurred {count} times. "
                f"Consider recommending preventive maintenance."
            )
        elif count >= 2:
            lines.append(
                f"  ! REPEAT: '{alarm}' has occurred {count} times. Monitor closely."
            )
    lines.append("")

    # Recent incidents
    lines.append(f"Last {len(recent)} incident(s):")
    for inc in recent:
        ts = inc.get("timestamp", "?")
        steps = inc.get("steps_taken", 0)
        reason = inc.get("done_reason", "")
        actions_desc = ", ".join(
            a["description"] for a in inc.get("actions", [])[:3]
        )
        lines.append(f"  [{ts}] steps={steps}, result='{reason}'")
        if actions_desc:
            lines.append(f"    actions: {actions_desc}")

    return "\n".join(lines)


def get_incident_count() -> int:
    """Return total number of recorded incidents."""
    return len(_load())
