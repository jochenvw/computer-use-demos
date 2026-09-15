"""
Prompt construction for the SRE reliability agent.

Builds the system instructions and task message that guide the
computer-use-preview model through alarm detection, diagnosis,
corrective action, and verification.

Prompts are stored as standalone Markdown files for easy editing:
  - SYSTEM_PROMPT.md  — persona, operating rules, UI reference, runbook
  - TASK_PROMPT.md    — mission and step-by-step procedure
"""

import os
from runbook import format_for_prompt

_DIR = os.path.dirname(__file__)


def _load_prompt(filename: str) -> str:
    """Read a prompt markdown file from the agent directory."""
    path = os.path.join(_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_system_prompt() -> str:
    """Load SYSTEM_PROMPT.md and inject the runbook at the {{RUNBOOK}} placeholder."""
    raw = _load_prompt("SYSTEM_PROMPT.md")
    return raw.replace("{{RUNBOOK}}", format_for_prompt())


def build_system_prompt() -> str:
    """Return the full system prompt, including incident history if available."""
    from memory import format_history_for_prompt
    prompt = _load_system_prompt()
    history = format_history_for_prompt()
    if history:
        return prompt + "\n\n" + history + "\n\nUse this history to inform your analysis. If a recurring pattern is evident, recommend preventive maintenance in your report.\n"
    return prompt


def build_task_prompt() -> str:
    """Return the task prompt."""
    return _load_prompt("TASK_PROMPT.md")
