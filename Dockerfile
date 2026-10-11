# BE-037 Phase A — production container image for the PoA backend.
#
# One image is built and shared by the API and the four background workers
# (analysis, notification, retention, webhook). Only the command differs.
#
# ARCHITECTURE: built and tested for linux/amd64. The pinned ML stack
# (torch 2.8.0 / ultralytics / transformers) ships manylinux x86_64 wheels that
# were verified here. aarch64/ARM (e.g. an OCI Always-Free Ampere VM) *does*
# have cp312 wheels for these packages, but that path was NOT exercised in this
# phase — do not assume the image runs on ARM until it is built and smoke-tested
# there. Build explicitly for the intended platform, e.g.
#   docker build --platform linux/amd64 -t poa-backend:be037a .
#
# CPU EXECUTION PATH: PyPI's default torch wheel bundles CUDA libraries but runs
# on CPU when no GPU is present; the app selects CPU automatically via
# VISION_DEVICE=auto (backend/core/config.py). The ML dependencies are kept in
# full — they are load-bearing for the analysis worker and were not trimmed to
# shrink the image.

FROM python:3.12-slim-bookworm AS runtime

# Reproducible, cache-free installs; unbuffered logs so the workers stream to
# the container log driver; no pip warnings about running as the build user.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# Runtime system libraries only — no compilers or build tools are installed.
# Every pinned dependency resolves to a cp312 manylinux wheel, so there is no
# need for build-essential in this image. libgomp1 backs torch's OpenMP use;
# libpq5 supports psycopg2; ca-certificates is needed because transformers/
# ultralytics fetch model weights over TLS on first use.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        libpq5 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first so the (large, slow) ML layer is cached and only
# rebuilds when the manifest changes, not on every source edit.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source. .dockerignore keeps .env, virtualenvs, local
# databases, evidence, model weights, Git metadata, caches and scratch out of
# the build context so no secret or stateful artifact is baked into the image.
COPY . .

# Run as an unprivileged, non-owning user. /app is owned by root and read-only
# to appuser by design: the API and workers never write to the code tree; any
# writable scratch space must be mounted explicitly.
RUN groupadd --system --gid 10001 appgroup \
    && useradd --system --uid 10001 --gid appgroup --no-create-home appuser \
    && chown -R root:root /app
USER appuser

EXPOSE 8000

# Production ASGI startup (not the dev run.py reload server). The API/worker
# Compose services override this command; workers import-check separately.
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
