---
name: pacs-viewer
description: Find a requested patient's imaging studies in an unfamiliar PACS (picture archiving and communication system) web viewer in the approved browser tab, look at the images, and transcribe the radiology report as a preliminary FHIR DiagnosticReport.
---

# PACS - imaging report and images

You get a task, a patient name and a patient identifier. You are NOT told
where the PACS is or how it is organised. It may be reachable from the
clinical workstation's application bar or from the EMR chart. Discover it.

## Tools

`observe`, `click`, `type_text` (exact patient name or identifier only;
click the input first, then `press_key` `Enter`), `press_key`, `scroll`,
`finish`, `stop`.

## How to work

1. `observe`. Find the imaging / PACS application and its study list.
2. Find the patient's studies; verify name AND identifier or date of birth.
3. Open the most relevant study (MRI first, then CT). Page through a few
   images of one series so the images are visible on screen.
4. Read the radiology report (referto) printed next to the images.
5. `finish`.

## Safety - transcription only

- Transcribe the report text verbatim (source language is fine; an English
  rendering may follow in brackets). Do NOT describe the images yourself,
  do NOT add findings, measurements or a diagnosis that are not printed.
- Mark every report preliminary.

## Output (finish)

`patient_id` = the requested identifier. One `imaging` resource per study
read (FHIR R4 DiagnosticReport, without `resourceType`):

- `source_id`: the accession number shown.
- `status: "preliminary"`.
- `code: {coding:[{system:"http://loinc.org", code:"18748-4",
  display:"Diagnostic imaging study"}], text: <study description as shown>}`.
- `identifier: [{system:"urn:pacs:accession", value: <accession>}]`.
- `effectiveDateTime` as shown (ISO 8601); `performer[{display}]` = reporting
  radiologist when printed.
- `conclusion`: `"Report text: <verbatim conclusion>. Preliminary: transcribed
  by AI, verify against source."` - it MUST end with exactly
  `Preliminary: transcribed by AI, verify against source.`

Never interpret pixels clinically. Synthetic training data only.
