# Epic desktop launcher

The launcher is installed separately from immutable version directories. It
keeps `.env`, browser profile, audit output and approved local files under the
current Windows user's `%LOCALAPPDATA%\EpicDemo\shared` directory.

```powershell
.\Bootstrap-EpicDemo.ps1
# Safe to run repeatedly.

.\Start-EpicDemo.ps1 -Mode InstallVersion -Version epic-v0.3.0
.\Start-EpicDemo.ps1 -Mode ApprovedChannel -Channel stable
.\Start-EpicDemo.ps1 -Mode RunInstalled
```

`channels.json` maps a reviewed channel to an exact tag; the launcher never
selects GitHub's newest release automatically. A private repository requires
`EPIC_RELEASE_GITHUB_TOKEN` in the installing shell. The token is not written
to launcher state. Installation verifies the GitHub artifact attestation,
restores locked dependencies, and runs a synthetic API retrieval before
activation.

An update asks the authenticated API to stop accepting new work and drain active
jobs. Timeout resumes job acceptance and cancels the update. Successful drain
stops only the launcher-owned API process. Activation failure starts the
previous working release. An installed release starts without contacting GitHub.

The **Start Epic Demo** shortcut runs in the current RDP/Bastion user session.
Live mode opens the dedicated Edge profile at `EPIC_READY_URL_PREFIX`; manual
read-only Epic login remains required. The API's authenticated `/v1/readiness`
endpoint reports API, files, browser, login URL and active-job state separately.
