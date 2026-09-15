# Coding Conventions

## Core Sections (Required)

### 1) Naming Rules

| Item | Rule | Example | Evidence |
|------|------|---------|----------|
| Files | PascalCase for C#/XAML; snake_case for Python | `MainWindow.xaml.cs`, `file_catalog.py` | `demos/plant-operations/app/`, `demos/epic-ehr/service/` |
| Functions/methods | PascalCase in C#; snake_case in Python | `ResetDemo`, `normalized_json` | `demos/plant-operations/app/ViewModels/MainViewModel.cs`, `demos/epic-ehr/service/src/epic_adapter/formats.py` |
| Types | PascalCase | `JobService`, `MainViewModel` | `demos/epic-ehr/service/src/epic_adapter/jobs.py` |
| Constants/env vars | UPPER_SNAKE_CASE in Python | `ALLOWED_EXTENSIONS`, `EPIC_BACKEND` | `demos/epic-ehr/service/src/epic_adapter/file_catalog.py` |

### 2) Formatting and Linting

- Formatter: none configured. `[TODO]`
- Linter: none configured. `[TODO]`
- C# uses nullable references and implicit usings through project properties.
- Epic Python uses a `src/` package layout, relative internal imports, Pydantic
  boundary models, and type annotations.
- Current validation commands are `dotnet build .\computer-use-demos.slnx` and
  `python -m compileall -q ...`.

### 3) Import and Module Conventions

- Python standard-library imports precede third-party and local imports.
- C# uses namespaces that match the project and layer.
- No path aliases or Python package barrels are configured.

### 4) Error and Logging Conventions

- Configuration and incomplete-job errors raise `RuntimeError`; missing jobs and
  fixture patients raise `LookupError`; invalid patient identifiers raise
  `ValueError`.
- FastAPI maps these boundary failures to explicit HTTP status codes.
- Unsupported Epic browser actions raise `ValueError`; the plant executor currently
  logs and returns an error-shaped description.
- Epic audit events are JSON Lines and contain a SHA-256 patient hash rather than
  the patient identifier.
- Rich terminal progress contains job IDs, phases and counts only. Exceptions are
  logged by type, without messages or tracebacks that could contain PHI.
- Sensitive values are read from environment variables and excluded from source.

### 5) Testing Conventions

- Epic tests live in `service/tests/`, use `test_*.py`, and subclass
  `unittest.TestCase`.
- Temporary directories isolate filesystem and audit tests.
- No coverage policy exists. `[TODO]`

### 6) Evidence

- `demos/epic-ehr/service/src/epic_adapter/models.py`
- `demos/epic-ehr/service/src/epic_adapter/api.py`
- `demos/epic-ehr/service/tests/test_api.py`
- `SECURITY.md`
