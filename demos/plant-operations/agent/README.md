# SRE Operational Reliability Agent

An SRE agent that monitors the local **North Sea Alpha — Plant Manager** WPF
simulator via screenshots, detects synthetic alarms, consults structured runbook
procedures, and proposes or executes corrective actions through UI automation.

The agent defaults to dry-run mode. It must never be used with a real industrial
control system.

## What It Does

The agent operates as a visual observer and operator. It captures screenshots of the running plant manager application, sends them to an AI model capable of interpreting UI elements, and receives back a sequence of mouse/keyboard actions to resolve alarms. It follows a structured standard operating procedure (SOP-4017) to adjust process parameters, acknowledge alarms, and verify that corrective actions have taken effect.

## Architecture

| Module | Purpose |
|---|---|
| `config.py` | Configuration and environment variables |
| `screen.py` | Screenshot capture and base64 encoding |
| `executor.py` | UI action execution via `pyautogui` |
| `state.py` | Task state tracking and safety limits |
| `runbook.py` | SOP-4017 structured procedure data |
| `prompts.py` | System and task prompts for the model |
| `agent.py` | Core orchestration loop (Responses API) |
| `main.py` | CLI entry point |
| `agent_card.py` | A2A agent card with skill definitions |
| `a2a_handler.py` | A2A task handler (bridges protocol to agent) |
| `a2a_server.py` | A2A HTTP server (uvicorn + starlette) |
| `serve.ps1` | A2A server launcher script |

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** package manager
- **Azure AI Foundry** resource with the `computer-use-preview` model deployed
- **Entra ID authentication** — run `az login` before starting the agent
- **Plant Manager simulator** running from `..\app`

## Setup

```bash
cd .\demos\plant-operations\agent
uv sync --locked --default-index https://pypi.org/simple
```

The manifest tracks tested stable SDK versions; `uv.lock` records the complete
dependency set. Prereleases are disabled. Setup uses `--locked` and public PyPI;
launch commands use `--frozen` so ambient index settings cannot rewrite the lock.
The PowerShell launchers use the existing virtual environment directly.
To refresh dependencies from public PyPI:

```powershell
uv lock --upgrade --default-index https://pypi.org/simple
uv sync --locked --default-index https://pypi.org/simple
uv run --frozen --no-sync python -m unittest discover -p "test_*.py" -v
```

The regression checks use in-process HTTP transports and synthetic images. They
exercise SDK client construction, Responses/chat serialization, and A2A discovery
and task completion without Azure credentials, model calls, or desktop actions.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `AZURE_AI_FOUNDRY_ENDPOINT` | **Yes** | Your Azure AI Foundry endpoint, e.g. `https://your-resource.services.ai.azure.com` |
| `MODEL_DEPLOYMENT` | No | Model deployment name (default: `computer-use-preview`) |

## Running

```powershell
# Set your endpoint
$env:AZURE_AI_FOUNDRY_ENDPOINT = "https://your-resource.services.ai.azure.com"

# Start the WPF app first, trigger Scenario 1, then:
uv run --frozen python main.py --once       # dry-run mode

$env:ALLOW_COMPUTER_CONTROL = "1"
uv run --frozen python main.py --once --live
uv run --frozen python main.py --once --live --verbose
```

## A2A Server Mode

The agent can also run as an A2A (Agent-to-Agent) protocol server, exposing a standard
agent card for discovery by Azure AI Foundry and other A2A-compatible agents.

### Starting the A2A Server

```powershell
# Configure endpoint
$env:AZURE_AI_FOUNDRY_ENDPOINT = "https://your-resource.services.ai.azure.com"

# Start the server
.\serve.ps1                          # default: port 10100
.\serve.ps1 -Port 8080               # custom port
```

The server binds to `127.0.0.1` by default and has no built-in authentication.
Do not expose it on a network without adding authentication and TLS.

Or directly:
```powershell
uv run --frozen python a2a_server.py --port 10100
```

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/.well-known/agent-card.json` | GET | A2A agent card (discovery) |
| `/.well-known/agent.json` | GET | Legacy discovery alias |
| `/` | POST | A2A 1.0 JSON-RPC (`SendMessage`, `GetTask`, etc.) |

The server uses the A2A SDK 1.x protobuf models and route builders. Native A2A 1.0
requests must send `A2A-Version: 1.0`; use `configuration.returnImmediately: false`
to wait for completion. A2A 0.3 JSON-RPC methods such as `message/send` remain
enabled through the SDK's compatibility adapter, including their existing
`configuration.blocking` option. Status updates and artifacts are awaited and
associated with an initial task, and active SDK tasks are drained on shutdown.

### Agent Card

The agent advertises three skills:

| Skill ID | Description |
|----------|-------------|
| `detect_plant_alarm` | Monitor the plant UI for critical alarms |
| `execute_corrective_action` | Apply SOP-guided corrective actions via UI automation |
| `verify_plant_stability` | Confirm plant has stabilized after intervention |

### Calling from Azure AI Foundry

Register this agent as an A2A endpoint in your Foundry project:
1. Add authentication and TLS in front of the A2A server.
2. Start it with an explicitly selected non-loopback bind address.
3. In Azure AI Foundry, add a connected agent pointing to the secured endpoint.
4. The orchestrator agent can discover skills via the agent card and send tasks.

## Demo Flow

Once launched against an active alarm scenario, the agent follows this sequence:

1. **Capture & observe** — Takes a screenshot, identifies alarm indicators on the dashboard
2. **Navigate to Alarms** — Clicks the Alarms tab, locates the critical alarm entry
3. **Open procedure** — Opens the related standard operating procedure (SOP-4017)
4. **Reduce feed rate** — Adjusts the feed rate to 95% via the parameter dialog
5. **Increase cooling target** — Sets cooling target to 38°C via the parameter dialog
6. **Acknowledge alarm** — Acknowledges the alarm with operator notes
7. **Verify** — Confirms the temperature trend is declining
8. **Report** — Outputs a summary of all actions taken and the final system state

## Safety Limits

| Constraint | Limit |
|---|---|
| Maximum steps per run | 15 |
| Maximum parameter changes | 2 |
| Repeated identical actions before abort | 3 |
| Live opt-in | `ALLOW_COMPUTER_CONTROL=1` and `--live` |
| Target window | Exact simulator title; no full-screen fallback |
| Manual override | `Ctrl+C` at any time |

## Example Output

```
╔═══════════════════════════════════════════════════════════════╗
║  SRE OPERATIONAL RELIABILITY AGENT                          ║
║  Target: North Sea Alpha — Plant Manager                    ║
║  Scenario: High Compressor Discharge Temperature            ║
╚═══════════════════════════════════════════════════════════════╝

=== SRE Agent Configuration ===
  Endpoint:             https://contoso.services.ai.azure.com
  Model:                computer-use-preview
  Display:              1400x900
  Dry run:              No
  Max steps:            15
  Max param changes:    2

[Step 0] 📸 Capturing initial screenshot...
[Step 0] 🔍 Sending to model for initial analysis...

[Step 1] 🖱️  Executing: click
  ⚡ click(x=450, y=62)
[Step 1] 📸 Capturing screenshot...
[Step 1] 🔍 Sending to model...

[Step 2] 🖱️  Executing: click
  ⚡ click(x=312, y=285)
[Step 2] 📸 Capturing screenshot...
[Step 2] 🔍 Sending to model...

[Step 3] 🖱️  Executing: click
  ⚡ click(x=780, y=340)
[Step 3] 📸 Capturing screenshot...
[Step 3] 🔍 Sending to model...

[Step 4] 🖱️  Executing: triple_click
  ⚡ triple_click(x=620, y=410)
[Step 4] ⌨️  Executing: type
  ⚡ type("95")
[Step 4] 📸 Capturing screenshot...
[Step 4] 🔍 Sending to model...
  ⚠️  Parameter change 1/2

[Step 5] 🖱️  Executing: click
  ⚡ click(x=700, y=450)
[Step 5] 📸 Capturing screenshot...
[Step 5] 🔍 Sending to model...
  ⚠️  Parameter change 2/2

[Step 6–11] ...

[Step 12] 🔍 Sending to model...
  ✅ Model reports: temperature declining, alarm acknowledged

[Done] 📋 Agent report:
  I detected a C101-DTEMP-HH critical alarm indicating high compressor
  discharge temperature at 142°C. Following SOP-4017, I reduced the feed
  rate to 95% and increased the cooling target to 38°C. The alarm was
  acknowledged with operator notes. Temperature is now trending downward
  at 138°C and continuing to decline.

═══════════════════════════════════════════════════════════════
  AGENT SUMMARY
═══════════════════════════════════════════════════════════════
  Goal:       High Compressor Discharge Temperature response
  Steps:      12/15
  Param Δ:    2
  Result:     Model finished — no more actions
═══════════════════════════════════════════════════════════════
```
