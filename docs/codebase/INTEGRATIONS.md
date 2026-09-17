# External Integrations

## Core Sections (Required)

### 1) Integration Inventory

| System | Type | Purpose | Auth model | Criticality | Evidence |
|--------|------|---------|------------|-------------|----------|
| Epic browser session | CDP / Playwright | Screenshot-based patient retrieval on an exact-origin tab | Dedicated authorized read-only browser account | High | `demos/epic-ehr/service/src/epic_adapter/browser.py` |
| Local clinical files | Filesystem / Copilot skill tools | Discover/open ECG and document files in configured roots | VM filesystem ACLs plus service and skill allowlists | High | `demos/epic-ehr/service/src/epic_adapter/file_catalog.py` |
| Copilot CLI runtime | Python SDK | Hosts packaged `epic-browser` and `local-files` skills with custom tools only | `COPILOT_GITHUB_TOKEN`, or optional Azure BYOM bearer token from `DefaultAzureCredential` | High | `demos/epic-ehr/service/src/epic_adapter/skill_runner.py` |
| Optional Azure BYOM model | OpenAI-compatible endpoint | Model backend for the isolated Copilot runtime | Entra ID bearer token from `DefaultAzureCredential`; no Azure API keys | High | `demos/epic-ehr/service/src/epic_adapter/skill_runner.py` |
| Microsoft dev tunnels | Outbound HTTPS forwarding | Synthetic demo API access without inbound firewall rule | Tunnel owner identity/connect token AND API bearer token | Optional | `demos/epic-ehr/service/tunnel.ps1` |
| Azure Bastion | Managed Azure service | Administrative access to private desktop VM | Azure RBAC | High | `demos/epic-ehr/infra/main.bicep` |
| GitHub Releases and Sigstore | HTTPS / `cosign` | Exact-version archive download and GitHub workflow/tag identity verification | Installer-process token for private releases; GitHub OIDC certificate identity | High | `.github/workflows/epic-release.yml`, `demos/epic-ehr/launcher/Start-EpicDemo.ps1` |
| Plant A2A server | HTTP/JSON-RPC | Expose the plant agent to A2A clients | No application auth is present | Medium | `demos/plant-operations/agent/a2a_server.py` |

### 2) Data Stores

| Store | Role | Access layer | Key risk | Evidence |
|-------|------|--------------|----------|----------|
| `memory.json` | Local plant incident history | `memory.py` | May retain generated operational text locally | `demos/plant-operations/agent/memory.py` |
| In-memory Epic job store | Retrieval status and results | `JobService` | Jobs disappear on restart and cannot scale across processes | `demos/epic-ehr/service/src/epic_adapter/jobs.py` |
| In-memory Epic retrieval cache | Short-lived reusable clinical bundles | `RetrievalCache` | Process-local LRU/TTL/byte bounds are not a durable or total-memory limit | `demos/epic-ehr/service/src/epic_adapter/cache.py` |
| JSON fixture files | Synthetic clinical records | `FixtureEpicAdapter` | Demo data can diverge from live schema | `demos/epic-ehr/fixtures/patients/DEMO-100042.json` |
| JSON Lines audit file | Hashed retrieval events | `AuditWriter` | Local file needs collection and retention controls | `demos/epic-ehr/service/src/epic_adapter/audit.py` |

No durable database/queue exists. A real Epic instance has not been connected.

### 3) Secrets and Credentials Handling

- Epic API demo authentication uses `API_BEARER_TOKEN`.
- Live worker configuration uses `COPILOT_GITHUB_TOKEN` for isolated Copilot
  mode, or an approved Azure resource endpoint with managed identity/Entra ID.
- `DefaultAzureCredential` supplies an Azure BYOM bearer token when configured.
  Azure API keys are not used. No live Epic or model endpoint has been invoked
  during development.
- `.env` and runtime memory files are ignored; `.env.example` files contain only
  placeholders.
- The repository-level secret scan must be rerun before every public push.
- Credential rotation policy is external to this repository. `[TODO]`
- `EPIC_RELEASE_GITHUB_TOKEN` is read only from the installer process and is not
  written to launcher state or shared `.env`.

### 4) Reliability and Failure Behavior

- GUI work is serialized with one process-local lock.
- Failed jobs expose an error status and generate a completion audit event.
- Skill sessions have an abort/disconnect/delete cleanup path, bounded timeout,
  and no automatic stale fallback; the configurable browser-step limit defaults
  to 40 (maximum 100). No durable queue.
- Jobs are bounded to eight pending and 128 total per process.
- Authenticated drain rejects new jobs, waits for active work, and resumes
  acceptance if its timeout expires.

### 5) Observability for Integrations

- The plant agent has an event log and Rich console output.
- The Epic service writes structured audit events without raw patient identifiers.
- No metrics, distributed tracing, or centralized logging is configured.

### 6) Evidence

- `demos/plant-operations/agent/config.py`
- `demos/plant-operations/agent/a2a_server.py`
- `demos/epic-ehr/service/src/epic_adapter/api.py`
- `demos/epic-ehr/service/src/epic_adapter/file_catalog.py`
- `demos/epic-ehr/infra/main.bicep`
