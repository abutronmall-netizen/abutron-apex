# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APEX_DATA_DIR=/var/data \
    APEX_ROLES=web

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir supervisor

COPY apex/ ./apex/
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY ui/ ./ui/
COPY deploy/ ./deploy/
COPY tests/ ./tests/
COPY Makefile README.md pyproject.toml ./

# mutable state lives on a mounted volume; the image itself stays read-only
RUN mkdir -p /var/data/state /var/data/results /var/data/data_cache /var/data/logs \
 && chmod -R 777 /var/data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/healthz" || exit 1

ENTRYPOINT ["python3", "deploy/entrypoint.py"]
