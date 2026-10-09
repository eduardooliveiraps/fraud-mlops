PY := python3.11

# Pinned CLI tools (sha256 from the official release pages), installed to ~/.local/bin.
BIN := $(HOME)/.local/bin
KIND_VERSION := v0.33.0
KIND_SHA256 := aee6151561422756b764a4ae28e7f44cda5af5a9eead3cc9985112b1de8d8e0d
KUBECTL_VERSION := v1.37.1
KUBECTL_SHA256 := 65691ff77eb6fa44c908b77a1082c9f092c3b9733b5cefabec0d1104890e21a8
HELM_VERSION := v4.3.0
HELM_SHA256 := 86584a54def73570558f66f5111cc53dfed56689637ae32c1201205d494f54fb

# Local cluster. --context makes every kubectl call target this cluster, never another one.
CLUSTER := fraud
KIND := $(BIN)/kind
KUBECTL := $(BIN)/kubectl --context kind-$(CLUSTER)
HELM := $(BIN)/helm --kube-context kind-$(CLUSTER)
METRICS_SERVER_CHART := 3.14.0
PROMETHEUS_CHART := 29.33.1
GRAFANA_CHART := 13.2.5
MLFLOW_URL := http://localhost:5000
# Unique tag per build: commit id, plus "-dirty" if there are uncommitted changes. Never "latest".
IMAGE := fraud-mlops
IMAGE_TAG := $(shell git describe --always --dirty)

install:
	$(PY) -m venv .venv && .venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements-dev.lock && .venv/bin/pip install --no-deps -e .
# Re-resolve pyproject.toml ranges in fresh venvs and pin every package exactly:
# requirements-dev.lock (laptop, CI) and requirements.lock (image, runtime only).
# The runtime lock is resolved inside the dev lock, so shared packages have equal versions.
# Cool-down: only releases at least 14 days old are considered (supply-chain safety).
lock: export PIP_UPLOADED_PRIOR_TO := P14D
lock:
	rm -rf .venv-lock && $(PY) -m venv .venv-lock && .venv-lock/bin/pip install -q -U pip
	.venv-lock/bin/pip install -q -e ".[dev]"
	.venv-lock/bin/pip freeze --exclude-editable > requirements-dev.lock && rm -rf .venv-lock
	$(PY) -m venv .venv-lock && .venv-lock/bin/pip install -q -U pip
	.venv-lock/bin/pip install -q -e . -c requirements-dev.lock
	.venv-lock/bin/pip freeze --exclude-editable > requirements.lock && rm -rf .venv-lock
lint:
	.venv/bin/ruff check src tests notebooks loadtest
test:
	.venv/bin/pytest -q
# Train on the real data, register a version in the cluster's MLflow, run the gate.
# MLFLOW_DISABLE_AGENT_HINT silences an MLflow startup message.
train:
	MLFLOW_TRACKING_URI=$(MLFLOW_URL) MLFLOW_DISABLE_AGENT_HINT=1 \
		.venv/bin/python -m fraud.train --config configs/config.yaml
# Scoring API on localhost:8000, serving the champion's pinned version from the cluster's MLflow.
serve:
	export MLFLOW_TRACKING_URI=$(MLFLOW_URL) MLFLOW_DISABLE_AGENT_HINT=1; \
	MODEL_URI=$$(.venv/bin/python -m fraud.registry --config configs/config.yaml) && \
	MODEL_URI=$$MODEL_URI .venv/bin/uvicorn --factory fraud.serve:create_app --port 8000
data:
	.venv/bin/python -m fraud.data --config configs/config.yaml

# $(call install-bin,name,url,sha256): skip if already installed with that checksum,
# else download (time-limited), verify the checksum, then install.
CURL := curl -fsSL --retry 3 --connect-timeout 20 --max-time 600
define install-bin
	echo "$(3)  $(BIN)/$(1)" | sha256sum --check --quiet 2>/dev/null || { \
		$(CURL) -o $(BIN)/.$(1).download $(2) \
		&& echo "$(3)  $(BIN)/.$(1).download" | sha256sum --check --quiet \
		&& chmod 0755 $(BIN)/.$(1).download && mv $(BIN)/.$(1).download $(BIN)/$(1); \
	} || { rm -f $(BIN)/.$(1).download; exit 1; }
endef

tools:
	mkdir -p $(BIN)
	$(call install-bin,kind,https://kind.sigs.k8s.io/dl/$(KIND_VERSION)/kind-linux-amd64,$(KIND_SHA256))
	$(call install-bin,kubectl,https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/linux/amd64/kubectl,$(KUBECTL_SHA256))
	$(BIN)/helm version --short 2>/dev/null | grep -q "^$(HELM_VERSION)+" || { \
		$(CURL) -o $(BIN)/.helm.tgz https://get.helm.sh/helm-$(HELM_VERSION)-linux-amd64.tar.gz \
		&& echo "$(HELM_SHA256)  $(BIN)/.helm.tgz" | sha256sum --check --quiet \
		&& tar -xzf $(BIN)/.helm.tgz -C $(BIN) --strip-components=1 linux-amd64/helm; \
		STATUS=$$?; rm -f $(BIN)/.helm.tgz; exit $$STATUS; \
	}
	$(KIND) version && $(BIN)/kubectl version --client && $(BIN)/helm version --short

# .state/ holds MLflow's database and artifacts on the host, so they outlive the cluster.
cluster-up:
	mkdir -p .state/mlflow
	$(KIND) create cluster --name $(CLUSTER) --config k8s/kind-config.yaml --wait 120s
cluster-down:
	$(KIND) delete cluster --name $(CLUSTER)

mlflow-up:
	$(KUBECTL) apply -f k8s/namespace.yaml -f k8s/mlflow/
	$(KUBECTL) -n fraud rollout status deployment/mlflow --timeout 300s
# Build the image and copy it into the kind node (no registry needed locally).
image:
	docker build -t $(IMAGE):$(IMAGE_TAG) .
	$(KIND) load docker-image $(IMAGE):$(IMAGE_TAG) --name $(CLUSTER)

# Config as a ConfigMap, data volume, and the CronJob pointing at the current image tag.
train-deploy:
	$(KUBECTL) -n fraud create configmap fraud-config --from-file=configs/config.yaml \
		--dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) apply -f k8s/train/storage.yaml
	sed 's/__IMAGE_TAG__/$(IMAGE_TAG)/g' k8s/train/cronjob.yaml | $(KUBECTL) apply -f -

# Run the CronJob's template now, wait until it completes or fails, then print its logs.
train-job:
	@JOB=train-manual-$$(date +%Y%m%d-%H%M%S); \
	$(KUBECTL) -n fraud create job $$JOB --from=cronjob/fraud-train; \
	echo "Waiting for $$JOB ..."; \
	while :; do \
		STATE=$$($(KUBECTL) -n fraud get job $$JOB -o jsonpath='{.status.conditions[*].type}'); \
		case "$$STATE" in *Complete*|*Failed*) break;; esac; sleep 5; \
	done; \
	$(KUBECTL) -n fraud logs -l job-name=$$JOB --prefix --tail=-1; \
	echo "$$JOB: $$STATE"; case "$$STATE" in *Complete*) ;; *) exit 1;; esac

# CPU/memory metrics for `kubectl top` and the HPA (kind does not ship metrics-server).
metrics-server:
	$(HELM) upgrade --install metrics-server metrics-server \
		--repo https://kubernetes-sigs.github.io/metrics-server/ --version $(METRICS_SERVER_CHART) \
		--namespace kube-system --values k8s/metrics-server/values.yaml --wait --timeout 3m

# Prometheus (server only, scrapes annotated pods, holds the alert rule) and Grafana
# (data source + dashboard provisioned from the repo) in namespace "monitoring".
monitoring:
	$(HELM) upgrade --install prometheus prometheus \
		--repo https://prometheus-community.github.io/helm-charts --version $(PROMETHEUS_CHART) \
		--namespace monitoring --create-namespace --values k8s/prometheus/values.yaml \
		--wait --timeout 5m
	$(HELM) upgrade --install grafana grafana \
		--repo https://grafana-community.github.io/helm-charts --version $(GRAFANA_CHART) \
		--namespace monitoring --values k8s/grafana/values.yaml \
		--set-file dashboards.default.fraud-api.json=k8s/grafana/fraud-dashboard.json \
		--wait --timeout 5m
	@echo "Prometheus: http://localhost:9090  Grafana: http://localhost:3000 (anonymous read-only)"
# Grafana admin password (generated by the chart into a Secret, never stored in the repo).
grafana-password:
	@$(KUBECTL) -n monitoring get secret grafana -o jsonpath='{.data.admin-password}' \
		| base64 -d && echo

# Deploy the API with the champion's pinned version, or MODEL_VERSION=<n>. A new model or image
# is a new ReplicaSet revision, so `make rollback` really brings back the previous model.
deploy:
	@export MLFLOW_TRACKING_URI=$(MLFLOW_URL) MLFLOW_DISABLE_AGENT_HINT=1; \
	URI=$$(.venv/bin/python -m fraud.registry --config configs/config.yaml \
		$(if $(MODEL_VERSION),--version $(MODEL_VERSION))) || exit 1; \
	ID=$$(docker image inspect $(IMAGE):$(IMAGE_TAG) --format '{{.Id}}') || exit 1; \
	echo "Deploying $$URI with image $(IMAGE):$(IMAGE_TAG)"; \
	sed -e "s|__IMAGE_TAG__|$(IMAGE_TAG)|g" -e "s|__IMAGE_ID__|$$ID|g" -e "s|__MODEL_URI__|$$URI|g" \
		k8s/api/deployment.yaml | $(KUBECTL) apply -f -
	$(KUBECTL) apply -f k8s/api/service.yaml -f k8s/api/hpa.yaml
	$(KUBECTL) -n fraud rollout status deployment/fraud-api --timeout 180s
rollback:
	$(KUBECTL) -n fraud rollout undo deployment/fraud-api
	$(KUBECTL) -n fraud rollout status deployment/fraud-api --timeout 180s

# Live checks against the API on localhost:8000 (also the last step of the CI smoke test).
smoke:
	SMOKE_URL=http://localhost:8000 .venv/bin/pytest -q tests/test_live_api.py

# Tag and push the image, e.g. make push REGISTRY=ghcr.io/<owner> (CI does this on main).
push:
	@test -n "$(REGISTRY)" || { echo "Set REGISTRY, e.g. REGISTRY=ghcr.io/<owner>"; exit 1; }
	docker tag $(IMAGE):$(IMAGE_TAG) $(REGISTRY)/$(IMAGE):$(IMAGE_TAG)
	docker push $(REGISTRY)/$(IMAGE):$(IMAGE_TAG)

# Headless Locust against localhost:8000: ramp 1 user/s to LOAD_USERS, run LOAD_TIME.
LOAD_USERS := 50
LOAD_TIME := 3m
loadtest:
	mkdir -p .state/loadtest
	.venv/bin/locust -f loadtest/locustfile.py --headless --host http://localhost:8000 \
		-u $(LOAD_USERS) -r 1 -t $(LOAD_TIME) --csv .state/loadtest/run --only-summary

# Drift demo: real held-out traffic (PSI stays low), then shifted traffic (synthetic data,
# PSI > 0.2; FraudScoreDrift fires after 5 min). Real mode needs data/processed (laptop only).
drift-demo:
	@echo "== 1/2 real held-out traffic, 4 min: PSI should stay below 0.1"
	LOAD_DATA=real $(MAKE) --no-print-directory loadtest LOAD_TIME=4m
	@echo "== 2/2 shifted traffic, 8 min: PSI above 0.2, alert Pending -> Firing after 5 min"
	LOAD_DATA=synthetic $(MAKE) --no-print-directory loadtest LOAD_TIME=8m

mlflow-check:
	curl -fsS $(MLFLOW_URL)/health && echo
	curl -fsS -X POST -H "Content-Type: application/json" -d '{"max_results": 5}' \
		$(MLFLOW_URL)/api/2.0/mlflow/experiments/search && echo

.PHONY: install lock lint test data train serve tools cluster-up cluster-down mlflow-up mlflow-check \
	image train-deploy train-job metrics-server deploy rollback loadtest monitoring grafana-password \
	drift-demo smoke push
