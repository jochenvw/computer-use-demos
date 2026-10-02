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
2. Discover tables and columns:
   `SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION`
   (filter with `WHERE TABLE_NAME LIKE ...` once you know candidates).
3. Find the patient table. The request `patient_id` is the hospital record
   number (MRN), usually a text column; the integer key is internal. Verify
   the name and date of birth match.
4. Join the data tables through the patient key. Latest rows first, `TOP 10`.
5. Read the grids from the screenshots, then `finish`.

**Speed matters (live demo):** at most 5 queries, at most 10 observations.

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
  CA 19-9 24108-3, heart rate 8867-4).

Only report values visible in the grid. Never infer diagnoses or fill gaps.
Return all terminology in English; never translate personal names or
identifiers.
Synthetic training data only.
