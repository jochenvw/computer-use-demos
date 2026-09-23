@description('Deployment region.')
param location string = resourceGroup().location

@description('Short lowercase prefix used in resource names.')
@minLength(3)
@maxLength(12)
param prefix string

@description('Optional generalized Windows image ID. Empty uses the SQL Server Developer marketplace image below.')
param desktopImageResourceId string = ''

@description('SQL Server Developer is licensed for development and testing only.')
param imagePublisher string = 'MicrosoftSQLServer'
param imageOffer string = 'sql2022-ws2022'
param imageSku string = 'sqldev-gen2'
param imageVersion string = '16.0.260610'

@description('Windows administrator user used only through Azure Bastion.')
param adminUsername string

@secure()
@description('Windows administrator password supplied securely at deployment time.')
param adminPassword string

@description('Optional private API client CIDR. Leave empty for loopback API plus outbound authenticated devtunnel only.')
param apiClientAddressPrefix string = ''

@description('VM size for the interactive desktop worker.')
param vmSize string = 'Standard_D4as_v5'

@description('Daily auto-shutdown (deallocate) time, HHmm, in shutdownTimeZone. Empty disables it.')
param shutdownTime string = '2300'

@description('Windows time zone ID for the auto-shutdown schedule.')
param shutdownTimeZone string = 'W. Europe Standard Time'

var vnetName = '${prefix}-vnet'
var workloadSubnetName = 'desktop'
var bastionSubnetName = 'AzureBastionSubnet'

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${prefix}-desktop-nsg'
  location: location
  properties: {
    securityRules: concat(empty(apiClientAddressPrefix) ? [] : [
      {
        name: 'AllowApiFromPrivateClients'
        properties: {
          priority: 100
          access: 'Allow'
          direction: 'Inbound'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '8000'
          sourceAddressPrefix: apiClientAddressPrefix
          destinationAddressPrefix: '*'
        }
      }
    ], [
      {
        name: 'AllowRdpFromBastionSubnet'
        properties: {
          priority: 110
          access: 'Allow'
          direction: 'Inbound'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '3389'
          sourceAddressPrefix: '10.80.2.0/26'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'DenyOtherInbound'
        properties: {
          priority: 4000
          access: 'Deny'
          direction: 'Inbound'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ])
  }
}

resource outboundPublicIp 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: '${prefix}-outbound-pip'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource nat 'Microsoft.Network/natGateways@2023-11-01' = {
  name: '${prefix}-nat'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    idleTimeoutInMinutes: 10
    publicIpAddresses: [
      { id: outboundPublicIp.id }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.80.0.0/16'
      ]
    }
    subnets: [
      {
        name: workloadSubnetName
        properties: {
          addressPrefix: '10.80.1.0/24'
          networkSecurityGroup: {
            id: nsg.id
          }
          defaultOutboundAccess: false
          natGateway: {
            id: nat.id
          }
        }
      }
      {
        name: bastionSubnetName
        properties: {
          addressPrefix: '10.80.2.0/26'
        }
      }
    ]
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2023-11-01' = {
  name: '${prefix}-desktop-nic'
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, workloadSubnetName)
          }
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2023-09-01' = {
  name: '${prefix}-desktop-vm'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: '${prefix}-vm'
      adminUsername: adminUsername
      adminPassword: adminPassword
      windowsConfiguration: {
        provisionVMAgent: true
        enableAutomaticUpdates: true
        patchSettings: {
          patchMode: 'AutomaticByOS'
          assessmentMode: 'ImageDefault'
        }
      }
    }
    storageProfile: {
      imageReference: empty(desktopImageResourceId) ? {
        publisher: imagePublisher
        offer: imageOffer
        sku: imageSku
        version: imageVersion
      } : {
        id: desktopImageResourceId
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'Premium_LRS'
        }
        diskSizeGB: 128
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
        }
      ]
    }
    diagnosticsProfile: {
      bootDiagnostics: {
        enabled: true
      }
    }
    securityProfile: {
      securityType: 'TrustedLaunch'
      uefiSettings: {
        secureBootEnabled: true
        vTpmEnabled: true
      }
    }
  }
}

resource autoShutdown 'Microsoft.DevTestLab/schedules@2018-09-15' = if (!empty(shutdownTime)) {
  name: 'shutdown-computevm-${vm.name}'
  location: location
  properties: {
    status: 'Enabled'
    taskType: 'ComputeVmShutdownTask'
    dailyRecurrence: { time: shutdownTime }
    timeZoneId: shutdownTimeZone
    targetResourceId: vm.id
    notificationSettings: { status: 'Disabled' }
  }
}

resource bastionPublicIp 'Microsoft.Network/publicIPAddresses@2023-11-01' = {
  name: '${prefix}-bastion-pip'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource bastion 'Microsoft.Network/bastionHosts@2023-11-01' = {
  name: '${prefix}-bastion'
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    enableTunneling: true
    scaleUnits: 2
    ipConfigurations: [
      {
        name: 'bastion-ipconfig'
        properties: {
          subnet: {
            id: resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, bastionSubnetName)
          }
          publicIPAddress: {
            id: bastionPublicIp.id
          }
        }
      }
    ]
  }
}

output vmName string = vm.name
output vmPrivateIp string = nic.properties.ipConfigurations[0].properties.privateIPAddress
output bastionName string = bastion.name
output vmResourceId string = vm.id
output deploymentLocation string = location
