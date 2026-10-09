terraform {
  required_version = "~> 1.16.0"

  # Exact versions; checksums are recorded in .terraform.lock.hcl (committed).
  required_providers {
    kind = {
      source  = "tehcyx/kind"
      version = "0.11.0" # embeds kind v0.31.0, so the node image must be one kind v0.31 supports
    }
    helm = {
      source  = "hashicorp/helm"
      version = "3.3.0"
    }
  }
}
