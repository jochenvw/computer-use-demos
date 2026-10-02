# Data Retrieval Agent - Ospedale di Montalcino: demo script

*Retrieves patient data from any system on this workstation, maps it to the
requested data standard, and shares it with the requesting hospital.*

No real or personal patient data is used. Anna Ricci (F, 1971-03-14,
`TUS-2026-0417`), Ospedale di Montalcino, SanitaCartella and MontalcinoPACS are
all synthetic.

## On stage (Munich, ~8 min)

1. **Story (30 s).** Anna collapses on holiday in Tuscany, is admitted to
   Ospedale di Montalcino on 2026-09-18 and transferred to UMC Utrecht. The
   Dutch MDT needs her Italian record. Connecting this hospital to the federated
   infrastructure would take months. Instead we deploy an agent inside the
   hospital and simply ask.
2. **The instruction (30 s).** Point at the typed input on the test page:
   *Retrieve all relevant medical information for patient Anna Ricci.* No
   system, path, table or menu. The console prints the same line as `TASK`.
3. **1 - Clinical data from the EMR (key `1`).** The agent finds Anna in the
   SanitaCartella worklist, opens her chart, reads labs and notes. Point out the
   dated Italian UI: a cheap, old, non-standard EMR.
4. **2 - Medical imaging from PACS (key `2`).** It follows the imaging link into
   MontalcinoPACS: report plus image. It transcribes only the signed report and
   marks it *Preliminary: transcribed by AI, verify against source*. No
   diagnosis of its own.
5. **3 - Local Italian database (key `3`).** Unknown schema, Italian column
   names, already on the VM. It explores the schema in SSMS and runs read-only
   queries.
6. **Handover (each run).** Closing line: *Handing over to the MDT dashboard,
   UMC Utrecht, in the requested standard: FHIR, OMOP or a custom schema.*
   Press `F` to cycle FHIR / OMOP / custom (SNOMED CT by default) without rerunning.

Fallbacks: offline fixture mode runs all three scenarios with the same
timeline; `EPIC_NAVIGATION_HINTS=1` if the live agent gets lost (invisible to
the audience); ECG fallback via `source: files`.

## Operator walkthrough (API)

1. Run `service\run.ps1` with a generated API bearer secret and the default
   fixture backend. Show the red ASCII cross and listening loopback API address.
   Fixture mode is offline and uses only synthetic records/files.
2. Set the caller header in a separate shell:

   ```powershell
   $headers = @{ Authorization = ("Bear" + "er " + $env:API_BEARER_TOKEN) }
   ```

3. Pre-warm the blood-pressure panel before the demo:

   ```powershell
   $bp = @{
     patient_id = "TUS-2026-0417"
     source = "ehr"
     resources = @("observations")
     observation_codes = @("85354-9")
   } | ConvertTo-Json
   $job = Invoke-RestMethod http://127.0.0.1:8000/v1/retrieval-jobs `
     -Method Post -Headers $headers -ContentType application/json -Body $bp
   Invoke-RestMethod "http://127.0.0.1:8000$($job.result_url)" -Headers $headers
   ```

   Default result output is `application/fhir+json`. The synthetic BP fixture is
   120/80 with LOINC `85354-9`, components `8480-6` and `8462-4`, and UCUM
   `mm[Hg]`.

4. Repeat the same POST. Show `cache_status: hit` on the job and
   `X-Retrieval-Cache: hit`, `X-Collected-At`, `X-Cache-Expires-At`, and
   `Cache-Control: no-store` on the result. The cache is a small in-memory
   LRU/TTL/byte-bound reuse cache; the job store is separately bounded and also
   process-local.
5. Force live work again:

   ```powershell
   $bpBypass = @{
     patient_id = "TUS-2026-0417"
     source = "ehr"
     resources = @("observations")
     observation_codes = @("85354-9")
     bypass_cache = $true
   } | ConvertTo-Json
   Invoke-RestMethod http://127.0.0.1:8000/v1/retrieval-jobs `
     -Method Post -Headers $headers -ContentType application/json -Body $bpBypass
   ```

   A successful bypass refreshes the cache. A failed bypass invalidates the old
   entry and does not return stale clinical data.

6. Request the ECG fallback (local files):

   ```powershell
   $ecg = @{
     patient_id = "TUS-2026-0417"
     source = "files"
     resources = @("ecg")
   } | ConvertTo-Json
   $job = Invoke-RestMethod http://127.0.0.1:8000/v1/retrieval-jobs `
     -Method Post -Headers $headers -ContentType application/json -Body $ecg
   Invoke-RestMethod "http://127.0.0.1:8000$($job.result_url)?format=json" -Headers $headers
   ```

   In fixture mode this lists scoped files. In Copilot mode the packaged
   `local-files` skill must list and open scoped handles, cite an opened file,
   and return existing documented ECG information only. It must not interpret
   waveforms or fall back silently to a catalog-only clinical answer for
   supported readable reports.

7. Show alternate output formats:

   ```powershell
   Invoke-WebRequest "http://127.0.0.1:8000$($job.result_url)?format=fhir-xml" -Headers $headers
   Invoke-WebRequest "http://127.0.0.1:8000$($job.result_url)?format=hl7" -Headers $headers
   Invoke-WebRequest "http://127.0.0.1:8000$($job.result_url)?format=ndjson" -Headers $headers
   ```

   FHIR JSON/XML are explicit illustrative subsets, not full profile validation.
   HL7 is a limited v2.5.1 ORU projection for supported observations and ECG
   DiagnosticReport conclusions. Unsupported data returns HTTP 422 instead of a
   fabricated representation. Original files remain available through job-scoped
   download links with hash recheck.

8. For separately authorized live training only, provision the SDK runtime with
   `uv run --frozen python -m copilot download-runtime`, open `browser.ps1`
   on the synthetic EMR (`http://127.0.0.1:8001/`, `EPIC_SYNTHETIC_PORTAL=1`)
   or, for a real EMR, sign in manually with a read-only account. Set
   `EPIC_BACKEND=copilot`, `EPIC_COMPUTER_USE_ENABLED=1`, exact `EPIC_ORIGIN`, loopback
   `EPIC_BROWSER_CDP_URL`, and `MODEL_DEPLOYMENT`. Use `COPILOT_GITHUB_TOKEN` in
   isolated mode, or optional Azure BYOM via `DefaultAzureCredential` bearer
   token. Do not use Azure API keys.
9. For repeatable demos, run `start-demo.ps1`. It starts the VM, refreshes scoped
   tunnel credentials without displaying them, opens RDP, and starts the local
   tester. In RDP, launch **Epic Live Demo** (legacy name); it starts the
   synthetic EMR and opens the worklist. The
   named private tunnel and encrypted local tester credentials remove all
   URL/token copy-paste.
10. Run `service\tunnel.ps1` only for ad-hoc authorized synthetic API access. Never tunnel
   the browser debugging port, commit `.env`, browser profiles, audit data, or
   runtime temp state, and do not claim live EMR/model verification unless an
   approved training-environment test was actually run.
