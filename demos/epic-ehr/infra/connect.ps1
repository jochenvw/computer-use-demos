[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [string]$ResourceGroup = 'rg-epic-demo-swc',
    [string]$Prefix = 'epicdemo',
    [ValidateRange(1024, 65535)][int]$LocalPort = 53389
)

$ErrorActionPreference = 'Stop'
$vmId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Compute/virtualMachines/$Prefix-desktop-vm"
Write-Host "Keep this terminal open. In another terminal run: mstsc /v:localhost:$LocalPort"
Write-Host 'Use the VM local account, not the Azure account. Ctrl+C closes this tunnel.'
& az network bastion tunnel --subscription $SubscriptionId --resource-group $ResourceGroup `
    --name "$Prefix-bastion" --target-resource-id $vmId --resource-port 3389 --port $LocalPort
if ($LASTEXITCODE -ne 0) { throw 'Bastion tunnel failed.' }
