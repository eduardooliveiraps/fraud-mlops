output "kubectl_context" {
  description = "Context written to ~/.kube/config."
  value       = "kind-${kind_cluster.this.name}"
}

output "urls" {
  description = "Local endpoints (bound to 127.0.0.1)."
  value       = { for name, p in local.ports : name => "http://localhost:${p.host}" }
}
