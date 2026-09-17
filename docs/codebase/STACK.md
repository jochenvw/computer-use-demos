# Technology Stack

## Core Sections (Required)

### 1) Runtime Summary

| Area | Value | Evidence |
|------|-------|----------|
| Primary languages | Python, C#, Bicep | `demos/epic-ehr/service/pyproject.toml`, `demos/plant-operations/app/plant_manager.csproj`, `demos/epic-ehr/infra/main.bicep` |
| Desktop runtime | .NET 8 for Windows with WPF (plant demo) | `demos/plant-operations/app/plant_manager.csproj` |
| API runtime | Python 3.11+ with FastAPI | `demos/epic-ehr/service/pyproject.toml` |
| Package managers | NuGet/MSBuild and uv | `demos/plant-operations/app/plant_manager.csproj`, `demos/epic-ehr/service/pyproject.toml` |
| Solution/build system | MSBuild solution XML (`.slnx`) | `computer-use-demos.slnx` |

### 2) Production Frameworks and Dependencies

| Dependency | Version | Role in system | Evidence |
|------------|---------|----------------|----------|
| WPF | .NET 8 SDK | Plant simulator UI | `demos/plant-operations/app/plant_manager.csproj` |
| LiveChartsCore.SkiaSharpView.WPF | 2.0.0-rc5.4 | Plant trend charts | `demos/plant-operations/app/plant_manager.csproj` |
| Playwright | >=1.51.0 | Screenshot/action browser control through a loopback CDP connection | `demos/epic-ehr/service/pyproject.toml` |
| azure-identity | >=1.20.0 | Entra ID authentication | `demos/epic-ehr/service/pyproject.toml` |
| github-copilot-sdk | 1.0.13 | Isolated Copilot CLI runtime for packaged Epic browser and local-file skills | `demos/epic-ehr/service/pyproject.toml` |
| FastAPI / Uvicorn | >=0.115.0 / >=0.34.0 | Epic adapter HTTP API | `demos/epic-ehr/service/pyproject.toml` |
| Pydantic | Transitive through FastAPI | Request, job, bundle, and resource schemas | `demos/epic-ehr/service/src/epic_adapter/models.py` |
| Rich | >=13.9.0 | Red-cross ASCII terminal and sanitized job progress | `demos/epic-ehr/service/pyproject.toml` |

### 3) Development Toolchain

| Tool | Purpose | Evidence |
|------|---------|----------|
| `dotnet` CLI | Restore and build the plant WPF project | `computer-use-demos.slnx` |
| `uv` | Resolve, install, and run Python dependencies | `demos/epic-ehr/service/pyproject.toml` |
| Python `unittest` | Epic service unit and API tests | `demos/epic-ehr/service/tests/` |
| Azure CLI Bicep | Validate the Azure VM/Bastion template | `demos/epic-ehr/infra/main.bicep` |
| Sigstore cosign | Keyless OIDC signing and workflow/tag identity verification for `epic-v*` archives | `.github/workflows/epic-release.yml` |

### 4) Key Commands

```powershell
dotnet build .\computer-use-demos.slnx
uv sync --project .\demos\epic-ehr\service
uv run --project .\demos\epic-ehr\service epic-agent
$env:PYTHONPATH = (Resolve-Path .\demos\epic-ehr\service\src).Path
python -m unittest discover .\demos\epic-ehr\service\tests
az bicep build --file .\demos\epic-ehr\infra\main.bicep
.\demos\epic-ehr\release\build-release.ps1 -Tag epic-v0.3.1
```

No linter or formatter is configured. `[TODO]`

### 5) Environment and Config

- Plant config comes from its `config.py`, `.env.example`, and environment.
- Epic API requires `API_BEARER_TOKEN`; fixture mode is the default.
- Epic live mode requires `EPIC_COMPUTER_USE_ENABLED=1`, `EPIC_ORIGIN`,
  loopback `EPIC_BROWSER_CDP_URL`, and `COPILOT_GITHUB_TOKEN` for isolated
  Copilot mode. Optional Azure BYOM uses `AZURE_AI_FOUNDRY_ENDPOINT` with
  `DefaultAzureCredential`; Azure API keys are not used. `MODEL_DEPLOYMENT`
  defaults to `gpt-6-astra`; actual account availability is unverified.
- The Epic live worker and plant demo require Windows and a visible unlocked
  desktop session.

### 6) Evidence

- `computer-use-demos.slnx`
- `demos/plant-operations/app/plant_manager.csproj`
- `demos/plant-operations/agent/pyproject.toml`
- `demos/epic-ehr/service/pyproject.toml`
- `demos/epic-ehr/infra/main.bicep`
