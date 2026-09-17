# Testing Patterns

## Core Sections (Required)

### 1) Test Stack and Commands

- Primary test framework: Python standard-library `unittest`.
- Assertion/mocking tools: `unittest` assertions and FastAPI `TestClient`.
- Current verification commands:

```powershell
dotnet build .\computer-use-demos.slnx
python -m compileall -q .\demos\plant-operations\agent .\demos\epic-ehr\service
$env:PYTHONPATH = (Resolve-Path .\demos\epic-ehr\service\src).Path
python -m unittest discover .\demos\epic-ehr\service\tests
az bicep build --file .\demos\epic-ehr\infra\main.bicep
.\demos\epic-ehr\release\build-release.ps1 -Tag <tag-at-HEAD>
```

There is no coverage command. `[TODO]`

### 2) Test Layout

- Epic tests live under `demos/epic-ehr/service/tests`.
- Test modules use `test_*.py`; classes subclass `unittest.TestCase`.

### 3) Test Scope Matrix

| Scope | Covered? | Typical target | Notes |
|-------|----------|----------------|-------|
| Unit | Yes | Source routing, browser bounds/origins, Copilot SDK session options, patient verification, FHIR/XML/HL7, cache, files | Fake SDK/browser responses and temporary data |
| Integration | Yes | Authenticated API, jobs, default FHIR JSON, XML/HL7, file download, cache headers, audit redaction | In-process `TestClient` with fixture backend |
| Runtime smoke | Yes | Managed Copilot runtime provisioning, no-model SDK session creation, real loopback API, and dedicated headless Edge CDP actions | Synthetic page only; no Epic/model/tunnel connection |
| Release/activation | Partial | Workflow tests, wheel build, archive manifest, launcher synthetic retrieval and loopback health | Publication, attestation and rollback execute during tagged deployment |
| E2E | Manual only | Actual Copilot model plus hospital Epic workflow | Requires authorized training environment |

### 4) Mocking and Isolation Strategy

- Temporary directories isolate file and audit tests.
- `EhrAdapter` separates the API/job layer from fixture and Copilot skill retrieval.
- The Copilot CLI lifecycle, selected-skill registration, custom-only tool
  allowlist, permission denial and cleanup are exercised with fake SDK calls.
  Browser screenshots and controls are also exercised against an isolated real
  Edge on Windows. No claims are made about actual Epic navigation/model
  availability.

### 5) Coverage and Quality Signals

- Coverage tool and threshold: `[TODO]`.
- Current reported coverage: `[TODO]`.
- Known gaps: plant window matching, real Epic workflows, live model requests,
  tunnel hosting and hospital-specific login URL prefixes require interactive acceptance.
- The solution build succeeds; NuGet emits compatibility warnings for transitive
  plant chart dependencies.

### 6) Evidence

- `computer-use-demos.slnx`
- `demos/epic-ehr/service/tests/test_api.py`
- `demos/epic-ehr/service/tests/test_file_catalog.py`
- `demos/plant-operations/DEMO_SCRIPT.md`
- `demos/epic-ehr/DEMO_SCRIPT.md`
- Terminal output from `dotnet build` and Python `compileall`
- `.github/workflows/epic-release.yml`
- `demos/epic-ehr/launcher/Start-EpicDemo.ps1`
