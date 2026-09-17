# Computer-Use Demos

Windows desktop simulators and companion AI agents for demonstrating visual
computer use in controlled environments.

## Demos

| Demo | Simulator | Agent task |
|---|---|---|
| [Plant Operations](demos/plant-operations/README.md) | .NET 8 WPF industrial control-room simulator | Investigate and stabilize a synthetic compressor alarm |
| [Epic Retrieval Agent](demos/epic-ehr/README.md) | Red-cross terminal, API, local files, and GPT Astra browser worker | Retrieve files or chart data as JSON, FHIR-style Bundles, or NDJSON; optional authenticated dev tunnel |

## Safety

- The public Epic adapter defaults to bundled synthetic fixtures.
- The Epic EHR demo is not affiliated with or endorsed by Epic Systems.
- Live Epic access is environment-specific and must be authorized by the
  healthcare organization operating the VM.
- Epic browser workflows are instructed to retrieve existing records only.
  A read-only Epic account is required: model instructions do not enforce permissions.
- Agents default to synthetic or dry-run mode.
- Live mouse and keyboard control requires `ALLOW_COMPUTER_CONTROL=1`.
- Screen capture fails closed unless the expected simulator window is present.
- Never use these agents with production systems, real patient data, or real
  industrial controls.

See [SECURITY.md](SECURITY.md) before running live automation.

## Prerequisites

- Windows 10 or later
- .NET 8 SDK for the plant simulator
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- An Azure AI Foundry project with a computer-use model deployment

## Build

```powershell
dotnet build .\computer-use-demos.slnx
$env:PYTHONPATH = (Resolve-Path .\demos\epic-ehr\service\src).Path
python -m unittest discover .\demos\epic-ehr\service\tests
```

Each demo has its own setup and walkthrough:

- `demos\plant-operations\README.md`
- `demos\epic-ehr\README.md`

## Repository layout

```text
demos/
  plant-operations/
    app/       Plant simulator
    agent/     Plant computer-use agent
  epic-ehr/
    service/   Terminal/API, Astra browser worker, local files, tunnel launcher, tests
    infra/     Azure VM and Bastion Bicep template
    launcher/  Separate version selector, installer, rollback, and desktop shortcut
    release/   Reproducible versioned release archive builder
    fixtures/  Synthetic patient and diagnostic-file metadata
docs/codebase/ Architecture and maintenance notes
scripts/       Optional local helper scripts
```
