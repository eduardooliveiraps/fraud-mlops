# fraud-mlops

Portfolio project for an ML Platform Engineer role (payments/fintech). A LightGBM fraud model on
the BAF Base dataset, run as a reproducible train -> gate -> deploy -> monitor loop on a local
kind cluster. Readers are recruiters and engineers: clarity and defensible decisions beat features.

## Map
- `src/fraud/`: Python package (data, training, gate, serving). `tests/`: pytest, synthetic data only.
- `configs/`: YAML config. All paths, months, thresholds, costs and URLs live here.
- `notebooks/`: exploration as `# %%` scripts, never `.ipynb`.
- `k8s/` manifests, `terraform/` local cluster + Helm releases, `.github/workflows/` CI
  (folders are created when a part needs them).
- `docs/ROADMAP.md`: part status, contracts between parts, design-decisions log.
  Read it at the start of every session. Update it when a part's status or contract changes.

## Commands
- `make install`, `make lint`, `make test`. Other targets: see `Makefile`.
- Python 3.11 in `.venv`. WSL2, CPU only, ~10 GB RAM for WSL: keep the cluster small.

## Hard rules
- Zero cost: local, free, open-source tools only. Never apply Terraform to a real cloud.
- Keep it simple: no tool, library, option or abstraction the current part does not need.
  If something seems missing or worth cutting, propose it with a recommendation; the owner decides.
- Data license (BAF, CC BY-NC-SA 4.0): never commit `data/`, derived data, model files,
  `mlflow.db`, `mlruns/` or `mlartifacts/`. Never put data in a container image.
- Never print, log or save row-level data. Aggregates only.
- `make_synthetic()` must not use real data values. Tests and CI use only synthetic data.
- The owner runs `git push`. Commit locally only after the owner approves a part.

## Working method: one part at a time (parts are in ROADMAP)
1. Design: goal, contract, acceptance criteria. Flag non-obvious choices with a
   recommendation and wait for OK before coding them.
2. Implement the smallest complete version.
3. Test: unit tests on synthetic data, plus one run of the real path locally.
4. Check the definition of done.
5. Integration: neighbour contracts still hold, everything still passes, README and ROADMAP updated.
6. Report and stop: what changed and why, how to verify, 2-3 concepts for interviews.
   Never start the next part without approval.

## Definition of done
- `make lint` and `make test` pass. New logic has tests, including edge cases and failure paths.
- Config-driven (no hardcoded paths, thresholds, costs, URLs). Fail fast with clear errors.
- Reproducible: fixed seeds, pinned dependencies, one `make` command per workflow.
- Typed signatures, `logging` (not `print`) in library code, no dead code.
- Containers/Kubernetes: pinned image and chart versions, non-root user, probes,
  resource requests/limits, no secrets in the repo.

## Teaching mode
The owner is new to Kubernetes, Terraform, Prometheus/Grafana and MLflow deployment.
- First time a concept appears: what it is, why we use it, a one-line analogy.
- Design decisions: 2-3 sentences, also logged in ROADMAP.
- Short answers, plain language, no undefined jargon.
