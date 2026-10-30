# syntax=docker/dockerfile:1.7
# BE-037 Phase A — production container image for the PRISM backend.
#
# One image is built and shared by the API and the four background workers
# (analysis, notification, retention, webhook). Only the command differs.
#
# ARCHITECTURE: built and tested for linux/amd64. The pinned ML stack
# (torch 2.8.0 / ultralytics / transformers) ships cp312 manylinux x86_64 wheels
# that were verified here. aarch64/ARM (e.g. an OCI Always-Free Ampere VM) *does*
# have cp312 wheels for these packages, but that path was NOT exercised in this
# phase — do not assume the image runs on ARM until it is built and smoke-tested
# there. Build explicitly for the intended platform, e.g.
#   docker build --platform linux/amd64 -t prism-backend:prism-7b65a826 .
#
# WHY CPU-ONLY TORCH: the deployment target is a CPU VM (no GPU), and the app
# already runs inference on CPU via VISION_DEVICE=auto (backend/core/config.py),
# which selects whatever device torch reports. PyPI's default torch==2.8.0 wheel
# is the CUDA build and drags ~3.5-4.5 GB of nvidia_* sub-wheels (cublas, cudnn,
# nvrtc, nccl, ...) that expand to ~10 GB+ of image layers and dominate build
# time and disk. We install the SAME pinned version (torch==2.8.0, plus the
# matching torchvision) from PyTorch's CPU wheel index instead. This:
#   * keeps every ML dependency fully present (torch/transformers/ultralytics are
#     NOT removed);
#   * preserves the exact torch==2.8.0 pin from requirements.txt (PEP 440 treats
#     the installed 2.8.0+cpu as satisfying torch==2.8.0, so the requirements
#     pass does not re-pull the CUDA wheel);
#   * is a genuine CPU inference path, not a trimmed-down stub.
# To deploy on a GPU target instead, drop the --index-url line (requirements.txt
# alone then pulls the CUDA build) — an owner/environment decision.

FROM python:3.12-slim-bookworm AS runtime

# Unbuffered logs so workers stream to the container log driver; no pip
# warnings. The wheel cache lives only in the BuildKit cache mount below, never
# in an image layer, so PIP_NO_CACHE_DIR is deliberately left off.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# Runtime system libraries only — no compilers or build tools are installed.
# Every dependency resolves to a cp312 prebuilt wheel (no source builds).
# libgomp1 backs torch's OpenMP use; libpq5 supports psycopg2; ca-certificates
# is needed because transformers/ultralytics fetch model weights over TLS.
# libgl1 + libglib2.0-0 are required by the OpenCV native module that
# ultralytics depends on: opencv-python (the non-headless wheel pinned
# transitively by ultralytics==8.4.155) links against libGL.so.1 and
# libglib/libgthread, and without them `import cv2`/`import ultralytics` raise
# ImportError inside the container (BE-037A-D1), which would fail every vision
# job at model load. These are runtime libs only — no build tooling.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        libpq5 \
        libgl1 \
        libglib2.0-0 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) CPU torch + the matching torchvision (0.23.0 pairs with torch 2.8.0; pinned
#    so the resolver cannot pull a newer torchvision that would drag a different
#    torch). Sole index for this step so no CUDA nvidia_* wheels can be pulled.
#    Cached across rebuilds via the BuildKit mount; pins keep it reproducible.
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url https://download.pytorch.org/whl/cpu \
        "torch==2.8.0" "torchvision==0.23.0"

# 2) The full pinned manifest. torch/torchvision are already satisfied by step 1,
#    so this adds the rest without re-downloading the CUDA build.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

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
