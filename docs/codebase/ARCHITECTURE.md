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
       -> files / EHR / both (fixture OR selected Copilot CLI skill)
       -> cached normalized clinical bundle
       -> FHIR JSON/XML, limited HL7 ORU, normalized JSON/NDJSON, original file
```

1. The API authenticates the caller and accepts a patient-scoped retrieval.
2. `JobService` creates an opaque job and serializes work through a GUI lock.
3. The configured adapter returns synthetic fixtures or starts an isolated
   empty-mode Copilot CLI session with one packaged `SKILL.md`.
4. `FileCatalog` searches only configured roots and allowlisted extensions; in
   Copilot mode the `local-files` skill must list/open handles before extracting.
5. The service combines both sources into a format-neutral `ClinicalBundle` and
   may reuse a caller/backend/patient/source/resource/filter cache hit.
6. Result endpoints render default FHIR JSON, FHIR XML, limited HL7 ORU,
   normalized JSON/NDJSON, or a job-scoped original file.

### 3) Layer/Module Responsibilities

| Layer or module | Owns | Must not own | Evidence |
|-----------------|------|--------------|----------|
| Epic API | Authentication and HTTP representation | Browser credentials or GUI details | `demos/epic-ehr/service/src/epic_adapter/api.py` |
| Job service | Lifecycle, serialization, bundle assembly, audit events | Format-specific rendering | `demos/epic-ehr/service/src/epic_adapter/jobs.py` |
| EHR adapters | Read-only source retrieval | API authentication or file downloads | `demos/epic-ehr/service/src/epic_adapter/adapters/` |
| Skill runner | SDK lifecycle, selected skill copy, custom tool allowlist, cleanup | Generic shell/filesystem/MCP/plugin access | `demos/epic-ehr/service/src/epic_adapter/skill_runner.py` |
| BrowserSession | Exact-origin CDP attachment, screenshots, bounded UI actions | Desktop input, arbitrary URLs or shortcuts | `demos/epic-ehr/service/src/epic_adapter/browser.py` |
| Console | Red ASCII cross, sanitized lifecycle and action events | Clinical content or credentials | `demos/epic-ehr/service/src/epic_adapter/console.py` |
| Tunnel launcher | Optional authenticated outbound forwarding of API port | Anonymous access or forwarding CDP port | `demos/epic-ehr/service/tunnel.ps1` |
| File catalog | Patient-scoped allowlisted local files | Arbitrary filesystem access | `demos/epic-ehr/service/src/epic_adapter/file_catalog.py` |
| Formatters | FHIR JSON/XML, limited HL7 ORU, normalized JSON/NDJSON | Source retrieval or full FHIR profile validation | `demos/epic-ehr/service/src/epic_adapter/formats.py` |
| Bicep | Private Windows VM, custom image, Bastion, NSG | Epic/browser session state | `demos/epic-ehr/infra/main.bicep` |
| Release workflow | Tests, packages and attests exact `epic-v*` commits | Runtime secrets or local patient files | `.github/workflows/epic-release.yml` |
| Desktop launcher | Per-version staging, authenticated drain, synthetic validation, activation and rollback | Automatic newest-release selection or unattended Epic login | `demos/epic-ehr/launcher/Start-EpicDemo.ps1` |

### 4) Reused Patterns

| Pattern | Where found | Why it exists |
|---------|-------------|---------------|
| Fail-closed guard | Epic config/browser modules; plant screenshot module | Rejects missing/incorrect target before capture |
| MVVM | Plant app models, engine, and ViewModel | Keeps telemetry state separate from WPF controls |
| Adapter | `EhrAdapter`, fixture adapter, computer-use adapter | Keeps API callers independent of retrieval mechanism |
| Opaque job | Epic API and `JobService` | Hides long-running serialized GUI work from callers |
| Allowlist | Epic `FileCatalog` and `CopilotSkillRunner` | Prevents arbitrary filesystem retrieval and unmanaged runtime tools |
| Local blue/green activation | Version directories plus current/previous state | Keeps the last working release available across failed updates |

### 5) Known Architectural Risks

- Copilot browser automation is implemented; actual hospital navigation and
  model deployment remain unverified. An authorized read-only Epic account is
  mandatory because origin/action restrictions cannot enforce click semantics.
- In fixture mode `files` uses only the local catalog. In Copilot mode `files`
  uses the packaged local-file skill, but never EHR browser navigation; `ehr`
  never searches local files; `both` requires both operations to succeed.
- The in-memory job store loses state on process restart and supports one process.
- The retrieval cache is a small in-process LRU/TTL cache, not a durable result
  store or total process memory cap.
- Bearer-token authentication is suitable only for the demo; production requires
  Entra ID, private gateway controls, and policy enforcement.
- The plant A2A server remains a separate exposure path, although live execution
  is now blocked by the same `run()` validation.
- Release integrity depends on GitHub artifact attestation verification through
  `gh`; private downloads additionally require a short-lived installer token.

### 6) Evidence

- `demos/plant-operations/agent/agent.py`
- `demos/plant-operations/app/ViewModels/MainViewModel.cs`
- `demos/epic-ehr/service/src/epic_adapter/api.py`
- `demos/epic-ehr/service/src/epic_adapter/jobs.py`
- `demos/epic-ehr/infra/main.bicep`
