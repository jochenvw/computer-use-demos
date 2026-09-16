# Codebase Concerns

## Core Sections (Required)

### 1) Top Risks (Prioritized)

| Severity | Concern | Evidence | Impact | Suggested action |
|----------|---------|----------|--------|------------------|
| High | Copilot browser skill can encounter PHI and clinical controls | `demos/epic-ehr/service/src/epic_adapter/skill_runner.py` | Wrong-patient retrieval or unintended click is possible despite model instructions | Enforce read-only account permissions, approved provider processing/retention, and hospital-specific synthetic acceptance tests |
| High | API bearer token is a demo authentication mechanism | `demos/epic-ehr/service/src/epic_adapter/api.py` | Shared-token compromise grants retrieval access | Replace with Entra ID OAuth validation and API gateway policy |
| High | Retrieval results and files are held in process memory and served by opaque IDs | `demos/epic-ehr/service/src/epic_adapter/jobs.py` | Restart loses jobs; multi-worker deployment breaks consistency | Use a durable encrypted job store and scoped authorization before production |
| Medium | Plant A2A HTTP server has no application authentication | `demos/plant-operations/agent/a2a_server.py` | Network clients could trigger work if explicitly exposed | Keep the localhost default and add auth before remote exposure |
| Medium | No actual Epic/model acceptance test | `docs/codebase/TESTING.md` | Real workflow failures may escape synthetic tests | Add authorized training-environment acceptance before clinical deployment |
| Low | Plant chart transitive packages produce `NU1701` warnings | `demos/plant-operations/app/plant_manager.csproj`; build output | Future framework updates may break chart rendering | Upgrade or replace the release-candidate chart package |

### 2) Technical Debt

| Debt item | Why it exists | Where | Risk if ignored | Suggested fix |
|-----------|---------------|-------|-----------------|---------------|
| Plant-specific monolithic orchestrator | Original single-demo design | `demos/plant-operations/agent/agent.py` | Harder to reuse and test | Separate API transport, policy, and loop state |
| In-memory Epic job implementation | Minimal public scaffold | `demos/epic-ehr/service/src/epic_adapter/jobs.py` | No restart recovery or horizontal scaling | Add a durable queue and encrypted result store |
| FHIR mapping is illustrative | Demo output requirement | `demos/epic-ehr/service/src/epic_adapter/formats.py` | Consumers may assume unsupported conformance | Validate against an agreed profile and publish capability metadata |

### 3) Security Concerns

| Risk | OWASP category | Evidence | Current mitigation | Gap |
|------|----------------|----------|--------------------|-----|
| Wrong-patient data retrieval | A01 | Epic skill runner and browser modules | Exact-origin screenshots, instructed identity checks, output identifier/subject checks | Model-reported identity is not independently verified against Epic backend |
| Sensitive screenshot/file disclosure | A02 | Epic skill runner | Dedicated-origin tab, temporary isolated CLI home, custom-only tool allowlist, sanitized console | Provider retention, image redaction and approved tenancy remain deployment responsibilities |
| Arbitrary local-file access | A01 | `file_catalog.py` and `skill_runner.py` | Safe identifier regex, configured roots, extension allowlist, opaque file handles, hash recheck | OS ACL and caller-to-patient authorization remain deployment responsibilities |
| Unauthenticated A2A endpoint | A01 | `demos/plant-operations/agent/a2a_server.py` | Loopback bind by default; live execution requires explicit opt-in | Authentication and TLS are required before remote exposure |
| Local secret files | A02 | `.gitignore`, `.env.example` files | `.env` ignored and examples use placeholders | Secret scanning is not yet automated in CI |

### 4) Performance and Scaling Concerns

| Concern | Evidence | Current symptom | Scaling risk | Suggested improvement |
|---------|----------|-----------------|-------------|-----------------------|
| Original file download shares the API process | `api.py` | Fine for small synthetic ECG files | Large DICOM/PDF downloads consume API worker capacity | Offload authorized downloads to encrypted object storage or a streaming tier |
| Single GUI lock serializes all jobs | `jobs.py` | One job at a time | Queue latency grows with callers | Keep one GUI worker per desktop session and scale through partitioned workers |
| Cache and job store are process-local | `cache.py`, `jobs.py` | Fine for a single synthetic demo process | Restart loses state; cache byte bound is not a total process-memory cap | Use durable encrypted stores and explicit retention limits before production |

### 5) Fragile/High-Churn Areas

| Area | Why fragile | Churn signal | Safe change strategy |
|------|-------------|-------------|----------------------|
| Epic live adapter | Hospital UI, patient context, and extraction schema must agree | Synthetic SDK/browser/API tests exist; no live Epic test | Require actual training-environment acceptance before enabling clinical data |
| `jobs.py` | Threads mutate process-local job records | No Git history exists yet | Add concurrency and restart tests before changing execution model |

### 6) `[ASK USER]` Questions

None remaining. The user chose to defer adding a license.

### 7) Evidence

- `SECURITY.md`
- `.gitignore`
- `demos/plant-operations/agent/a2a_server.py`
- `demos/epic-ehr/service/src/epic_adapter/api.py`
- `demos/epic-ehr/service/src/epic_adapter/jobs.py`
- `demos/epic-ehr/service/src/epic_adapter/file_catalog.py`
- `demos/plant-operations/app/plant_manager.csproj`
