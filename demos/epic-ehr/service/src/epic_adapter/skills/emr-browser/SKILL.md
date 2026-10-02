---
name: emr-browser
description: Read a requested patient's clinical data from an unfamiliar clinician EMR (electronic medical record) shown in the approved browser tab, and return it as FHIR R4 resources.
---

# Clinician EMR - read-only retrieval

You get a task, a patient name and a patient identifier. You are NOT told
which EMR this is, how it is organised or which language it uses. Discover it.

## Tools

- `observe` - screenshot of the approved browser tab.
- `click` - click a link, tab or button (pixel coordinates from the screenshot).
- `type_text` - type ONLY the exact patient name or identifier from the
  request. Click the input first; press `Enter` with `press_key` to submit.
- `press_key`, `scroll` - navigate and reveal content.
- `finish` / `stop`.

## How to work

1. `observe`. Identify the screen: worklist, search, chart, sign-in page.
2. Find the patient. Typical EMRs offer a ward list / worklist, or a search
   box. Use whatever this one offers.
3. Verify identity before reading anything: the name AND the identifier or
   date of birth on screen must match the request. Similar names exist.
4. Open the chart and explore its sections (summary, labs, notes, specialty
   views). Menus may be in a foreign language: translate as you read.
5. Read only what is visible. Never type anything other than the patient
   name or identifier, and never submit forms that change data.
6. `finish` as soon as the requested resources are collected.

Stop reasons: `session_expired` (sign-in page), `patient_not_verified`,
`unavailable_data`, `record_write_required`, `unsupported_workflow`.

## Output (finish)

`patient_id` = the requested identifier. All text you return is English:
translate test names, encounter and note types and note text faithfully from
the source language (no additions, no omissions). Never translate personal
names, hospital or product names, identifiers or codes; keep numbers, unit
symbols and dates exactly. Add LOINC only when certain.

- `patient`: `name[{family, given}]`, `gender`, `birthDate` (YYYY-MM-DD).
- `encounters`: `status`, `class`, `period{start,end}`, `reasonCode` text,
  discharge / transfer destination text when shown.
- `observations`: one per lab value or vital sign: `status: "final"`,
  `code{coding, text}`, `effectiveDateTime` (ISO 8601), `valueQuantity{value,
  unit}` or `valueString`, `referenceRange` and `interpretation` when shown.
- `documents`: one per clinical note: `status: "current"`, `type.text`,
  `date`, `description` = the note text translated faithfully into English
  (shortened only with "...").
- `imaging`: only if the chart shows a report text; otherwise leave imaging
  to the PACS skill.

Never infer diagnoses, never fill missing values. Synthetic training data only.
