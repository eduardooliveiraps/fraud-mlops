# fraud-mlops: rules for Claude Code

Portfolio project: fraud scoring service with a train → gate → deploy → monitor loop on a local kind cluster.

## Hard constraints
- Zero cost: everything runs locally with free/open-source tools. No paid cloud resources.
- Keep it simple. Do NOT add tools, libraries, or features beyond the current task.
- One task at a time. Do only what is asked, then stop and summarize.
- Python 3.11, code in `src/fraud/`, tests in `tests/`, config in `configs/`.
- Never commit data (`data/`), `mlflow.db`, or `mlruns/`. The BAF dataset is non-commercial licensed.
- Explain the "why" briefly; the owner is learning Kubernetes/MLOps.

## Commands
- `make install`, `make lint`, `make test`
