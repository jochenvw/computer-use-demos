"""
Maintenance Advisor — Incident Pattern Monitor

A separate monitoring loop that watches the SRE agent's incident memory file
(memory.json) for changes.  When new incidents are recorded, it sends the full
history to GPT-5.4 for pattern analysis and determines whether preventive
maintenance should be scheduled.

Usage:
    .venv\\Scripts\\python.exe maintenance_advisor.py

Environment variables (same .env as the SRE agent):
    AZURE_AI_FOUNDRY_ENDPOINT  (required)
    AZURE_API_KEY              (recommended)
"""

import json
import os
import sys
import time
from datetime import datetime

from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.live import Live
from rich.layout import Layout
from rich.align import Align
from rich import box

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(_DIR, "memory.json")
POLL_INTERVAL = 5  # seconds between file checks
MODEL_DEPLOYMENT = "gpt-5.4"

console = Console()

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

BANNER = r"""[bold magenta]
  __  __       _       _                                       
 |  \/  | __ _(_)_ __ | |_ ___ _ __   __ _ _ __   ___ ___     
 | |\/| |/ _` | | '_ \| __/ _ \ '_ \ / _` | '_ \ / __/ _ \    
 | |  | | (_| | | | | | ||  __/ | | | (_| | | | | (_|  __/    
 |_|  |_|\__,_|_|_| |_|\__\___|_| |_|\__,_|_| |_|\___\___|    
     _       _       _                                         
    / \   __| |_   _(_)___  ___  _ __                          
   / _ \ / _` \ \ / / / __|/ _ \| '__|                         
  / ___ \ (_| |\ V /| \__ \ (_) | |                            
 /_/   \_\__,_| \_/ |_|___/\___/|_|                            
[/][dim]  North Sea Alpha · Predictive Maintenance Intelligence[/]
"""

# ---------------------------------------------------------------------------
# Analysis prompt
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """\
You are a senior maintenance engineer and reliability analyst for an offshore
oil & gas platform (North Sea Alpha).  You review incident logs produced by an
automated SRE agent that monitors the plant's control systems.

Your job:
1. Look for PATTERNS — recurring alarms, repeated corrective actions, or
   escalating severity that suggest an underlying equipment problem.
2. Decide whether PREVENTIVE MAINTENANCE should be recommended.
3. A single, isolated incident is NOT grounds for maintenance — only repeating
   or escalating patterns warrant action.

Output format (use exactly these section headers):

## Pattern Analysis
Describe any patterns you see.  Be specific: which alarms repeat, how often,
what actions the agent took each time.

## Risk Assessment
Rate the risk: LOW / MEDIUM / HIGH / CRITICAL
Explain why.

## Recommendation
One of:
- ✅ NO ACTION — Isolated incident, continue monitoring.
- ⚠️  MONITOR — Pattern emerging, increase monitoring frequency.
- 🔧 SCHEDULE MAINTENANCE — Clear recurring pattern, schedule preventive work.
- 🚨 URGENT MAINTENANCE — Escalating or critical pattern, act immediately.

Include a one-line summary of what maintenance is needed (or why none is).

## Details
Bullet-point the specific evidence from the incident log that supports your
recommendation.
"""


# ---------------------------------------------------------------------------
# Azure OpenAI client
# ---------------------------------------------------------------------------

def _get_client() -> OpenAI:
    """Build an OpenAI client pointing at Azure AI Foundry."""
    endpoint = os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT", "")
    api_key = os.environ.get("AZURE_API_KEY", "")

    if not endpoint:
        console.print("[bold red]ERROR: AZURE_AI_FOUNDRY_ENDPOINT not set.[/]")
        sys.exit(1)

    if api_key:
        base_url = endpoint.rstrip("/") + "/openai/v1/"
        return OpenAI(api_key=api_key, base_url=base_url)
    else:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        project = AIProjectClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
        )
        return project.get_openai_client()


# ---------------------------------------------------------------------------
# Memory file helpers
# ---------------------------------------------------------------------------

def _load_memory() -> list[dict]:
    """Load the incident memory file."""
    if not os.path.exists(MEMORY_FILE):
        return []
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _file_mtime() -> float:
    """Return the modification time of the memory file, or 0."""
    try:
        return os.path.getmtime(MEMORY_FILE)
    except OSError:
        return 0.0


def _format_incidents_for_prompt(incidents: list[dict]) -> str:
    """Format the incident list as text for the LLM."""
    if not incidents:
        return "(no incidents recorded)"

    lines = [f"Total incidents on record: {len(incidents)}\n"]
    for i, inc in enumerate(incidents, 1):
        ts = inc.get("timestamp", "unknown")
        goal = inc.get("goal", "unknown")
        steps = inc.get("steps_taken", 0)
        changes = inc.get("parameter_changes", 0)
        reason = inc.get("done_reason", "")
        abort = inc.get("abort_reason")
        actions = inc.get("actions", [])

        lines.append(f"--- Incident #{i} [{ts}] ---")
        lines.append(f"  Alarm/Goal: {goal}")
        lines.append(f"  Steps taken: {steps}")
        lines.append(f"  Parameter changes: {changes}")
        lines.append(f"  Outcome: {reason}")
        if abort:
            lines.append(f"  Abort reason: {abort}")
        if actions:
            lines.append(f"  Actions:")
            for a in actions:
                lines.append(f"    - {a.get('action', '?')}: {a.get('description', '')}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _render_status_panel(status: str, incident_count: int, last_check: str) -> Panel:
    """Render the live status panel."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()

    table.add_row("Status", f"[bold]{status}[/]")
    table.add_row("Memory file", MEMORY_FILE)
    table.add_row("Incidents", f"[cyan]{incident_count}[/]")
    table.add_row("Last check", last_check)
    table.add_row("Model", f"[green]{MODEL_DEPLOYMENT}[/]")

    return Panel(table, title="[bold magenta]📡 Advisor Status[/]", border_style="magenta", box=box.ROUNDED)


def _render_analysis(analysis_text: str, incident_count: int, timestamp: str) -> Panel:
    """Render the GPT analysis as a styled panel."""
    # Color-code the recommendation line
    styled = analysis_text
    if "🚨 URGENT" in analysis_text:
        border = "bold red"
        title_emoji = "🚨"
    elif "🔧 SCHEDULE" in analysis_text:
        border = "bold yellow"
        title_emoji = "🔧"
    elif "⚠️" in analysis_text or "MONITOR" in analysis_text:
        border = "yellow"
        title_emoji = "⚠️"
    else:
        border = "green"
        title_emoji = "✅"

    return Panel(
        styled,
        title=f"[bold]{title_emoji} Analysis — {incident_count} incident(s) — {timestamp}[/]",
        border_style=border,
        box=box.DOUBLE,
        padding=(1, 2),
    )


def _render_waiting_animation(frame: int) -> str:
    """Simple spinner animation for the watching state."""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    return frames[frame % len(frames)]


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze_incidents(client: OpenAI, incidents: list[dict]) -> str:
    """Send incident history to GPT-5.4 and return the analysis."""
    incident_text = _format_incidents_for_prompt(incidents)

    user_message = (
        "Here is the current incident log from the SRE agent. "
        "Analyze the incidents for patterns and determine whether "
        "preventive maintenance should be recommended.\n\n"
        f"{incident_text}"
    )

    response = client.chat.completions.create(
        model=MODEL_DEPLOYMENT,
        messages=[
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        max_completion_tokens=1500,
    )

    return response.choices[0].message.content or "(no analysis returned)"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    console.print(BANNER)

    # Show config
    endpoint = os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT", "(not set)")
    auth = "🔑 API Key" if os.environ.get("AZURE_API_KEY") else "🆔 Entra ID"
    console.print(f"  [dim]Endpoint:[/]  {endpoint[:60]}")
    console.print(f"  [dim]Model:[/]     {MODEL_DEPLOYMENT}")
    console.print(f"  [dim]Auth:[/]      {auth}")
    console.print(f"  [dim]Watching:[/]  {MEMORY_FILE}")
    console.print()

    client = _get_client()
    console.print("  [green]✓[/] [dim]Connected to Azure AI Foundry[/]\n")

    last_mtime = _file_mtime()
    last_count = len(_load_memory())
    analysis_count = 0
    frame = 0

    # If there are already incidents, do an initial analysis
    if last_count > 0:
        console.print(
            Rule(f"[bold magenta]📋 Initial Analysis — {last_count} existing incident(s)[/]", style="magenta")
        )
        console.print(f"  [dim]Sending {last_count} incident(s) to {MODEL_DEPLOYMENT} for analysis...[/]\n")
        try:
            incidents = _load_memory()
            result = analyze_incidents(client, incidents)
            analysis_count += 1
            ts = datetime.now().strftime("%H:%M:%S")
            console.print(_render_analysis(result, len(incidents), ts))
        except Exception as exc:
            console.print(f"  [bold red]Analysis error:[/] {exc}\n")

    console.print(Rule("[bold magenta]👁️  Watching for new incidents[/]", style="magenta"))
    console.print(f"  [dim]Polling memory.json every {POLL_INTERVAL}s — press Ctrl+C to stop[/]\n")

    try:
        while True:
            current_mtime = _file_mtime()
            current_count = len(_load_memory())
            now = datetime.now().strftime("%H:%M:%S")

            if current_mtime != last_mtime and current_count != last_count:
                new_incidents = current_count - last_count
                last_mtime = current_mtime
                last_count = current_count

                console.print(
                    f"\n  [bold cyan]🔔 Change detected![/] "
                    f"[dim]{now}[/] — "
                    f"[cyan]+{new_incidents} new incident(s)[/] "
                    f"[dim](total: {current_count})[/]"
                )

                console.print(
                    f"  [dim]Analyzing {current_count} incident(s) with {MODEL_DEPLOYMENT}...[/]\n"
                )

                try:
                    incidents = _load_memory()
                    result = analyze_incidents(client, incidents)
                    analysis_count += 1
                    ts = datetime.now().strftime("%H:%M:%S")
                    console.print(_render_analysis(result, len(incidents), ts))
                    console.print()
                except Exception as exc:
                    console.print(f"  [bold red]Analysis error:[/] {exc}\n")

            elif current_mtime != last_mtime:
                # File changed but count didn't — might be a rewrite
                last_mtime = current_mtime
                last_count = current_count

            # Watching animation
            spinner = _render_waiting_animation(frame)
            frame += 1
            console.print(
                f"  {spinner} [dim]Watching... {now} · "
                f"{last_count} incident(s) · "
                f"{analysis_count} analysis run(s)[/]",
                end="\r",
            )

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        console.print(f"\n\n  👋 [dim]Maintenance Advisor stopped. Goodbye![/]\n")


if __name__ == "__main__":
    main()
