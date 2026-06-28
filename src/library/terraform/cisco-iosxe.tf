terraform {
  required_providers {
    iosxe = {
      source  = "CiscoDevNet/iosxe"
      version = ">= 0.3.3"
    }
  }
}

provider "iosxe" {
  username = "admin"
  password = "XXXXXXXX"
  url      = "https://your-switch-hostname-or-ip"
}

##########################################
# Should not need to change below here ! #
##########################################
variable source_address {
    type = string
    default = "1.1.1.1"
    description = "Source address" 
}

variable receiver_ip {
    type = string
    default = "1.1.1.1"
    description = "Receiver IP" 
}

variable receiver_port  {
    type = string
    default = "57500"
    description = "Port to send data to" 
}

resource "iosxe_mdt_subscription" "cpu_subs" {
  for_each               = var.cpu_subscriptions
  subscription_id        = each.key
  stream                 = "yang-push"
  encoding               = "encode-kvgpb"
  update_policy_periodic = var.cpu_periodic
  source_address         = var.source_address
  filter_xpath           = each.value.xpath
  receivers = [
    {
      address  = var.receiver_ip
      port     = var.receiver_port
      protocol = "grpc-tcp"
    }
  ]
}

variable cpu_periodic {
    type = string
    default = "100"
    description = "Short update interval" 
}

# CPU.tf
variable "cpu_subscriptions" {
  default = {
    100 = {
      xpath = "/process-cpu-ios-xe-oper:cpu-usage/cpu-utilization/five-seconds"
    },
    101 = {
      xpath = "/process-cpu-ios-xe-oper:cpu-usage/cpu-utilization/one-minute"
    },
    102 = {
      xpath = "/process-cpu-ios-xe-oper:cpu-usage/cpu-utilization/five-minutes"
    }
  }
}

resource "iosxe_mdt_subscription" "example" {
  for_each               = var.subscriptions
  subscription_id        = each.key
  stream                 = "yang-push"
  encoding               = "encode-kvgpb"
  update_policy_periodic = var.example_periodic
  source_address         = var.source_address
  filter_xpath           = each.value.xpath
  receivers = [
    {
      address  = var.receiver_ip
      port     = var.receiver_port
      protocol = "grpc-tcp"
    }
  ]
 }

variable example_periodic {
    type = string
    default = "6000"
    description = "Long update interval" 
}

# XPATH.tf
variable "subscriptions" {
  default = {
    103 = {
      xpath = "/environment-ios-xe-oper:environment-sensors"
    },
    104 = {
      xpath = "/interfaces-ios-xe-oper:interfaces"

    }
  }
}
