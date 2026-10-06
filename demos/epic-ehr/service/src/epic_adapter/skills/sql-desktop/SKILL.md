---
name: sql-desktop
description: Open SSMS on this workstation's local SQL Server, discover an unfamiliar database schema with read-only queries, find the requested patient and return the data as FHIR R4 resources.
---

# Local database via SSMS - unknown schema

You get a task, a patient name and a patient identifier. You are NOT told the
table or column names. The schema is local, undocumented and may use another
language. Discover it.

## Tools

- `observe` - opens SSMS already connected to the local database (Windows
  authentication) and returns a screenshot. If a *Connect to Server* dialog
  appears, click **Connect**.
- `run_query` - replaces the editor text with ONE read-only query, runs it and
  returns a screenshot of the results grid.
- `click`, `press_key`, `scroll` - only to reveal grid content.

`run_query` rules (enforced by the host): one statement, `SELECT`/`WITH` only,
no comments, no `INTO`/DML/DDL/`EXEC`, no other databases. A rejected query
returns the reason: fix it and retry. Click in the editor if focus was lost.

## How to work

1. `observe`.
2. Discover tables and columns in one grid, one row per table:
   `SELECT TABLE_SCHEMA, TABLE_NAME, STRING_AGG(CAST(COLUMN_NAME AS varchar(max)), ', ') WITHIN GROUP (ORDER BY ORDINAL_POSITION) AS cols FROM INFORMATION_SCHEMA.COLUMNS GROUP BY TABLE_SCHEMA, TABLE_NAME ORDER BY TABLE_NAME`
   Scroll the grid or re-run it filtered (`WHERE TABLE_NAME IN (...)`) only
   if column lists you need are cut off. Spend at most 3 queries on schema
   discovery in total.
3. Find the patient table. The request `patient_id` is the hospital record
   number (MRN), usually a text column; the integer key is internal.
4. **Run a compact patient-only query before reading clinical rows.** Select
   only the MRN, given name, family name, date of birth and internal key, and
   filter by the exact requested MRN. The single visible result row is the
   patient verification: confirm the MRN and name, plus date of birth. Do not
   stop with `patient_not_verified` while this read-only query is available.
5. Read the clinical tables that serve the requested resource types, joined
   through the verified internal patient key. Include the requested MRN in each
   clinical query so the visible grid keeps the patient association explicit.
   Typical content to look for (names differ per hospital; use the schema):
   - `observations`: laboratory results (latest first, `TOP 10`), vital signs,
     tumour biomarkers.
   - `encounters`: admissions / episodes of care.
   - `documents`: diagnoses / problem list, medications, procedures,
     pathology, tumour staging, medical history, clinical alerts or events.
   - `imaging`: imaging studies with their report and conclusion.
   Skip categories for resource types that were not requested. **Cover every
   requested resource type with at least one query before refining any of
   them**; a good order is encounters, documents (diagnoses, medications,
   then the rest via one `UNION ALL`), imaging, then observations (labs,
   vitals, biomarkers). Copy column names exactly from the schema grid; if a
   query errors, fix the named identifier and retry once.
6. Keep grids readable: a few narrow columns per query. For long text
   (reports, conclusions, descriptions) select the date plus that one text
   column so it spans the grid. Several small lists may be combined with
   `UNION ALL` into one grid of `category, date, code, text` columns.
7. Read the grids from the screenshots, then `finish`.

**Speed matters (live demo):** at most 12 queries, at most 16 observations.
Prefer narrow result grids; never use `SELECT *`.

## Translation to FHIR (finish)

`patient_id` = the requested MRN.

- `patient`: `source_id` = MRN; `identifier[{system:"urn:local-db:mrn",
  value}]`, `name[{family, given}]`, `gender` (M -> male, F -> female),
  `birthDate`.
- `observations` (one per row): `status: "final"`, `category` laboratory or
  vital-signs, `code{coding:[{system:"urn:local-db:code", code, display}],
  text}` with `display` and `text` translated into English (keep the source
  `code` as is), `subject.reference:"Patient/<MRN>"`,
  `effectiveDateTime`, `valueQuantity{value, unit}`, `referenceRange`,
  `interpretation` when present. Add LOINC only when certain (haemoglobin
  718-7, creatinine 2160-0, leukocytes 6690-2, platelets 777-3, CEA 2039-6,
  CA 19-9 24108-3, heart rate 8867-4). Vital-sign rows give one observation
  per measured value; a pending biomarker uses `status: "registered"` and
  `valueString`.
- `encounters` (one per episode): `status` (finished when an end date is
  shown), `class` (inpatient / emergency / ambulatory), `period{start,end}`,
  `reasonCode[{text}]`, discharge or transfer destination text when shown.
- `documents` (one per clinical topic, e.g. `source_id` `diagnoses`,
  `medications`, `procedures`, `pathology`, `staging`, `history`):
  `status: "current"`, `type.text` (English topic name), `date`,
  `description` = the visible rows as a faithful English list, keeping codes
  (e.g. `ICD-9-CM 153.3`), doses, routes and dates exactly.
- `imaging` (one per study, FHIR DiagnosticReport): `status: "final"`,
  `code.text` (modality and body region), `effectiveDateTime`, `conclusion`
  = the visible conclusion translated into English.

Only report values visible in the grid. Never infer diagnoses or fill gaps.
Return all terminology in English; never translate personal names or
identifiers.
Synthetic training data only.
