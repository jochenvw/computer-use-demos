# External Integrations

## Core Sections (Required)

### 1) Integration Inventory

| System | Type | Purpose | Auth model | Criticality | Evidence |
|--------|------|---------|------------|-------------|----------|
| Epic browser session | CDP / Playwright | Screenshot-based patient retrieval on an exact-origin tab | Dedicated authorized read-only browser account | High | `demos/epic-ehr/service/src/epic_adapter/browser.py` |
| Local clinical files | Filesystem | Discover ECG and document files in configured roots | VM filesystem ACLs plus service allowlist | High | `demos/epic-ehr/service/src/epic_adapter/file_catalog.py` |
| GPT Astra deployment | Responses API | Images -> constrained function calls -> validated extracted resources | Entra ID or local API key | High | `demos/epic-ehr/service/src/epic_adapter/adapters/computer_use.py` |
| Microsoft dev tunnels | Outbound HTTPS forwarding | Synthetic demo API access without inbound firewall rule | Tunnel owner identity/connect token AND API bearer token | Optional | `demos/epic-ehr/service/tunnel.ps1` |
| Azure Bastion | Managed Azure service | Administrative access to private desktop VM | Azure RBAC | High | `demos/epic-ehr/infra/main.bicep` |
| Plant A2A server | HTTP/JSON-RPC | Expose the plant agent to A2A clients | No application auth is present | Medium | `demos/plant-operations/agent/a2a_server.py` |

### 2) Data Stores

| Store | Role | Access layer | Key risk | Evidence |
|-------|------|--------------|----------|----------|
| `memory.json` | Local plant incident history | `memory.py` | May retain generated operational text locally | `demos/plant-operations/agent/memory.py` |
| In-memory Epic job store | Retrieval status and results | `JobService` | Jobs disappear on restart and cannot scale across processes | `demos/epic-ehr/service/src/epic_adapter/jobs.py` |
| JSON fixture files | Synthetic clinical records | `FixtureEpicAdapter` | Demo data can diverge from live schema | `demos/epic-ehr/fixtures/patients/DEMO-100042.json` |
| JSON Lines audit file | Hashed retrieval events | `AuditWriter` | Local file needs collection and retention controls | `demos/epic-ehr/service/src/epic_adapter/audit.py` |

No durable database/queue exists. A real Epic instance has not been connected.

### 3) Secrets and Credentials Handling

- Epic API demo authentication uses `API_BEARER_TOKEN`.
- Live worker configuration uses an approved Foundry endpoint and should use
  managed identity/Entra ID.
- DefaultAzureCredential and a Cognitiveservices token provider are wired;
  AZURE_API_KEY is optional. No configured model has been invoked during development.
- `.env` and runtime memory files are ignored; `.env.example` files contain only
  placeholders.
- The repository-level secret scan must be rerun before every public push.
- Credential rotation policy is external to this repository. `[TODO]`

### 4) Reliability and Failure Behavior

- GUI work is serialized with one process-local lock.
- Failed jobs expose an error status and generate a completion audit event.
- Model requests have a 60-second timeout and no automatic retries; the
  configurable browser-step limit defaults to 40 (maximum 100). No durable queue.
- Jobs are bounded to eight pending and 128 total per process.

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
