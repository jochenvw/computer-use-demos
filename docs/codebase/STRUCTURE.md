# Codebase Structure

## Core Sections (Required)

### 1) Top-Level Map

| Path | Purpose | Evidence |
|------|---------|----------|
| `demos/plant-operations/` | Industrial simulator, agent, and walkthrough | `demos/plant-operations/README.md` |
| `demos/epic-ehr/` | API-fronted EHR adapter, synthetic fixtures, Azure infrastructure, and walkthrough | `demos/epic-ehr/README.md` |
| `docs/codebase/` | Maintainer-facing codebase documentation | This directory |
| `scripts/` | Optional environment helper examples | `scripts/connect-to-demo-vm.example.ps1` |
| `computer-use-demos.slnx` | Builds the plant WPF simulator | `computer-use-demos.slnx` |
| `README.md` | Repository entry point and safety summary | `README.md` |

### 2) Entry Points

- Plant simulator: `demos/plant-operations/app/App.xaml`.
- Epic API: `demos/epic-ehr/service/src/epic_adapter/api.py`.
- Epic terminal: `epic-agent` / `src/epic_adapter/console.py`, launched by `service/run.ps1`.
- Epic dedicated browser and authenticated tunnel launchers: `service/browser.ps1`
  and `service/tunnel.ps1`.
- Plant agent CLI: `demos/plant-operations/agent/main.py`.
- Plant A2A server: `demos/plant-operations/agent/a2a_server.py`.
- Epic Azure deployment entry: `demos/epic-ehr/infra/main.bicep`.
- Entry selection is explicit through `dotnet run`, `epic-agent`, Azure
  deployment, or the plant agent's PowerShell launchers.

### 3) Module Boundaries

| Boundary | What belongs here | What must not be here |
|----------|-------------------|------------------------|
| `plant-operations/app/` | Local simulator UI and synthetic state | Cloud credentials or agent API calls |
| `plant-operations/agent/` | Screenshot capture, model calls, UI execution, prompts | Sensitive data or real control-system adapters |
| `epic-ehr/service/` | Authenticated API, jobs, adapters, Copilot skill runner, packaged skills, file catalog, formats, audit | Hospital credentials or deployment state |
| `epic-ehr/fixtures/` | Synthetic patient and diagnostic-file examples | Real protected health information |
| `epic-ehr/infra/` | Parameterized Azure VM/Bastion infrastructure | Secrets or logged-in desktop state |
| `epic-ehr/launcher/` | Current-user bootstrap, exact-version/channel install, drain, activation and rollback | Versioned service files or persisted GitHub tokens |
| `epic-ehr/release/` | Builds tracked archives and version/lock manifests | Local runtime state |
| `docs/` | Verified maintenance documentation | Runtime state |
| `scripts/` | Parameterized local helpers | Tenant-, subscription-, or host-specific values |

### 4) Naming and Organization Rules

- Demo directories use kebab-case; C# types/files use PascalCase; Python modules
  use snake_case.
- The plant demo uses `app/` and `agent/`; the Epic adapter uses `service/`,
  `fixtures/`, and `infra/`.
- Plant Python modules use top-level local imports. The Epic service is an
  installable `src/epic_adapter` package with relative imports. Its
  `src/epic_adapter/skills/*/SKILL.md` files are packaged data for runtime use,
  not checkout-only prompts.

### 5) Evidence

- `README.md`
- `computer-use-demos.slnx`
- `demos/plant-operations/README.md`
- `demos/epic-ehr/README.md`
- `demos/epic-ehr/launcher/Start-EpicDemo.ps1`
- `.github/workflows/epic-release.yml`
