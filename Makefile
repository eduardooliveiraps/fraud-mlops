PY := python3.11

# Pinned CLI tools (sha256 from the official release pages), installed to ~/.local/bin.
BIN := $(HOME)/.local/bin
KIND_VERSION := v0.33.0
KIND_SHA256 := aee6151561422756b764a4ae28e7f44cda5af5a9eead3cc9985112b1de8d8e0d
KUBECTL_VERSION := v1.37.1
KUBECTL_SHA256 := 65691ff77eb6fa44c908b77a1082c9f092c3b9733b5cefabec0d1104890e21a8

# Local cluster. --context makes every kubectl call target this cluster, never another one.
CLUSTER := fraud
KIND := $(BIN)/kind
KUBECTL := $(BIN)/kubectl --context kind-$(CLUSTER)
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
lock:
	rm -rf .venv-lock && $(PY) -m venv .venv-lock && .venv-lock/bin/pip install -q -U pip
	.venv-lock/bin/pip install -q -e ".[dev]"
	.venv-lock/bin/pip freeze --exclude-editable > requirements-dev.lock && rm -rf .venv-lock
	$(PY) -m venv .venv-lock && .venv-lock/bin/pip install -q -U pip
	.venv-lock/bin/pip install -q -e . -c requirements-dev.lock
	.venv-lock/bin/pip freeze --exclude-editable > requirements.lock && rm -rf .venv-lock
lint:
	.venv/bin/ruff check src tests notebooks
test:
	.venv/bin/pytest -q
# Train on the real data, register a version in the cluster's MLflow, run the gate.
# MLFLOW_DISABLE_AGENT_HINT silences an MLflow startup message.
train:
	MLFLOW_TRACKING_URI=$(MLFLOW_URL) MLFLOW_DISABLE_AGENT_HINT=1 \
		.venv/bin/python -m fraud.train --config configs/config.yaml
data:
	.venv/bin/python -m fraud.data --config configs/config.yaml

# $(call install-bin,name,url,sha256): download, verify checksum, then install.
define install-bin
	curl -fsSL --retry 3 -o $(BIN)/.$(1).download $(2)
	echo "$(3)  $(BIN)/.$(1).download" | sha256sum --check --quiet \
		|| { rm -f $(BIN)/.$(1).download; exit 1; }
	chmod 0755 $(BIN)/.$(1).download && mv $(BIN)/.$(1).download $(BIN)/$(1)
endef

tools:
	mkdir -p $(BIN)
	$(call install-bin,kind,https://kind.sigs.k8s.io/dl/$(KIND_VERSION)/kind-linux-amd64,$(KIND_SHA256))
	$(call install-bin,kubectl,https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/linux/amd64/kubectl,$(KUBECTL_SHA256))
	$(KIND) version && $(BIN)/kubectl version --client

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

mlflow-check:
	curl -fsS $(MLFLOW_URL)/health && echo
	curl -fsS -X POST -H "Content-Type: application/json" -d '{"max_results": 5}' \
		$(MLFLOW_URL)/api/2.0/mlflow/experiments/search && echo

.PHONY: install lock lint test data train tools cluster-up cluster-down mlflow-up mlflow-check \
	image train-deploy train-job
