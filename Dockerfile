# One image for training (python -m fraud.train) and, from part 7, serving.
FROM python:3.11-slim@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce

# GHCR links the package to this repository through the source label.
LABEL org.opencontainers.image.source="https://github.com/eduardooliveiraps/fraud-mlops" \
      org.opencontainers.image.licenses="MIT"

# LightGBM needs the OpenMP runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp \
    MLFLOW_DISABLE_AGENT_HINT=1 \
    GIT_PYTHON_REFRESH=quiet

WORKDIR /app
# Dependencies first: this layer is reused until requirements.lock changes.
COPY requirements.lock .
RUN pip install -r requirements.lock
COPY src/ src/

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001

# configs/ is mounted from a ConfigMap; there is no config (and never data) in the image.
CMD ["python", "-m", "fraud.train", "--config", "configs/config.yaml"]
