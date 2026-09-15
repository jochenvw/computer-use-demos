$subscriptionId = "<subscription-id>"
$resourceGroup = "<resource-group>"
$bastionName = "<bastion-name>"
$vmName = "<virtual-machine-name>"

az network bastion tunnel `
  --name $bastionName `
  --resource-group $resourceGroup `
  --target-resource-id "/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Compute/virtualMachines/$vmName" `
  --resource-port 3389 `
  --port 50000