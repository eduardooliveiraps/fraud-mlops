# Local platform: a one-node kind cluster plus third-party add-ons from pinned Helm charts.
# Our own components (MLflow, training CronJob, API) are plain manifests applied by `make`.
# State stays local (terraform.tfstate, gitignored): it contains the cluster's credentials.

locals {
  repo = abspath("${path.module}/..")
  # The newest image kind v0.31.0 (inside the provider) supports, pinned by digest.
  node_image = "kindest/node:v1.35.0@sha256:452d707d4862f52530247495d180205e029056831160e22870e37e3f6c1ac31f"

  # localhost port -> Service NodePort. 127.0.0.1 keeps every UI off the local network.
  ports = {
    mlflow     = { host = 5000, node = 30500 }
    api        = { host = 8000, node = 30800 }
    prometheus = { host = 9090, node = 30900 }
    grafana    = { host = 3000, node = 30300 }
  }
}

resource "kind_cluster" "this" {
  name            = var.cluster_name
  node_image      = local.node_image
  wait_for_ready  = true
  kubeconfig_path = pathexpand("~/.kube/config") # adds context kind-<name>, like the kind CLI

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    # One node (control plane also runs our pods) to keep RAM low.
    node {
      role = "control-plane"

      # MLflow database and artifacts on the host, so they outlive the cluster.
      extra_mounts {
        host_path      = "${local.repo}/.state/mlflow"
        container_path = "/mnt/mlflow"
      }
      # Training data, read-only: nothing in the cluster can change it.
      extra_mounts {
        host_path      = "${local.repo}/data/processed"
        container_path = "/mnt/data"
        read_only      = true
      }

      dynamic "extra_port_mappings" {
        for_each = local.ports
        content {
          container_port = extra_port_mappings.value.node
          host_port      = extra_port_mappings.value.host
          listen_address = "127.0.0.1"
        }
      }
    }
  }
}

provider "helm" {
  kubernetes = {
    host                   = kind_cluster.this.endpoint
    client_certificate     = kind_cluster.this.client_certificate
    client_key             = kind_cluster.this.client_key
    cluster_ca_certificate = kind_cluster.this.cluster_ca_certificate
  }
}

# CPU/memory metrics for `kubectl top` and the HPA (kind does not ship metrics-server).
resource "helm_release" "metrics_server" {
  name       = "metrics-server"
  repository = "https://kubernetes-sigs.github.io/metrics-server/"
  chart      = "metrics-server"
  version    = "3.14.0"
  namespace  = "kube-system"
  values     = [file("${local.repo}/k8s/metrics-server/values.yaml")]
  timeout    = 300
}

# Prometheus server only: scrapes annotated pods, holds the FraudScoreDrift rule.
resource "helm_release" "prometheus" {
  count            = var.monitoring ? 1 : 0
  name             = "prometheus"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "prometheus"
  version          = "29.33.1"
  namespace        = "monitoring"
  create_namespace = true
  values           = [file("${local.repo}/k8s/prometheus/values.yaml")]
  timeout          = 300
}

# Grafana: data source and dashboard provisioned from the repo (no state in Grafana).
resource "helm_release" "grafana" {
  count      = var.monitoring ? 1 : 0
  name       = "grafana"
  repository = "https://grafana-community.github.io/helm-charts"
  chart      = "grafana"
  version    = "13.2.5"
  namespace  = "monitoring"
  values = [
    file("${local.repo}/k8s/grafana/values.yaml"),
    yamlencode({
      dashboards = { default = { "fraud-api" = {
        json = file("${local.repo}/k8s/grafana/fraud-dashboard.json")
      } } }
    }),
  ]
  timeout    = 300
  depends_on = [helm_release.prometheus] # the dashboard's data source
}
