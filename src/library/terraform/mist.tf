# Resource to create a new Mist Site
resource "mist_site" "tf_managed_lab_site" {
  org_id       = var.mist_org_id
  name         = "Terraform Managed Lab Site"
  address      = "123 Main Rd, Any City, VA 23456, USA" # Required field: provide a valid address
  country_code = "US" # Example, choose appropriate for your lab
  # You can add other site-specific settings here, e.g., timezone, latlng
}

# Output the ID of the created site
output "mist_site_id" {
  value       = mist_site.tf_managed_lab_site.id
  description = "The ID of the Mist site created by Terraform"
}

resource "mist_org_networktemplate" "offices" {
    additional_config_cmds = [null]
    dhcp_snooping          = {
        enabled  = false
        networks = [null]
    }
    dns_servers            = [
        "8.8.8.8",
        "1.1.1.1",
    ]
    dns_suffix             = []
    mist_nac               = {
        enabled = false
    }
    name                   = "Offices"
    networks               = jsondecode(file("${path.module}/mist_networks.json"))
    ntp_servers            = [
        "time.google.com",
        "time.cloudflare.com",
    ]
    org_id                 = var.mist_org_id 
    port_mirroring         = {}
    port_usages            = jsondecode(file("${path.module}/mist_port_usages.json"))
    radius_config          = {
        acct_interim_interval = 0
        auth_server_selection = "ordered"
        auth_servers_retries  = 3
        auth_servers_timeout  = 5
        coa_enabled           = false
        coa_port              = ""
        fast_dot1x_timers     = false
    }
    remote_syslog          = {
        enabled = false
    }
    snmp_config            = {
        enabled = false
    }
    switch_matching        = {
        enable = true
        rules  = [
            {
                additional_config_cmds = [
                    null,
                ]
                match_model            = "EX4400-48MP"
                match_name_offset      = 0
                default_port_usage     = "default"
                name                   = "corporate_offices"
            },
            {
                additional_config_cmds = [
                    null,
                ]
                match_model            = "EX2300-24"
                match_name_offset      = 0
                default_port_usage     = "default"
                name                   = "sales_office"
                port_config            = {
                    "mge-0/0/0-2" = {
                        description        = null
                        no_local_overwrite = true
                        usage              = "uplink"
                    },
                    "mge-0/0/3-7, ge-0/0/8-24" = {
                        description        = null
                        dynamic_usage      = "dynamic"
                        no_local_overwrite = true
                        usage              = "access"
                    },
                }
            },
        ]
    }
    switch_mgmt            = {
        config_revert_timer = 10
        dhcp_option_fqdn    = false
        local_accounts      = {}
        protect_re          = {
            allowed_services = []
            custom           = []
            enabled          = false
            trusted_hosts    = []
            hit_count        = false
        }
        root_password       = var.root_password
        tacacs              = {
            enabled = false
        }
    }
    vrf_config             = {
        enabled = false
    }
}