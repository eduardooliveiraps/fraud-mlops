# fraud-mlops: rules for Claude Code

Portfolio project: fraud scoring service with a train → gate → deploy → monitor loop on a local kind cluster.

## Hard constraints
- Zero cost: everything runs locally with free/open-source tools. No paid cloud resources.
- Keep it simple. Do NOT add tools, libraries, or features beyond the current task.
- One task at a time. Do only what is asked, then stop and summarize.
- Python 3.11, code in `src/fraud/`, tests in `tests/`, config in `configs/`.
- BAF is CC BY-NC-SA 4.0. Never commit data (`data/`), derived data, model files, `mlflow.db` or `mlruns/`. make_synthetic must not use real data values.
- Explain the "why" briefly; the owner is learning Kubernetes/MLOps.

## Commands
- `make install`, `make lint`, `make test`
