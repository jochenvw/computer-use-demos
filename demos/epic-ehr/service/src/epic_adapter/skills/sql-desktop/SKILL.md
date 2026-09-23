---
name: sql-desktop
description: Open SSMS on the demo VM, connect to the local SQL Server database OncologiaDemo (Italian oncology schema), write read-only queries and return patient data as FHIR.
---

# SSMS – OncologiaDemo (Italian schema)

## Where the database runs

- The demo VM itself is the SQL Server: server `localhost`, **Windows
  authentication** (the logged-in `demoadmin` account – no password needed).
- Database **`OncologiaDemo`**, schema **`oncologia_demo`** (all Italian names).
- SSMS 20 is installed. `observe` launches SSMS already connected
  (`-S localhost -E -d OncologiaDemo`) with an empty query editor, and returns a
  screenshot. If a *Connect to Server* dialog appears, click **Connect**
  (Authentication = Windows Authentication, Server = localhost).

## Key tables (always prefix `oncologia_demo.`)

| Table | Useful columns |
|---|---|
| `paziente` | `paziente_id` (int PK), `mrn` (e.g. `SYN-2026-0001`), `nome`, `cognome`, `sesso`, `data_nascita`, `comune_residenza`, `stato_sintetico` |
| `esame_laboratorio` | `paziente_id`, `data_ora`, `codice`, `nome_esame`, `valore_numerico`, `valore_testo`, `unita`, `range_basso`, `range_alto`, `flag_anomalia` |
| `osservazione_vitale` | `paziente_id`, `data_ora`, `frequenza_cardiaca`, `pressione_sistolica`, `pressione_diastolica`, `frequenza_respiratoria`, `spo2`, `temperatura`, `news2` |
| `diagnosi` | `paziente_id`, `sistema_codifica` (ICD-9-CM), `codice`, `descrizione`, `data_diagnosi`, `attiva` |
| `terapia_farmacologica` | `paziente_id`, `farmaco`, `dose`, `via`, `frequenza`, `data_inizio`, `stato` |
| `episodio` | `paziente_id`, `tipo_episodio`, `data_inizio`, `data_fine`, `motivo`, `stato` |

Also: `neoplasia`, `biomarcatore`, `imaging`, `anatomia_patologica`,
`valutazione_funzione`, `alert_clinico`, views `v_mdt_patient_summary`,
`v_timeline_ai`. To discover columns, query
`SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='oncologia_demo'`.

The API `patient_id` is the **MRN** (`paziente.mrn`), not the integer key.
Always join through `paziente`: `JOIN oncologia_demo.paziente p ON p.paziente_id = x.paziente_id WHERE p.mrn = N'<patient_id>'`.

## Workflow

1. `observe` → SSMS opens, connected.
2. `run_query` with the patient query, e.g.
   `SELECT p.mrn, p.nome, p.cognome, p.sesso, p.data_nascita FROM oncologia_demo.paziente p WHERE p.mrn = N'SYN-2026-0001'`
3. ONE `run_query` for the latest labs only (keeps the demo fast):
   `SELECT TOP 8 e.data_ora, e.codice, e.nome_esame, e.valore_numerico, e.unita, e.range_basso, e.range_alto, e.flag_anomalia FROM oncologia_demo.esame_laboratorio e JOIN oncologia_demo.paziente p ON p.paziente_id = e.paziente_id WHERE p.mrn = N'SYN-2026-0001' ORDER BY e.data_ora DESC`
4. Read the results grid in the screenshot, then `finish` immediately.
   Do NOT query vitals or other tables unless explicitly requested.

**Speed matters (live demo):** at most 3 queries, at most 8 observations,
keep each resource minimal (only the fields below, no narrative text).

`run_query` rules (enforced by the host): one statement, `SELECT`/`WITH` only,
no comments, no `INTO`/DML/DDL/`EXEC`, no other databases. A rejected query
returns the reason – fix it and retry. If you clicked outside the editor,
click in the query text area before the next `run_query`.

## Translation to FHIR (finish)

`patient_id` = the requested MRN.

- `patient`: `source_id` = MRN; data `identifier[{system:"urn:oncologiademo:mrn", value}]`,
  `name[{family: cognome, given:[nome]}]`, `gender` (M→male, F→female),
  `birthDate` (YYYY-MM-DD).
- `observations` (one per lab row / vital sign): `source_id` e.g. `lab-HB-1`;
  data `status:"final"`, `category` laboratory or vital-signs,
  `code{coding:[{system:"urn:oncologiademo:codice", code: codice, display: nome_esame}], text: nome_esame}`,
  `subject.reference:"Patient/<MRN>"`, `effectiveDateTime` (ISO 8601 from `data_ora`),
  `valueQuantity{value, unit}`, `referenceRange[{low, high}]` when present,
  `interpretation[{text: flag_anomalia}]` when present. Add LOINC codings only
  when certain (e.g. Emoglobina 718-7, Creatinina 2160-0, eGFR 33914-3,
  Leucociti 6690-2, Piastrine 777-3, heart rate 8867-4).

Only report values visible in the grid; keep Italian source text in `display`
/ `text`. Synthetic data – never infer diagnoses or fill missing values.
