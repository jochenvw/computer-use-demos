# Azure desktop worker infrastructure

`main.bicep` creates:

- one Windows VM from an organization-approved custom desktop image;
- no VM public IP;
- one virtual network with desktop and `AzureBastionSubnet` subnets;
- Azure Bastion for administrative Remote Desktop Protocol access;
- an NSG that permits API traffic only from a supplied private address prefix;
- a system-assigned managed identity and managed boot diagnostics.

The template does not install Epic, create a browser login, persist credentials,
or expose the API publicly. Those are organization-specific operational steps.

```powershell
az deployment group create `
  --resource-group <resource-group> `
  --template-file .\main.bicep `
  --parameters `
      prefix=<prefix> `
      desktopImageResourceId=<image-resource-id> `
      adminUsername=<admin-user> `
      adminPassword=<secure-value> `
      apiClientAddressPrefix=<private-client-cidr>
```

Use Azure Key Vault or deployment-system secret injection for the secure
parameter. Do not put the password in a parameter file committed to Git.

## Image contents

The generalized image should contain:

- a supported Windows desktop;
- the organization-approved browser and endpoint protection;
- Python 3.11+ and `uv`;
- the API source or a deployment bootstrap;
- folders intended for allowlisted ECG and document discovery.

Do not capture a logged-in Epic session, browser cookies, patient data, API
tokens, or cached screenshots into the image. Establish the user session after
deployment through the organization's normal identity controls.
