# Epic Retrieval Agent Walkthrough

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
     patient_id = "DEMO-100042"
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
     patient_id = "DEMO-100042"
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

6. Request the local ECG skill path:

   ```powershell
   $ecg = @{
     patient_id = "DEMO-100042"
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
   `uv run --frozen python -m copilot download-runtime`, launch `browser.ps1`, log in
   manually using a read-only account, set `EPIC_BACKEND=copilot`,
   `EPIC_COMPUTER_USE_ENABLED=1`, exact `EPIC_ORIGIN`, loopback
   `EPIC_BROWSER_CDP_URL`, and `MODEL_DEPLOYMENT`. Use `COPILOT_GITHUB_TOKEN` in
   isolated mode, or optional Azure BYOM via `DefaultAzureCredential` bearer
   token. Do not use Azure API keys.
9. Run `service\tunnel.ps1` only for authorized synthetic API access. Never tunnel
   the browser debugging port, commit `.env`, browser profiles, audit data, or
   runtime temp state, and do not claim live Epic/model verification unless an
   approved training-environment test was actually run.
