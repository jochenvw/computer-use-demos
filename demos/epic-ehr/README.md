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
| `files` | Local catalog only; no EHR lookup, screenshot, or model call |
| `ehr` | Fixture or GPT Astra browser retrieval; no local-file discovery |
| `both` | Both sources; a failure prevents a success-shaped partial result |

Store approved files under **exact patient directories**, for example
`D:\DemoRecords\DEMO-100042\ecg.pdf`. Configure `EPIC_FILE_ROOTS=D:\DemoRecords`.
Multiple Windows roots are separated by semicolons. Substring matches across
patient IDs are not allowed. Missing roots and escaped links fail explicitly.

Supported originals: PDF, PNG/JPEG, DICOM (`.dcm`), SCP-ECG, XML, JSON.
Files are cataloged, hashed, and downloadable, not clinically interpreted.
The agent does not extract waveforms or diagnose ECG images.

## GPT Astra browser mode

The worker uses **Responses API vision plus function tools**. It sends screenshots
to the configured GPT Astra deployment and executes one permitted browser action
per response. It does not assume support for the older `computer_use_preview`
tool and never silently substitutes another model.

Set your actual Azure deployment name in `MODEL_DEPLOYMENT`; `gpt-6-astra` is the
default requested model name, not a guarantee of availability in your account.
The deployment must support image input, function calling, and the Responses API.

1. On the VM, open a **dedicated** browser profile:

   ```powershell
   .\browser.ps1 -EpicUrl https://your-authorized-epic-host
   ```

2. Log in manually using an authorized **read-only account**, preferably in Epic
   training with synthetic records. Keep exactly one Epic tab open.
3. Configure `.env` (replace placeholders):

   ```text
   EPIC_BACKEND=computer-use
   EPIC_COMPUTER_USE_ENABLED=1
   EPIC_ORIGIN=https://your-authorized-epic-host
   EPIC_BROWSER_CDP_URL=http://127.0.0.1:9222
   AZURE_AI_FOUNDRY_ENDPOINT=https://your-resource.services.ai.azure.com
   MODEL_DEPLOYMENT=gpt-6-astra
   ```

4. Use Entra ID (`az login` with the appropriate model role), or supply
   `AZURE_API_KEY` through the local environment. Start `.\run.ps1`.
5. Submit an `ehr` or `both` request. No special caller-side automation is needed.

The worker attaches over the browser's loopback Chrome DevTools Protocol (CDP).
It only captures the configured-origin tab, rejects cross-origin navigation,
bounds coordinates, restricts keys, and permits typing only the requested
patient identifier. It validates returned patient/subject identifiers and
requested resource types. Session expiry or uncertain identity produces a failed
job, not invented data. Screenshots remain in memory and API calls use
`store=False`; the organization's model processing/retention policies still apply.

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
| GET | `/v1/retrieval-jobs/{job_id}/result?format=ndjson` | Normalized resource lines |
| GET | `/v1/retrieval-jobs/{job_id}/files/{file_id}` | Original file, reverified before download |
| GET | `/healthz` | Process health only |

FHIR output preserves recorded quantities/components; it is an illustrative
mapping, not validated FHIR profile conformance. NDJSON contains clinical
resources; file links are in JSON/FHIR. Source provenance is included in normalized
JSON. The caller need not know or orchestrate computer use, but provenance is not
misrepresented as a native Epic API response.

## Verify

```powershell
uv run python -m unittest discover tests -v
uv run epic-agent --banner-only
```

Unit/API tests use fixtures and mocked model calls; they do not contact Epic or
Azure. Infrastructure template and image preparation are in `infra\`.
