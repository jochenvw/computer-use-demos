"""
Core orchestration loop for the SRE reliability agent.

Captures screenshots, sends them to Azure AI Foundry's computer-use-preview
model via the Responses API, interprets the model's output (computer_call
actions or final text), executes UI actions, and repeats until the goal is
achieved or safety limits are reached.
"""

import json
import time
from dataclasses import dataclass, field

import config
from screen import capture
from executor import execute
from state import TaskState
from prompts import build_system_prompt, build_task_prompt


# ---------------------------------------------------------------------------
# Live display state -- shared with the TUI in main.py
# ---------------------------------------------------------------------------

@dataclass
class DisplayState:
    """Mutable state object that the TUI reads to render the dashboard."""
    cycle: int = 0
    phase: str = "idle"             # idle, scanning, reasoning, acting, verifying, done, error, waiting
    step: int = 0
    max_steps: int = 15
    param_changes: int = 0
    countdown: int = 0
    last_action: str = ""
    reasoning: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    event_log: list[str] = field(default_factory=list)
    summary_text: str = "Initializing..."
    error: str = ""

    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.event_log.append(f"[{ts}] {msg}")
        if len(self.event_log) > 100:
            self.event_log = self.event_log[-100:]

    def set_reasoning(self, lines: list[str]):
        self.reasoning = lines[-10:] if lines else []

    def set_messages(self, lines: list[str]):
        self.messages = lines[-6:] if lines else []


# Global display state
display = DisplayState()


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _get_client():
    """Build an OpenAI client for the Responses API."""
    if config.AZURE_API_KEY:
        from openai import OpenAI
        base_url = config.AZURE_AI_FOUNDRY_ENDPOINT.rstrip("/") + "/openai/v1/"
        return OpenAI(api_key=config.AZURE_API_KEY, base_url=base_url)
    else:
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        project = AIProjectClient(
            endpoint=config.AZURE_AI_FOUNDRY_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
        return project.get_openai_client()


def _extract_computer_calls(response) -> list:
    """Extract computer_call items from the response output."""
    calls = []
    for item in response.output:
        if item.type == "computer_call":
            calls.append(item)
    return calls


def _extract_text(response) -> str | None:
    """Extract final text output from the response."""
    texts = []
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if hasattr(part, "text"):
                    texts.append(part.text)
    return "\n".join(texts) if texts else None


def _build_screenshot_input(data_uri: str) -> dict:
    """Build an image input item for the Responses API using a data URI."""
    return {
        "type": "input_image",
        "image_url": data_uri,
    }


def _build_computer_call_output(call_id: str, data_uri: str) -> dict:
    """Build a computer_call_output item to send back after executing an action."""
    return {
        "type": "computer_call_output",
        "call_id": call_id,
        "output": {
            "type": "computer_screenshot",
            "image_url": data_uri,
        },
    }


def _extract_reasoning_text(response) -> list[str]:
    """Extract all reasoning and thinking text from the response."""
    lines = []
    for item in response.output:
        if item.type == "reasoning":
            # Summary lines
            for summary in (item.summary or []):
                text = getattr(summary, "text", None)
                if text:
                    lines.append(text)
            # Content lines (may contain the actual reasoning)
            for content in (item.content or []):
                text = getattr(content, "text", None)
                if text:
                    lines.append(text)
    return lines


def _extract_all_text(response) -> list[str]:
    """Extract ALL text from the response: reasoning, messages, everything."""
    lines = []
    for item in response.output:
        if item.type == "reasoning":
            for summary in (item.summary or []):
                text = getattr(summary, "text", None)
                if text:
                    lines.append(f"[thinking] {text}")
            for content in (item.content or []):
                text = getattr(content, "text", None)
                if text:
                    lines.append(f"[thinking] {text}")
        elif item.type == "message":
            for part in item.content:
                text = getattr(part, "text", None)
                if text:
                    lines.append(f"[model] {text}")
        elif item.type == "computer_call":
            action = item.action
            if action:
                desc = action.type
                if hasattr(action, "x") and hasattr(action, "y"):
                    desc += f"({action.x}, {action.y})"
                elif hasattr(action, "text"):
                    desc += f"('{action.text[:30]}')"
                elif hasattr(action, "keys"):
                    desc += f"({action.keys})"
                lines.append(f"[action] {desc}")
    return lines


def run(dry_run: bool = True, verbose: bool = False) -> dict:
    """
    Run the SRE agent loop.

    Returns a summary dict with issue, actions taken, outcome, and step count.
    Updates display state throughout for the TUI.
    """
    config.validate(live=not dry_run)
    d = display

    # Initialize Azure client
    d.phase = "scanning"
    d.log("Initializing Azure AI client...")
    client = _get_client()

    # Computer-use tool definition (must match screenshot dimensions)
    from screen import _MODEL_WIDTH, _MODEL_HEIGHT
    computer_tool = {
        "type": "computer_use_preview",
        "display_width": _MODEL_WIDTH,
        "display_height": _MODEL_HEIGHT,
        "environment": config.ENVIRONMENT,
    }

    # State tracker
    state = TaskState(goal="Detect and respond to high compressor discharge temperature alarm")
    d.max_steps = config.MAX_STEPS

    # Action log
    action_log: list[dict] = []

    system_prompt = build_system_prompt()
    task_prompt = build_task_prompt()

    d.phase = "scanning"
    d.log("Capturing initial screenshot...")
    b64, _ = capture()

    # Build initial input: task text + screenshot
    initial_input = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": task_prompt},
                _build_screenshot_input(b64),
            ],
        }
    ]

    d.phase = "reasoning"
    d.last_action = "Sending screenshot to model..."
    d.log("Sending to model for initial analysis...")
    response = client.responses.create(
        model=config.MODEL_DEPLOYMENT,
        instructions=system_prompt,
        input=initial_input,
        tools=[computer_tool],
        truncation="auto",
        include=["reasoning.encrypted_content"],
    )

    previous_response_id = response.id

    # Main loop
    while not state.done:
        # Extract everything the model said and log it fully
        all_text = _extract_all_text(response)
        for line in all_text:
            d.log(line)

        # Update reasoning panel (thinking lines only)
        reasoning_lines = _extract_reasoning_text(response)
        d.set_reasoning(reasoning_lines)

        # Update messages panel (model text output)
        text_output = _extract_text(response)
        if text_output:
            d.set_messages(text_output.split("\n"))

        # Check for computer_call actions
        computer_calls = _extract_computer_calls(response)

        if not computer_calls:
            d.phase = "done"
            d.summary_text = text_output or "No actions needed"
            d.log("Model finished -- no more actions")
            state.mark_done("Model finished -- no more actions")
            break

        if dry_run:
            proposed_actions = []
            for call in computer_calls:
                actions = call.actions or ([call.action] if call.action else [])
                proposed_actions.extend(action.type for action in actions)
            d.phase = "done"
            d.summary_text = "Dry run proposed: " + ", ".join(proposed_actions)
            d.log(d.summary_text)
            return {
                "goal": "High Compressor Discharge Temperature response",
                "steps_taken": 0,
                "steps_limit": config.MAX_STEPS,
                "parameter_changes": 0,
                "done_reason": d.summary_text,
                "abort_reason": None,
                "actions": [],
                "proposed_actions": proposed_actions,
            }

        # Process each computer_call
        for call in computer_calls:
            if state.done or not state.is_within_limits():
                break

            call_id = call.call_id

            actions = []
            if call.actions:
                actions = call.actions
            elif call.action:
                actions = [call.action]

            for action in actions:
                if not state.is_within_limits():
                    d.phase = "error"
                    d.error = state.abort_reason or "Safety limit reached"
                    d.log(f"ABORT: {state.abort_reason}")
                    state.mark_done(f"Safety limit: {state.abort_reason}")
                    break

                d.phase = "acting"
                d.step = state.step_count + 1
                d.last_action = f"{action.type}"
                d.log(f"Step {d.step}: executing {action.type}")

                desc = execute(action)

                d.last_action = desc
                state.record_action(desc)
                action_log.append({
                    "step": state.step_count,
                    "action": action.type,
                    "description": desc,
                    "timestamp": time.strftime("%H:%M:%S"),
                })
                d.step = state.step_count
                d.param_changes = state.parameter_changes

                # Track parameter changes
                if action.type == "type" and hasattr(action, "text"):
                    text = action.text
                    if text in ("95.0", "95", "38.0", "38"):
                        state.record_parameter_change()
                        d.param_changes = state.parameter_changes

            # Capture new screenshot after actions
            d.phase = "scanning"
            d.log(f"Step {state.step_count}: capturing screenshot...")
            time.sleep(config.SCREENSHOT_DELAY)
            b64, _ = capture()

            # Check safety limits before next API call
            if not state.is_within_limits():
                d.phase = "error"
                d.error = state.abort_reason or "Safety limit reached"
                d.log(f"ABORT: {state.abort_reason}")
                state.mark_done(f"Safety limit: {state.abort_reason}")
                break

            # Send computer_call_output back to the model
            output_item = _build_computer_call_output(call_id, b64)

            d.phase = "reasoning"
            d.log(f"Step {state.step_count}: sending result to model...")
            response = client.responses.create(
                model=config.MODEL_DEPLOYMENT,
                previous_response_id=previous_response_id,
                input=[output_item],
                tools=[computer_tool],
                truncation="auto",
                include=["reasoning.encrypted_content"],
            )
            previous_response_id = response.id

    # Build summary
    summary = {
        "goal": "High Compressor Discharge Temperature response",
        "steps_taken": state.step_count,
        "steps_limit": config.MAX_STEPS,
        "parameter_changes": state.parameter_changes,
        "done_reason": state.current_goal,
        "abort_reason": state.abort_reason,
        "actions": action_log,
    }

    d.summary_text = state.current_goal
    return summary
