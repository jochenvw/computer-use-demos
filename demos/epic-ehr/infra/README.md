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
Small source archives are delivered through the authenticated Azure VM agent
channel as 4 KiB parts (non-persistent `az vm run-command invoke`, so the
25-managed-run-command cap is never hit), then reassembled and hash-verified on
the VM. The parts contain tracked source only, never secrets.
This needs no storage public endpoint, SAS, account key, or extra data-plane role,
and stays below Windows command-line limits. The demo publisher caps archives
at 4 MiB; use an approved private artifact pipeline for larger applications.

## Deploy and prepare

Run these commands from the repository root on Windows after `az login`.
Check current SKU/image availability, quota, permissions, and cost in your
subscription before creating resources.

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
source parts travel as encrypted/protected Run Command parameters. Setup
creates only the `EpicDemo` synthetic database/tables if absent; it does not
replace existing data. SQL memory is capped at 8 GiB to leave room for Edge,
SSMS and the agent.

Publishing packages **tracked files from the selected Git commit**, verifies
the archive hash on the VM, installs dependencies and the SDK-matched runtime,
and exercises a synthetic FHIR BP retrieval. It preserves an existing `.env`.
The API bearer token is generated inside the VM, with file access limited to
SYSTEM and `demoadmin`. Copilot credentials, devtunnel login and Epic cookies
are not deployed or embedded in an image.

For ongoing updates after the initial source installation, use the separate
interactive-user launcher in `..\launcher\`. Versioned `epic-v*` archives are
attested by GitHub, staged under per-version directories, synthetically tested,
and activated only after loopback health succeeds. Shared `.env`, audit data and
browser state remain outside release directories. The launcher drains active
jobs before stopping its owned API process and restores the previous release
when activation fails.

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

The VM desktop is kept demo-clean: **Epic Live Demo** (opens the dedicated
browser and starts the visible live API in Windows Terminal), **Microsoft Edge**, **SQL Server
Management Studio** and the **assets** folder used by the files scenario.
`bootstrap-tools.ps1` installs a pinned, hash-checked portable Windows Terminal
under `C:\DemoTools\terminal`; the `EpicDemoApi` logon task opens the agent there
via `service\agent-terminal.ps1 -KeepAlive`.

Operator-only items live in `C:\EpicDemo`: **Configure Epic Agent** (opens the
private `.env`), **READ ME FIRST.txt** and a sample query. `service\run.ps1`
(`-WithTunnel` optional) and `service\testing.ps1` still start the local-only
agent, the tunnel agent, or a VM-side tester.

Inside the RDP session, first run `devtunnel user login` manually. Start
`service\run.ps1 -WithTunnel` and copy its actual HTTPS URL. It cannot provide a
working remote URL before tunnel authentication and startup succeed.

For the full no-copy/paste startup from the repository root:

```powershell
.\demos\epic-ehr\start-demo.ps1 -SubscriptionId $subscription
```

The command starts the VM, refreshes the stable tunnel, opens Bastion RDP, and
starts the local tester. It uses the locally signed-in Dev Tunnel CLI to issue
fresh scoped host and connect tokens, stores them using user-bound DPAPI, and
sends only the host token through protected Azure Run Command parameters. The
tunnel host runs as a SYSTEM startup task and waits up to 30 minutes for the
loopback API. It does not start or hide the agent. The agent remains a visible
interactive process launched through **Epic Live Demo**.

On your **local** machine:

```powershell
.\demos\epic-ehr\service\testing.ps1
# Open the printed local address, normally http://127.0.0.1:8765
```

When the protected local state is present, the tester opens automatically with
the stable tunnel URL and uses the encrypted API and connect tokens server-side.
The masked fields remain blank and no copy/paste is required. Pass
`-ManualCredentials` only when intentionally testing another tunnel. The tester
does not persist credentials and does not require wildcard CORS or an anonymous
tunnel.

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

## Azure Foundry with the VM identity

The VM already has a system-assigned managed identity. Grant that identity
**Cognitive Services OpenAI User** on the existing Azure AI account only; no
API key, subscription-wide role, or new model deployment is needed:

```powershell
$vmPrincipal = az vm show --subscription $subscription -g rg-epic-demo-swc `
  -n epicdemo-desktop-vm --query identity.principalId -o tsv
$accountId = '<existing-Azure-AI-account-resource-ID>'
az role definition list --name 'Cognitive Services OpenAI User' `
  --query '[].{name:roleName,id:id}' -o table
az role assignment create --assignee-object-id $vmPrincipal `
  --assignee-principal-type ServicePrincipal `
  --role 'Cognitive Services OpenAI User' --scope $accountId

.\demos\epic-ehr\infra\run-vm-script.ps1 -SubscriptionId $subscription `
  -ScriptPath .\demos\epic-ehr\infra\configure-foundry.ps1 `
  -CommandName configure-foundry `
  -ProtectedParameters @{
    Endpoint = 'https://<account-name>.openai.azure.com'
    Deployment = '<actual-deployment-name>'
  }
```

Allow time for a new role assignment to propagate before retrying a denied
request. The configuration script uses the VM managed identity and installed,
SDK-matched Copilot runtime to perform an actual synthetic tool call and model
reply. It persists the endpoint and deployment in the private `.env` only after
that round trip succeeds. It never prints an access token or changes the API
bearer, backend, browser opt-in, or running API/tunnel processes.

This verifies **model access, not Epic retrieval**. To prepare the browser, run
the following inside the interactive VM desktop and log in manually to the
authorized demo environment with a read-only account:

```powershell
Set-Location C:\EpicDemo\service
.\browser.ps1 -EpicUrl (Read-Host 'Paste the HTTPS demo URL')
```

Use that dedicated browser, not an ordinary Edge window; its session is exposed
only on loopback CDP port 9222. Never tunnel CDP. Configure `EPIC_ORIGIN` as the
exact approved chart origin (scheme and host, plus port if needed; no path),
`EPIC_COMPUTER_USE_ENABLED=1`, and `EPIC_BACKEND=copilot` only when the login is
ready. Also set `EPIC_READY_URL_PREFIX` to the authenticated chart URL prefix;
redirects to a login page then appear as a readiness failure. Restart the agent
from a fresh PowerShell process to load the updated
`.env`, then bypass the cache for an actual browser retrieval.
Azure Global Standard deployments may process requests outside the account's
region; use synthetic data for this demo.

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

The VM, disk, Bastion Standard, NAT gateway, public IPs and traffic are billable.
**Stopping/deallocating the VM does not stop Bastion/NAT/disk billing.**
Review current regional prices and subscription discounts. Remove the dedicated
demo resource group when the environment is no longer needed, after preserving
anything you want to keep. The VM auto-shuts down (deallocates) daily at
23:00 W. Europe time (`shutdownTime` / `shutdownTimeZone` in `main.bicep`;
empty `shutdownTime` disables it). `start-demo.ps1` starts it again. No
automatic teardown is configured.
