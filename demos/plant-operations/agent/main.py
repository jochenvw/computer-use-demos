"""
SRE Operational Reliability Agent -- Scrolling Terminal UI

Usage:
    .venv\\Scripts\\python.exe main.py [--live] [--verbose] [--once]

Environment variables:
    AZURE_AI_FOUNDRY_ENDPOINT  (required)
    AZURE_API_KEY              (recommended)
    MODEL_DEPLOYMENT           (optional, default: computer-use-preview)
"""

import argparse
import time
import threading

import config
from agent import run, display
from memory import record_incident, get_incident_count

from rich.console import Console

console = Console()

# ---------------------------------------------------------------------------
# Emoji mapping for log lines
# ---------------------------------------------------------------------------

PHASE_EMOJI = {
    "idle": "💤",
    "waiting": "⏳",
    "scanning": "📸",
    "reasoning": "🧠",
    "acting": "⚡",
    "verifying": "🔍",
    "done": "✅",
    "error": "🔥",
}

BANNER = r"""[bold cyan]
   _____ ____  ______   ___                    __
  / ___// __ \/ ____/  /   | ____ ____  ____  / /_
  \__ \/ /_/ / __/    / /| |/ __ `/ _ \/ __ \/ __/
 ___/ / _, _/ /___   / ___ / /_/ /  __/ / / / /_
/____/_/ |_/_____/  /_/  |_\__, /\___/_/ /_/\__/
                          /____/
[/][dim]  North Sea Alpha · Operational Reliability Copilot[/]
"""


def _emoji_for(text: str) -> str:
    """Pick an emoji prefix based on log line content."""
    lower = text.lower()
    if "[thinking]" in lower:
        return "💭"
    if "[model]" in lower:
        return "💬"
    if "[action]" in lower:
        return "⚡"
    if "abort" in lower or "error" in lower:
        return "🔥"
    if "screenshot" in lower or "capturing" in lower:
        return "📸"
    if "sending" in lower or "model" in lower:
        return "🧠"
    if "step" in lower:
        return "👣"
    if "cycle" in lower:
        return "🔄"
    if "incident" in lower or "memory" in lower:
        return "📝"
    if "initializ" in lower:
        return "🔌"
    return "·"


def _style_for(text: str) -> str:
    """Pick a rich style based on log line content."""
    lower = text.lower()
    if "[thinking]" in lower:
        return "yellow"
    if "[model]" in lower:
        return "bold white"
    if "[action]" in lower:
        return "bold cyan"
    if "abort" in lower or "error" in lower:
        return "bold red"
    if "done" in lower or "all clear" in lower or "complete" in lower:
        return "bold green"
    return "dim"


# Track last printed index so we only print new log lines
_last_printed = 0


def flush_log():
    """Print any new event_log lines from the display state."""
    global _last_printed
    d = display
    while _last_printed < len(d.event_log):
        line = d.event_log[_last_printed]
        emoji = _emoji_for(line)
        style = _style_for(line)
        console.print(f"  {emoji} [{style}]{line}[/]")
        _last_printed += 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global _last_printed

    parser = argparse.ArgumentParser(
        description="SRE agent that monitors a plant manager UI and responds to alarms"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Execute actions in the local simulator (default is dry-run)",
    )
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    parser.add_argument("--once", action="store_true", help="Single check, no continuous monitoring")
    args = parser.parse_args()

    config.validate(live=args.live)

    console.print(BANNER)

    d = display
    d.max_steps = config.MAX_STEPS

    auth = "🔑 API Key" if config.AZURE_API_KEY else "🆔 Entra ID"
    dry_run = not args.live
    mode = "🧪 DRY RUN" if dry_run else "🟢 LIVE"
    mem = get_incident_count()
    console.print(f"  [dim]Endpoint:[/]  {config.AZURE_AI_FOUNDRY_ENDPOINT[:60]}")
    console.print(f"  [dim]Model:[/]     {config.MODEL_DEPLOYMENT}")
    console.print(f"  [dim]Auth:[/]      {auth}")
    console.print(f"  [dim]Memory:[/]    📝 {mem} past incident(s)")
    console.print(f"  [dim]Mode:[/]      {mode}")
    console.print()

    cycle = 0
    agent_thread = None
    agent_result = [None]
    agent_error = [None]

    def _run_agent():
        try:
            agent_result[0] = run(dry_run=dry_run, verbose=args.verbose)
        except Exception as exc:
            agent_error[0] = str(exc)
            d.phase = "error"
            d.error = str(exc)
            d.log(f"ERROR: {exc}")

    try:
        while True:
            cycle += 1
            d.cycle = cycle
            d.phase = "idle"
            d.step = 0
            d.param_changes = 0
            d.reasoning = []
            d.messages = []
            d.error = ""
            d.last_action = ""
            d.summary_text = ""
            agent_result[0] = None
            agent_error[0] = None

            # Countdown
            phase_emoji = PHASE_EMOJI["waiting"]
            console.print(f"\n  {phase_emoji} [dim]Next scan in {config.POLL_INTERVAL}s...[/]")
            for remaining in range(config.POLL_INTERVAL, 0, -1):
                d.countdown = remaining
                d.phase = "waiting"
                time.sleep(1)

            d.countdown = 0
            d.phase = "scanning"
            console.print(f"\n  🔄 [bold cyan]━━━ Cycle {cycle} ━━━[/]")
            d.log(f"Cycle {cycle}: starting scan...")

            # Run agent in thread, flush log lines as they appear
            agent_thread = threading.Thread(target=_run_agent, daemon=True)
            agent_thread.start()

            while agent_thread.is_alive():
                flush_log()
                time.sleep(0.3)

            agent_thread.join()
            flush_log()

            # Record incident
            if agent_result[0]:
                record_incident(agent_result[0])
                steps = agent_result[0].get("steps_taken", 0)
                if steps > 0:
                    console.print(f"  ✅ [bold green]Done — {steps} action(s)[/]")
                else:
                    console.print(f"  ✅ [green]All clear[/]")

            if agent_error[0]:
                console.print(f"  🔥 [bold red]Error — will retry[/]")

            if args.once:
                console.print(f"\n  👋 [dim]Single check complete.[/]")
                break

    except KeyboardInterrupt:
        console.print(f"\n  👋 [dim]Interrupted. Bye![/]")


if __name__ == "__main__":
    main()
