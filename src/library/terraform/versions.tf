terraform {
  required_providers {
    mist = {
      source  = "Juniper/mist"
      version = "0.7.2"
    }
    meraki = {
      source  = "CiscoDevNet/meraki"
      version = "1.11.0"
    }
    netbox = {
      source  = "e-breuninger/netbox"
      version = "5.3.0"
    }
  }
}