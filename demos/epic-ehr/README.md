# Epic Retrieval Agent

A red-cross terminal agent exposing a clinical-data retrieval API. Callers
request files, EHR data, or both; browser actions stay behind the API boundary.

```text
        ++++++++
        ++++++++
  ++++++++++++++++++++
  ++++++++++++++++++++
        ++++++++
        ++++++++

  EPIC RETRIEVAL AGENT
  Local files / browser worker / clinical data API
```

The cross is rendered red in the terminal. This is an independent training demo,
not an Epic Systems or humanitarian organization product.

## Start the terminal and API

```powershell
cd .\demos\epic-ehr\service
uv sync --extra test
Copy-Item .env.example .env
```

Set `API_BEARER_TOKEN` to a generated secret in the ignored `.env` file or process
environment. Do not use the example placeholder. Then:

```powershell
.\run.ps1
# Preview without starting a server:
.\run.ps1 -BannerOnly
```

The API listens on `127.0.0.1:8000`. The console shows queued/running/completed
jobs, file counts, and browser action names, but no patient identifiers, model
reasoning, clinical text, or screenshots. Stop with Ctrl+C.

Default `EPIC_BACKEND=fixture` runs against synthetic data with no browser/model
calls. The in-memory demo job store supports one process, at most eight pending
jobs, and 128 total jobs per session. Restarting clears jobs and results.

## Choose a source

```powershell
$headers = @{ Authorization = "Bearer $env:API_BEARER_TOKEN" }
$body = @{
    patient_id = 'DEMO-100042'
    source = 'files' # files, ehr, or both
    resources = @('patient', 'ecg', 'documents')
} | ConvertTo-Json
$job = Invoke-RestMethod http://127.0.0.1:8000/v1/retrieval-jobs `
    -Method Post -Headers $headers -ContentType application/json -Body $body
Invoke-RestMethod "http://127.0.0.1:8000$($job.status_url)" -Headers $headers
# Once status is complete:
Invoke-RestMethod "http://127.0.0.1:8000$($job.result_url)?format=fhir" -Headers $headers
```

`run.ps1` loads `.env` into its own process. Set the caller's token separately;
do not assume a second shell inherited the file.

| Source | Operation |
|---|---|
| `files` | Fixture: local catalog. Copilot: local-file skill lists/opens approved reports; no EHR lookup |
| `ehr` | Fixture or Copilot Epic-browser skill; no local-file discovery |
| `both` | Both sources; a failure prevents a success-shaped partial result |

Store approved files under **exact patient directories**, for example
`D:\DemoRecords\DEMO-100042\ecg.pdf`. Configure `EPIC_FILE_ROOTS=D:\DemoRecords`.
Multiple Windows roots are separated by semicolons. Substring matches across
patient IDs are not allowed. Missing roots and escaped links fail explicitly.

Supported originals: PDF, PNG/JPEG, DICOM (`.dcm`), SCP-ECG, XML, JSON.
Files are cataloged, hashed, and downloadable. The Copilot file skill opens
JSON/XML, text PDFs, and images to retrieve existing documented report text;
each extracted resource cites an opened file handle. Reads are limited to 4 MiB
and 100,000 text characters; encrypted, textless, or over-50-page PDFs fail.
DICOM/SCP-ECG remain original downloads. No waveform conversion or diagnosis.

## Copilot CLI skills mode

The Python agent hosts **GitHub Copilot CLI through `github-copilot-sdk==1.0.13`**.
Two packaged `SKILL.md` modules implement `epic-browser` and `local-files`.
Each request gets an isolated empty-mode CLI session with only the selected
skill eagerly loaded and that skill's host tools. Generic shell, filesystem,
network, built-in skills, plugins, and configuration discovery are not enabled.
Browser lifecycle and actions run on one dedicated thread.

Provision the SDK-matched runtime before an offline demonstration:

```powershell
uv run python -m copilot download-runtime
```

Set the Copilot model name in `MODEL_DEPLOYMENT`; `gpt-6-astra` is the requested
default, not a guarantee of account availability. Supply `COPILOT_GITHUB_TOKEN`
for the isolated runtime. Alternatively, configure `AZURE_AI_FOUNDRY_ENDPOINT`
and use Entra ID (`DefaultAzureCredential`) for Azure BYOM; then
`MODEL_DEPLOYMENT` is your deployment name. API-key authentication is not used.

1. On the VM, open a **dedicated** browser profile:

   ```powershell
   .\browser.ps1 -EpicUrl https://your-authorized-epic-host
   ```

2. Log in manually using an authorized **read-only account**, preferably in Epic
   training with synthetic records. Keep exactly one Epic tab open.
3. Configure `.env` (replace placeholders):

   ```text
   EPIC_BACKEND=copilot
   EPIC_COMPUTER_USE_ENABLED=1
   EPIC_ORIGIN=https://your-authorized-epic-host
   EPIC_BROWSER_CDP_URL=http://127.0.0.1:9222
   MODEL_DEPLOYMENT=gpt-6-astra
   ```

4. Set the runtime credential locally, or use Entra ID for optional Azure BYOM.
   Start `.\run.ps1`. `computer-use` remains an alias for `copilot`.
5. Submit an `ehr` or `both` request. No special caller-side automation is needed.

The worker attaches over the browser's loopback Chrome DevTools Protocol (CDP).
It only captures the configured-origin tab, rejects cross-origin navigation,
bounds coordinates, restricts keys, and permits typing only the requested
patient identifier. It validates returned patient/subject identifiers and
requested resource types. Session expiry or uncertain identity produces a failed
job, not invented data. Sessions are aborted, disconnected, deleted and their
temporary CLI homes removed after execution. The CLI can write temporary
session data during a request; use only synthetic data on an approved host.
Provider processing/retention policies still apply. Each skill has an action
budget (`EPIC_MAX_BROWSER_STEPS`, default 40) and timeout
(`EPIC_SKILL_TIMEOUT_SECONDS`, default 180).

## Warm retrieval cache and force live work

A format-neutral in-process LRU retains up to 16 entries / 8 MiB of serialized
bundle data for 900 seconds. Configure `EPIC_CACHE_MAX_ENTRIES`,
`EPIC_CACHE_MAX_BYTES`, and `EPIC_CACHE_TTL_SECONDS`. This is not an overall
process-memory cap; job results remain in the separately bounded job store.
Keys include caller, backend, exact patient, source, requested resources, and
observation-code filter. A hit invokes no model, skill, browser or file discovery.
Downloads still verify the original file's current hash.

Warm blood pressure before the demo using a normal request:

```json
{
  "patient_id": "DEMO-100042",
  "source": "ehr",
  "resources": ["observations"],
  "observation_codes": ["85354-9"],
  "bypass_cache": false
}
```

Repeat the same request for a hit. Set `"bypass_cache": true` to invalidate the
entry, execute the skill live and cache a successful result. Fresh failures fail
the job; there is no stale fallback. The optional code filter matches observation
panel/component codes after retrieval and preserves the full BP composite.
For ECG files, use `source: files` and `resources: ["ecg"]`.
Job status exposes `cache_status` (`hit`, `miss`, `bypass`), `collected_at` and
`expires_at`; result headers expose the same metadata without altering FHIR.
Oversized bundles are returned but not cached (`expires_at == collected_at`).

**Read-only intent is not an authorization boundary.** Model instructions and
tool restrictions cannot guarantee that every clicked Epic control is read-only.
The Epic account must enforce read-only permissions. Browser debugging grants
access to its session: never tunnel port 9222, reuse your everyday browser
profile, or run alongside confidential tabs. Test hospital-specific navigation
with synthetic records before any approved clinical deployment.

## Authenticated dev tunnel

In a second terminal on the same machine:

```powershell
devtunnel user login
.\tunnel.ps1
```

This forwards local port 8000 through outbound connectivity. No public VM IP or
inbound firewall rule is needed. The script requires a healthy local API, uses a
one-hour tunnel, and **does not enable anonymous access**. Ctrl+C closes it.

Use the HTTPS URL printed by devtunnel in place of `http://127.0.0.1:8000`.
Response links are relative, so they also work behind Host-rewriting tunnels.
Interactive clients authenticate to the tunnel. For programmatic clients, obtain
a tunnel connect token using your devtunnel CLI's token command and send it as
`X-Tunnel-Authorization: tunnel <connect-token>`; continue sending
`Authorization: Bearer <API_BEARER_TOKEN>` separately. Treat both tokens as secrets.
Never send patient data in URL parameters.

```powershell
# Run locally; do not save or publish the printed token.
devtunnel token <tunnel-id> --scopes connect
```

See [Microsoft's dev tunnel security guidance](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/security).

This is for authorized synthetic demonstrations, not an approved PHI transport.
For clinical use, replace it with organization-approved private ingress, Entra ID
authorization and TLS. The demo API has one shared operator principal, not
multi-user or patient-level authorization.

## API and output formats

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/retrieval-jobs` | Patient-scoped retrieval (`files`, `ehr`, `both`) |
| GET | `/v1/retrieval-jobs/{job_id}` | Job status, no clinical result |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=json` | Normalized JSON |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=fhir` | FHIR R4-style Bundle |
| GET | `/v1/retrieval-jobs/{job_id}/result` | Default: FHIR JSON |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=fhir-xml` | Explicit-subset FHIR XML |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=hl7` | HL7 v2.5.1 ORU observation/report projection |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=ndjson` | Normalized resource lines |
| GET | `/v1/retrieval-jobs/{job_id}/files/{file_id}` | Original file, reverified before download |
| GET | `/healthz` | Process health only |

FHIR output preserves recorded quantities/components; it is an illustrative
mapping, not validated FHIR profile conformance. NDJSON contains clinical
resources; file links are in JSON/FHIR. Source provenance is included in normalized
JSON. The caller need not know or orchestrate computer use, but provenance is not
misrepresented as a native Epic API response.

XML supports an explicit R4 subset, not arbitrary narrative/extensions.
HL7 preserves supported numeric/text observations, BP component codes/units and
documented ECG conclusions, using CR-separated segments and escaped delimiters.
Unsupported fields/values or a file-only HL7 request return HTTP 422, not a
fabricated clinical message. This is not a full hospital interface profile.

## Verify

```powershell
uv run python -m unittest discover tests -v
uv run epic-agent --banner-only
```

Unit/API tests use fixtures and mocked model calls; they do not contact Epic or
Azure. Infrastructure template and image preparation are in `infra\`.
