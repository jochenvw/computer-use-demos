# Security and privacy

This repository contains computer-use demonstrations. Production clinical use
requires a separate security, privacy, compliance, and clinical-safety review by
the organization operating the environment.

## Data handling

- The public Epic adapter uses only bundled synthetic records by default.
- Protected health information must not be written to logs, source files,
  prompts stored in Git, or diagnostics.
- Screenshots are sent to the configured AI endpoint while an agent is running.
- Prefer Entra ID authentication over API keys.
- Keep local `.env` files untracked; only placeholder `.env.example` files are
  committed.

## Live-control guardrails

Agents start in dry-run mode. Live actions require both the `--live` flag and:

```powershell
$env:ALLOW_COMPUTER_CONTROL = "1"
```

The plant capture layer requires its exact simulator window title. The Epic
worker captures only the tab on the configured HTTPS origin through a dedicated,
loopback-only browser debugging connection. It never captures the desktop.

## Epic adapter boundary

- The external API requires a bearer token in the demo implementation. Replace
  this with Microsoft Entra ID and an API gateway before non-demo use.
- The VM has no public IP. Remote administration uses Azure Bastion.
- The API should be reachable only over private networking.
- For synthetic dev demonstrations, `tunnel.ps1` uses an authenticated outbound
  dev tunnel, not anonymous access. Do not tunnel browser debugging port 9222.
- File discovery is limited to configured root directories and allowlisted
  clinical file extensions.
- The service hashes patient identifiers in audit records.
- Live Epic mode requires `EPIC_COMPUTER_USE_ENABLED=1`, a deployed GPT Astra
  model, and an authorized read-only Epic account. Prompt-level read-only
  instructions and output validation cannot enforce clinical permissions.
- This is a single-operator demo. A bearer token is not per-patient authorization.
- Patient identifiers are hashed in audit events, but hashes are not anonymization.
  Protect the audit file; do not expose it publicly.
- Browser profiles, cookies, screenshots and medical documents must never enter Git.

## Reporting a problem

Do not include secrets, real patient data, or screenshots containing sensitive
information in an issue. Reproduce the problem with the included synthetic data.
