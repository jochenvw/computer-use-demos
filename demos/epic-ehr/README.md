# Clinical Data Agent – computer use for healthcare

An AI agent that **uses a hospital workstation the way a person does**: it looks
at the screen, clicks, types, and reads. It then returns what it found as
structured data in the format you choose.

> Independent training demo with **synthetic patients only**. Not an Epic Systems
> product, not a medical device, and not for clinical decisions.

## For clinicians: what this shows

### The problem

Clinical data is spread across systems that were never designed to share it:
- **EHR portals:** Epic or other electronic health record (EHR) portals, used through a browser.
- **Files:** ECG printouts and scanned reports saved in folders.
- **Local databases:** accessed with desktop tools, in the local language.

Integration projects (APIs, HL7 interfaces) take months per system. Meanwhile,
staff re-type values between screens.

### The idea

Give an AI agent the same screen, mouse, and keyboard a staff member has. You ask
for data ("labs for patient X"). The agent opens the right application, finds the
data, reads it, and hands it over in a standard format:
- **FHIR:** Fast Healthcare Interoperability Resources, the HL7 exchange standard.
- **OMOP:** the Observational Medical Outcomes Partnership common data model, used for research.
- **Your own schema or ontology,** in any language.

No integration project and no change to the source system.

### The story (voice-over)

1. A patient on holiday (Italian or Dutch) is admitted to a hospital in Italy.
2. They are transferred to the Netherlands.
3. The Dutch multidisciplinary team (MDT) needs the Italian record to agree on treatment.
4. **Before:** the Italian hospital must build database mappers that emit FHIR, OMOP or similar.
5. **With the agent:** that no longer matters. It picks up scans, crawls
   databases, uses apps on screen, and emits whatever output format the MDT asks for.

The demo VM plays the Italian hospital. Both UIs (the tester's case strip and
pipeline, and the agent console header) use this narrative.

### The three scenarios

| # | Source | What the agent does | Returns | Time |
|---|---|---|---|---|
| 1 | **Hospital patient portal** (Epic MyChart / Mijn Dossier, browser) | Opens the logged-in portal, goes to *Uitslagen* (results), reads the latest lab results | Lab observations with values, units, dates | ~1 min (portal-dependent) |
| 2 | **Scanned ECG** (image file on the desktop) | Opens the `assets` folder, opens `ecg.jpg`, reads what is **printed** on it | ECG report + one observation per printed value: rate, PR, QRS, QT, QTc, axes, printed statements | ~30–60 s |
| 3 | **Italian oncology database** (SQL Server Management Studio) | Writes and runs read-only queries on an Italian-language schema (`paziente`, `esame_laboratorio`) | Patient + recent labs (e.g., *Emoglobina*, *Creatinina*, CEA), translated into FHIR/OMOP | ~1 min |

You can switch the output after the run: **FHIR**, **OMOP**, JSON, HL7 v2, or a
**custom schema**. A Dutch example is prefilled. The results are mapped again
without repeating the computer work.

### What you see during the demo

1. **The workstation (remote desktop).** Windows open and the mouse moves; in the
   browser, red rings mark each click. SQL is typed into SSMS. Afterwards the
   agent closes everything it opened.
2. **The agent console** (Windows Terminal, "HEALTH REWIRED MUNICH 2026" block
   title). It shows the same three acts as the tester (1 · ASK → 2 · WATCH →
   3 · RECEIVE) and a plain-language running commentary:
   - `REQUEST`: what was asked.
   - `ACTION`: what it is doing on screen.
   - `QUERY`: the exact SQL it ran.
   - `THINKING`: a short summary of the model's reasoning.
   - `FOUND`: each value it extracted.
   - `[DONE]`: total time.
3. **The test page** (browser). Scenario buttons, a live timeline with a spinner,
   a *What was found* summary in readable form, and the formatted output.

### Safety boundaries built in

- **Reads, does not interpret.** For the ECG, the agent copies only what is
  printed or plainly visible (for example "Printed on ECG: Rate 63; PR 176 …").
  It adds no diagnosis of its own. ECG items are marked *preliminary:
  transcribed by AI, verify against source*.
- **Verified or nothing.** Every value must come from a screen or file the agent
  actually opened. It checks the patient identity, and it stops with a clear
  reason (such as "portal session expired – log in again") rather than guess.
- **Narrow permissions.**
  - Each scenario gets only its own tools.
  - SQL must be read-only (`SELECT`) and limited to the demo database.
  - The browser stays on one approved site and may type only the requested
    patient ID.
- **Read-only accounts still required.** The instructions to the AI are not a
  security control. The source system's account must itself be read-only.
- **Synthetic data only.** The model runs in Azure AI Foundry (GlobalStandard
  deployment). Processing location is not guaranteed to stay in one country.
  Real patient data would need approved hosting, identity, and a data
  processing agreement.

### Honest limitations

- **Speed:** a model looking at screens takes 30–70 s per request. Code written
  for one system would be faster, but the agent adapts to a German or Italian
  system without new code.
- **Accuracy:** screen and image reading can err. The output is a draft for
  human verification, not a final record.
- **Throughput:** one request at a time on one workstation. This is a
  demonstration, not a production interface engine.

---

## For operators: technical reference

The sections below cover setup, running, and the API.

## Start the terminal and API

```powershell
cd .\demos\epic-ehr\service
uv sync --locked --extra test --default-index https://pypi.org/simple
Copy-Item .env.example .env
```

Set `API_BEARER_TOKEN` to a generated secret in the ignored `.env` file or process
environment. Do not use the example placeholder. Then:

```powershell
.\run.ps1
# Preview without starting a server:
.\run.ps1 -BannerOnly
```

The API listens on `127.0.0.1:8000`. The console shows a plain-language
timeline per job: steps, SQL queries, reasoning summaries, and extracted values.
Because it shows clinical values, use synthetic data only. Stop with Ctrl+C.

On the VM the agent opens in a portable Windows Terminal (`agent-terminal.ps1`,
profile in `service\terminal\settings.json`: 18 pt font, MDT colours). Zoom with
Ctrl + / Ctrl − (or Ctrl+scroll), F11 for full screen; the header reflows from a
one-line block title to two lines to plain text as the font grows.
`run.ps1 -KeepAlive` restarts the agent in the same tab after a crash or deploy.
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
Three packaged `SKILL.md` modules implement `epic-browser`, `local-files`, and
`sql-desktop`.
Each request gets an isolated empty-mode CLI session with only the selected
skill eagerly loaded and that skill's host tools. Generic shell, filesystem,
network, built-in skills, plugins, and configuration discovery are not enabled.
Browser lifecycle and actions run on one dedicated thread.

Provision the SDK-matched runtime before an offline demonstration:

```powershell
uv run --frozen python -m copilot download-runtime
```

Set the Copilot model name in `MODEL_DEPLOYMENT`; `gpt-6-astra` is the requested
default, not a guarantee of account availability. Supply `COPILOT_GITHUB_TOKEN`
for the isolated runtime. Alternatively, configure `AZURE_AI_FOUNDRY_ENDPOINT`
and use Entra ID (`DefaultAzureCredential`) for Azure BYOM; then
`MODEL_DEPLOYMENT` is your deployment name. API-key authentication is not used.

The repository's configured Foundry target is account
`nl-stu-jvw-ai-saoyr2` in `nl-stu-jvw-foundry-rg`, Sweden Central. For the
medical agent's Azure BYOM mode, set these values in the local environment or
the VM's **Configure Epic Agent** file:

```text
AZURE_AI_FOUNDRY_ENDPOINT=https://nl-stu-jvw-ai-saoyr2.openai.azure.com
MODEL_DEPLOYMENT=nl-stu-jvw-gpt-6-astra
```

The deployment serves `gpt-6-astra` version `2026-09-03`. Its SKU is
**GlobalStandard**: the resource's Sweden location does not guarantee that
inference stays in Sweden. Use only synthetic data in this demo.

These two values, plus `AZURE_SUBSCRIPTION_ID`, `AZURE_TENANT_ID`,
`AZURE_AI_RESOURCE_GROUP`, `AZURE_AI_ACCOUNT_NAME`, and `AZURE_AI_LOCATION`,
are saved as GitHub repository **variables**, not secrets. Variables do not
authenticate a process or automatically update local/VM configuration.
The account disables API-key authentication; use an authorized Entra identity
through `DefaultAzureCredential`. A VM identity needs inference permission on
this account; GitHub Actions should use an explicitly configured OIDC identity,
not a copied Azure account key. Neither identity is provisioned by saving variables.

This Astra selection applies to the medical agent's Copilot host-tool skills.
It does not establish compatibility with the plant agent's native
`computer_use_preview` tool, and no such model deployment was found in this
account. Keep that agent's model selection separate.

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
   EPIC_READY_URL_PREFIX=https://your-authorized-epic-host/chart
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
Each click displays a temporary red ring in the visible browser before the
Playwright action, so the RDP/Bastion presenter can follow computer use.
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
Copy the **forwarded port** URL, for example
`https://<tunnel-id>-8000.<region>.devtunnels.ms`, not the port-less
**Inspect network activity** URL. The integrated launcher labels the forwarded
address **API HTTPS URL (copy this)**.
Response links are relative, so they also work behind Host-rewriting tunnels.
Interactive clients authenticate to the tunnel. For programmatic clients, obtain
a tunnel connect token using your devtunnel CLI's token command and send it as
`X-Tunnel-Authorization: tunnel <connect-token>`; continue sending
the API `Authorization` header separately. Treat both tokens as secrets.
Never send patient data in URL parameters.

```powershell
# Run in the VM's hosting account; never publish or save the token in plaintext.
devtunnel list
devtunnel token <tunnel-id> --scopes connect
```

Run these commands in the VM under the Windows account and devtunnel sign-in
that started the host. Use the management **Tunnel ID** returned by
`devtunnel list`, including its region suffix. Do not derive it from the
forwarding URL: the URL's hostname prefix and the management ID can differ.
Paste the raw connect token into the tester's separate tunnel-token field;
the VM API bearer remains required in its own field.

See [Microsoft's dev tunnel security guidance](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/security).

This is for authorized synthetic demonstrations, not an approved PHI transport.
For clinical use, replace it with organization-approved private ingress, Entra ID
authorization and TLS. The demo API has one shared operator principal, not
multi-user or patient-level authorization.

## Local testing UI and VM startup

On the Windows VM, RDP through Bastion, manually sign in to the dedicated
authorized Epic browser, then start the API and its authenticated tunnel as one
owned process:

```powershell
.\run.ps1 -WithTunnel
```

It waits for loopback health and prints the **actual** HTTPS `devtunnels.ms`
URL only after the CLI establishes it. `devtunnel user login` is manual and
must be completed first. Ctrl+C closes both owned children. It never tunnels
CDP port 9222 or RDP port 3389.

On the local machine, install the demo package, then run:

```powershell
cd .\demos\epic-ehr\service
uv sync --locked --extra test --default-index https://pypi.org/simple
.\testing.ps1
```

When the deployment's protected `.azure\rg-epic-demo-swc` state contains the
named tunnel origin, API bearer token, and tunnel connect token, `testing.ps1`
decrypts them only into the tester process and opens `http://127.0.0.1:8765`.
The URL is prefilled and the credential fields stay blank: the loopback relay
uses the protected defaults server-side, so no demo-time copy/paste is needed.
Use `-ManualCredentials` to disable this behavior.

Add `-Stage` (or open `/?mode=stage`, or click **Stage mode** in the header)
for the presenter layout. It shows one screen in three acts (Ask → Watch →
Receive) under a case strip (Italy → Netherlands → Dutch MDT; before/with the
agent) and a sticky Italian hospital → Agent → For the Dutch MDT strip. It uses
projector-sized text, a large "current step" line, and format chips that
re-render the last result. The instruction text, output contract, job status and
connection controls sit behind **Details**. Keys: `1`/`2`/`3` run a source, `F`
cycles formats, `D` toggles details, `Esc` stops watching. `start-demo.ps1`
opens Stage mode by default. The tester binds its port exclusively and exits
with a clear error if another tester already uses it.

The local UI uses a loopback-only same-origin relay rather than changing API
CORS or using an anonymous tunnel. It accepts only an HTTPS
`*.devtunnels.ms` origin and fixed job/result/file routes. Secrets are never
embedded in the page or persisted by the tester. Fixture mode remains the safe
default. `bypass_cache` intentionally causes live skill work only in the
Copilot backend, so use it only after the manual authorized browser login.

For the complete no-copy/paste startup, run:

```powershell
.\demos\epic-ehr\start-demo.ps1 -SubscriptionId <subscription-id>
```

It starts the VM, obtains fresh `host` and `connect` tokens through the locally
signed-in Dev Tunnel CLI, stores them with Windows Data Protection API (DPAPI),
updates the VM host task through protected Run Command parameters, opens the
Bastion RDP connection, and starts the preconfigured local tester. It never
prints either token. In RDP, double-click **Epic Live Demo** and complete the
manual read-only Epic login. The visible agent and browser remain in the RDP
session.

`infra\enable-demo-mode.ps1` remains available when the VM and RDP session are
already running and only the protected tunnel credentials/shortcut need refresh.

## Three-scenario demo runbook

| # | Button | Skill | What the agent does | Typical time |
|---|---|---|---|---|
| 1 | Browser EHR | `epic-browser` | Navigates the logged-in Mijn Dossier session → Uitslagen, reads 5 results | depends on portal |
| 2 | Local clinical files | `local-files` | Lists Desktop `assets`, opens `ecg.jpg`, transcribes only printed/visible data (rate, PR, QRS, QT/QTc, axes, printed statements, speed/gain) → DiagnosticReport + one Observation per measurement | ~30 s |
| 3 | Italian SSMS | `sql-desktop` | Opens SSMS on `OncologiaDemo`, writes 2 read-only queries on the Italian schema → Patient + 8 labs | ~55 s |

Before the demo:

1. `start-demo.ps1`, then log in to Mijn Dossier in the VM's Edge **just before**
   running scenario 1 (MyChart logs out after ~20 min idle; the agent then stops
   with `session_expired` and the UI says to log in again).
2. Keep the RDP window **restored**. A minimized RDP client stops drawing and
   ignores keyboard input, so SSMS reports `rdp_minimized`. The local registry
   value `HKCU\Software\Microsoft\Terminal Server Client\RemoteDesktop_SuppressWhenMinimized=2`
   (set once; applies to new RDP connections) keeps a minimized session live.
   A **closed/disconnected** RDP window gives the same error; run
   `infra\keep-session-alive.ps1` to move the session to the VM console
   (`tscon`) so it keeps rendering without any RDP client. Reconnecting RDP
   takes it back.
3. Output: pick FHIR, OMOP, JSON, … or **Custom schema / ontology** (paste any
   JSON schema, example, or description; a Dutch example is prefilled).
   **Show last result in this format** re-renders the same job without rerunning
   computer use.

What the audience sees:

- **VM console window** (Rich TUI in Windows Terminal): big "HEALTH REWIRED
  MUNICH 2026" title, the ASK → WATCH → RECEIVE acts with live status, plus a
  scrolling log in plain clinical language (`REQUEST`, `ACTION`, `QUERY`,
  `THINKING`, `FOUND`, `DONE`). `THINKING` lines are
  the model's reasoning summaries (`EPIC_REASONING_SUMMARY`=`none|concise|detailed`,
  default `concise`). `EPIC_TUI=0` falls back to plain log lines.
- **Test UI**: the same lines as a live timeline (job status field `timeline`),
  a "What was found" summary, and the formatted output.
- Each skill closes what it opened (SSMS, the `assets` folder, the ECG viewer),
  so the desktop is clean for the next scenario.

Operational notes:

- The model deployment needs real throughput; 10K TPM throttled every run.
  The Foundry deployment runs at 300K TPM. `EPIC_REASONING_EFFORT` defaults
  to `low` for demo speed.
- The deployment name is custom, so the runtime can't infer vision support. The
  host declares vision capabilities on the session; without that, tool images
  never reached the model.
- SQL Server uses a trusted local `localhost` TLS certificate (SSMS 20 enforces
  encryption). Each SQL run closes leftover SSMS instances and clears SSMS
  auto-recover files, so no dialog blocks the agent.

Operator inner loop (diagnose → fix → release → test, about 5 min):

```powershell
cd .\demos\epic-ehr\infra
.\deploy-changed.ps1 -Files src\epic_adapter\desktop.py   # zip + chunked Run Command, restarts API only
.\run-scenario.ps1 -Scenario sql -Format fhir -Schema '{"labuitslagen":[{"test_nl":"...","waarde":0}]}'
```

`run-scenario.ps1` prints the readable timeline, the result, the per-step agent trace, and downloads
screenshots to `.azure\<rg>\diagnostics\<run>` (gitignored; may contain real
portal screenshots).

## Versioned release and desktop launcher

Tagged `epic-v*` releases run the Windows service tests, build the wheel and a
locked release archive, publish the archive to GitHub Releases, and attach a
GitHub build-provenance attestation. The archive contains tracked source,
synthetic fixtures, the dependency lock and a commit/tag manifest; it excludes
local `.env`, browser profiles, audit output, screenshots, downloads and virtual
environments.

Install the launcher separately in the interactive Windows account:

```powershell
cd .\demos\epic-ehr\launcher
.\Bootstrap-EpicDemo.ps1
.\Start-EpicDemo.ps1 -Mode InstallVersion -Version epic-v0.3.1
```

Bootstrap is idempotent and creates **Start Epic Demo** on that user's desktop.
The launcher supports an exact selected tag, an operator-reviewed channel
mapping, or the already-installed version. It never selects the newest release
implicitly. Private release downloads use `EPIC_RELEASE_GITHUB_TOKEN` only from
the installing process; the token is not persisted. The launcher verifies the
keyless Sigstore bundle against the exact GitHub Actions workflow and tag
identity before staging proceeds.

Each version has its own immutable directory. Configuration, API token, browser
profile and audit output remain outside version directories. Before an update,
the launcher calls the authenticated drain endpoint: new jobs stop, active jobs
finish, and a timeout resumes acceptance and cancels the update. The candidate
must restore locked dependencies and pass a synthetic API retrieval. Activation
must pass loopback health; otherwise the previous working version is restarted.
Running an installed version does not contact GitHub.

## API and output formats

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/retrieval-jobs` | Patient-scoped retrieval (`files`, `ehr`, `both`) |
| GET | `/v1/retrieval-jobs/{job_id}` | Job status, no clinical result |
| GET | `/v1/retrieval-jobs/{job_id}/result` | Default: FHIR JSON |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=json` | Normalized JSON |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=fhir` | FHIR R4-style Bundle |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=fhir-xml` | Explicit-subset FHIR XML |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=hl7` | HL7 v2.5.1 ORU observation/report projection |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=ndjson` | Normalized resource lines |
| GET | `/v1/retrieval-jobs/{job_id}/result?format=omop` | OMOP CDM 5.4 JSON (source values, unmapped concepts) |
| POST | `/v1/retrieval-jobs/{job_id}/transform` | Model-assisted mapping to any target schema/ontology: body `{"schema": "..."}` |
| GET | `/v1/admin/diagnostics?runs=N` | Authenticated per-run agent traces (may contain clinical screenshots) |
| GET | `/v1/retrieval-jobs/{job_id}/files/{file_id}` | Original file, reverified before download |
| GET | `/healthz` | Process health only |
| GET | `/v1/readiness` | Authenticated API/files/browser/login and active-job readiness |
| POST | `/v1/admin/drain?timeout_seconds=60` | Authenticated update drain; timeout resumes acceptance |

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
uv run --frozen --extra test python -m unittest discover tests -v
uv run --frozen epic-agent --banner-only
```

Unit/API tests use fixtures and mocked model calls; they do not contact Epic or
Azure. Infrastructure template and image preparation are in `infra\`.

## Dependency maintenance

Commit `service\uv.lock` together with `service\pyproject.toml` so installations
use the reviewed dependency set. The lock uses public PyPI artifact URLs and
SHA-256 hashes, not machine-specific package-feed URLs. From `service\`, refresh
compatible stable releases and verify them before committing. The launchers use
`--frozen` so starting either UI does not rewrite the lock:

```powershell
uv lock --upgrade --default-index https://pypi.org/simple
uv sync --locked --extra test --default-index https://pypi.org/simple
uv run --frozen --extra test python -m unittest discover tests -v
```

The Copilot SDK is deliberately pinned because its matched CLI runtime and
session isolation APIs are part of the demo's behavior. Upgrade that pin
explicitly, provision the matching runtime, and verify the guarded skill
sessions rather than assuming `uv lock --upgrade` changes it.
