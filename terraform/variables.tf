variable "cluster_name" {
  description = "kind cluster name; kubectl context is kind-<name>."
  type        = string
  default     = "fraud"
}

variable "monitoring" {
  description = "Install Prometheus and Grafana (CI turns this off to save time and RAM)."
  type        = bool
  default     = true
}
