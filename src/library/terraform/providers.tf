provider "meraki" {
  # No explicit configuration needed here if using MERAKI_API_KEY environment variable
  # meraki_base_url = "https://api.meraki.com/api/v1" # This is the default, can be omitted
  # export MERAKI_API_KEY=""
  api_key = ""
}

provider "mist" {
  # No explicit configuration needed here
  # export TF_VAR_mist_org_id=""
  # export MIST_API_TOKEN=""
  apitoken = ""
  host     = "api.mist.com"
}