variable mist_org_id {
  description = "Your Juniper Mist Organization ID"
  type        = string
}
variable "root_password" {
  type      = string
  sensitive = true
}