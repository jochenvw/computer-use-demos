# Architecture

## Core Sections (Required)

### 1) Architectural Style

- Primary style: independent vertical demos. The plant demo is a simulator plus
  agent; the Epic demo is a private API plus serialized VM desktop worker.
- The Epic external contract is backend-agnostic: callers see retrieval jobs and
  clinical representations, not browser automation.
- Primary constraints: one interactive GUI session, private networking, strict
  patient/file scoping, authentication, auditability, and read-only behavior.

### 2) System Flow

```text
caller -> authenticated API -> serialized retrieval job
       -> files / EHR / both (EHR: fixture OR Astra screenshots + browser function tools)
       -> normalized clinical bundle -> JSON/FHIR/NDJSON/original file
```

1. The API authenticates the caller and accepts a patient-scoped retrieval.
2. `JobService` creates an opaque job and serializes work through a GUI lock.
3. The configured EHR adapter returns normalized read-only resources.
4. `FileCatalog` searches only configured roots and allowlisted extensions.
5. The service combines both sources into a `ClinicalBundle`.
6. Result endpoints render normalized JSON, FHIR R4-style Bundle, NDJSON, or a
   job-scoped original file.

### 3) Layer/Module Responsibilities

| Layer or module | Owns | Must not own | Evidence |
|-----------------|------|--------------|----------|
| Epic API | Authentication and HTTP representation | Browser credentials or GUI details | `demos/epic-ehr/service/src/epic_adapter/api.py` |
| Job service | Lifecycle, serialization, bundle assembly, audit events | Format-specific rendering | `demos/epic-ehr/service/src/epic_adapter/jobs.py` |
| EHR adapters | Read-only source retrieval | API authentication or file downloads | `demos/epic-ehr/service/src/epic_adapter/adapters/` |
| BrowserSession | Exact-origin CDP attachment, screenshots, bounded UI actions | Desktop input, arbitrary URLs or shortcuts | `demos/epic-ehr/service/src/epic_adapter/browser.py` |
| Console | Red ASCII cross, sanitized lifecycle and action events | Clinical content or credentials | `demos/epic-ehr/service/src/epic_adapter/console.py` |
| Tunnel launcher | Optional authenticated outbound forwarding of API port | Anonymous access or forwarding CDP port | `demos/epic-ehr/service/tunnel.ps1` |
| File catalog | Patient-scoped allowlisted local files | Arbitrary filesystem access | `demos/epic-ehr/service/src/epic_adapter/file_catalog.py` |
| Formatters | JSON, FHIR-style Bundle, NDJSON | Source retrieval | `demos/epic-ehr/service/src/epic_adapter/formats.py` |
| Bicep | Private Windows VM, custom image, Bastion, NSG | Epic/browser session state | `demos/epic-ehr/infra/main.bicep` |

### 4) Reused Patterns

| Pattern | Where found | Why it exists |
|---------|-------------|---------------|
| Fail-closed guard | Epic config/browser modules; plant screenshot module | Rejects missing/incorrect target before capture |
| MVVM | Plant app models, engine, and ViewModel | Keeps telemetry state separate from WPF controls |
| Adapter | `EhrAdapter`, fixture adapter, computer-use adapter | Keeps API callers independent of retrieval mechanism |
| Opaque job | Epic API and `JobService` | Hides long-running serialized GUI work from callers |
| Allowlist | Epic `FileCatalog` | Prevents arbitrary filesystem retrieval |

### 5) Known Architectural Risks

- Astra browser automation is implemented; actual hospital navigation and
  model deployment remain unverified. An authorized read-only Epic account is
  mandatory because origin/action restrictions cannot enforce click semantics.
- `files` never calls EHR/model; `ehr` never searches local files; `both` requires
  both operations to succeed. One GUI lock serializes worker activity.
- The in-memory job store loses state on process restart and supports one process.
- Bearer-token authentication is suitable only for the demo; production requires
  Entra ID, private gateway controls, and policy enforcement.
- The plant A2A server remains a separate exposure path, although live execution
  is now blocked by the same `run()` validation.

### 6) Evidence

- `demos/plant-operations/agent/agent.py`
- `demos/plant-operations/app/ViewModels/MainViewModel.cs`
- `demos/epic-ehr/service/src/epic_adapter/api.py`
- `demos/epic-ehr/service/src/epic_adapter/jobs.py`
- `demos/epic-ehr/infra/main.bicep`
