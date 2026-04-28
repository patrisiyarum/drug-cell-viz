FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

# System deps for RDKit wheels + Biopython + curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl libxrender1 libxext6 libsm6 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.30 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

# Install base deps + the radiogenomics extra (torch + monai) so the API
# can run real CT-scan inference. Pin torch to the CPU-only wheel index;
# Render web services are CPU-only and the CUDA wheels are ~3x bigger.
ENV UV_INDEX_STRATEGY=unsafe-best-match \
    UV_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

RUN uv sync --no-dev --extra radiogenomics

# Writable blob root for the local-filesystem storage backend.
RUN mkdir -p /data/blobs

EXPOSE 8000

# Respect $PORT if the platform (Render, Fly, Cloud Run) provides one;
# fall back to 8000 for docker-compose and local dev.
CMD ["sh", "-c", "uv run uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
