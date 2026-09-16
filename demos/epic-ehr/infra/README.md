# Private SQL / Epic demo VM

The default deployment is a **SQL Server 2022 Developer / Windows Server 2022**
desktop in **Sweden Central**. SQL Developer is for development and testing,
not production. The VM has four vCPUs, 16 GiB RAM, a 128 GiB Premium OS disk,
Trusted Launch, and no public IP.

Two independent connections serve different purposes:

| Connection | Purpose |
|---|---|
| Azure Bastion Standard native tunnel | Local RDP client connects to `localhost:53389`, forwarded to VM port 3389 |
| Authenticated devtunnel | Local API tester calls the agent's HTTPS URL; VM API remains loopback-only |

Bastion native tunneling is enabled explicitly. The VM subnet denies other
inbound traffic, including SQL 1433, API 8000, and browser CDP 9222. A NAT gateway
provides explicit outbound access for dependencies, model requests, and devtunnel.
Its public IP is **not** a VM inbound endpoint.
An LRS storage account holds private, commit-versioned source archives. Public
blob access and Shared Key authentication are disabled. The signed-in publisher
gets Storage Blob Data Contributor scoped only to this account. Publishing uses
Entra authentication and a one-hour, read-only, single-blob user-delegation SAS
delivered as a protected Run Command parameter, not a command-line secret.

## Deploy and prepare

Run these commands from the repository root on Windows after `az login`.
Check current SKU/image availability, quota, permissions, and cost in your
subscription before creating resources.
Deployment also requires permission to create the scoped artifact-publisher
role assignment (for example Owner or User Access Administrator).

```powershell
$subscription = '<your-subscription-id>'
.\demos\epic-ehr\infra\deploy.ps1 -SubscriptionId $subscription
```

Defaults: resource group `rg-epic-demo-swc`, prefix `epicdemo`, region
`swedencentral`, VM size `Standard_D4as_v5`. `-ValidateOnly` creates/validates the
resource group and template but does not deploy VM/network resources.
The Bicep template also supports a custom generalized Windows image ID.

The deployment helper generates a `demoadmin` password, stores it using
Windows user-bound DPAPI in `.azure\rg-epic-demo-swc\vm-admin.credential.xml`,
and restricts the local state directory to the current Windows user and SYSTEM.
Temporary plaintext ARM parameter files are removed in `finally`; passwords
are never printed or committed. Preserve this encrypted credential on the
same Windows account/machine until you no longer need it.

Install signed Microsoft tools and the checksum-verified pinned `uv` release:

```powershell
.\demos\epic-ehr\infra\run-vm-script.ps1 `
  -SubscriptionId $subscription `
  -ScriptPath .\demos\epic-ehr\infra\bootstrap-tools.ps1 `
  -CommandName bootstrap-tools

.\demos\epic-ehr\infra\run-vm-script.ps1 `
  -SubscriptionId $subscription `
  -ScriptPath .\demos\epic-ehr\infra\initialize-sql.ps1 `
  -CommandName initialize-sql `
  -WithAdminCredential

.\demos\epic-ehr\infra\publish-agent.ps1 -SubscriptionId $subscription -SourceRef HEAD
```

The SQL setup uses the verified Windows administrator identity for SQL Windows
authentication rather than Run Command's SYSTEM identity. Credentials and the
short-lived archive URL travel as encrypted/protected Run Command parameters. Setup
creates only the `EpicDemo` synthetic database/tables if absent; it does not
replace existing data. SQL memory is capped at 8 GiB to leave room for Edge,
SSMS and the agent.

Publishing packages **tracked files from the selected Git commit**, verifies
the archive hash on the VM, installs dependencies and the SDK-matched runtime,
and exercises a synthetic FHIR BP retrieval. It preserves an existing `.env`.
The API bearer token is generated inside the VM, with file access limited to
SYSTEM and `demoadmin`. Copilot credentials, devtunnel login and Epic cookies
are not deployed or embedded in an image.

Managed Run Command reports its actual execution state and exit code; an ARM
resource's successful creation alone does not mean a bootstrap script worked.
Inspect a failed command before retrying. Use a new `-CommandName` for a
separate attempt if you want to preserve the previous diagnostic record.

## RDP from localhost

Keep this command running in one terminal:

```powershell
.\demos\epic-ehr\infra\connect.ps1 -SubscriptionId $subscription
```

In another terminal:

```powershell
mstsc /v:localhost:53389
```

Sign in as `.\demoadmin`. To copy the generated password locally without
printing it, run:

```powershell
$credential = Import-Clixml .\.azure\rg-epic-demo-swc\vm-admin.credential.xml
$credential.GetNetworkCredential().Password | Set-Clipboard
```

Paste into the RDP credential prompt, then clear the clipboard. The encrypted
credential is not portable to another Windows user or machine. Native Bastion
access requires the appropriate Azure read permissions for the VM/NIC/Bastion.
Ctrl+C in the tunnel terminal closes the connection.

## Try the agent and local tester

The VM desktop has shortcuts for:

- **Epic Agent Local Only**: safe fixture API, no model/browser calls.
- **Epic Agent with Tunnel**: agent plus owned authenticated devtunnel.
- **Configure Epic Agent**: opens the private `.env`.
- **Epic API Tester**: optional tester running on the VM itself.
- **SQL Server Management Studio**, **Synthetic SQL Demo.sql**, and a short
  **READ ME FIRST.txt**.

Inside the RDP session, first run `devtunnel user login` manually. Start
**Epic Agent with Tunnel** and copy its actual HTTPS URL. It cannot provide a
working remote URL before tunnel authentication and startup succeed.

On your **local** machine:

```powershell
.\demos\epic-ehr\service\testing.ps1
# Open the printed local address, normally http://127.0.0.1:8765
```

Paste the tunnel URL and the API bearer token from the VM's `.env` into the
masked fields. If tunnel access requires a connect token, generate one using
the devtunnel CLI for that tunnel and paste it into the separate masked field.
The tester does not persist credentials and does not require wildcard CORS or
an anonymous tunnel.

**Quick BP** selects the synthetic BP panel. Repeat a request for a cache hit;
check **Bypass cache** to run fresh work. **ECG file** selects the file source.
FHIR JSON is the default; JSON output includes original-file download links.
See `..\DEMO_SCRIPT.md` for the detailed API walkthrough.

For live Epic browser work, configure `EPIC_BACKEND=copilot`, the explicit
computer-use opt-in, exact Epic HTTPS origin, and an authorized Copilot token
or Azure BYOM identity. Start `service\browser.ps1` and log into Epic manually
using a read-only account before restarting the agent. Keep the interactive
desktop available. Fixture mode and cache hits intentionally do not perform
computer use.

## SQL / SSMS

SSMS connects to `localhost` using Windows authentication. Open the desktop
query against `EpicDemo`: it contains one explicitly synthetic patient and
systolic/diastolic observations (120/80 mmHg).

**The API does not yet control SSMS or expose a database retrieval source.**
The installed SQL/SSMS environment prepares for a future dedicated desktop
skill. The existing Epic skill controls only the approved browser tab.
Establish a read-only database identity before any future SQL computer-use
demo; the VM administrator is intentionally privileged for initial setup.

## Cost and lifecycle

The VM, disk, Bastion Standard, NAT gateway, public IPs, artifact storage and traffic are billable.
**Stopping/deallocating the VM does not stop Bastion/NAT/disk billing.**
Review current regional prices and subscription discounts. Remove the dedicated
demo resource group when the environment is no longer needed, after preserving
anything you want to keep. No automatic teardown or shutdown is configured.
