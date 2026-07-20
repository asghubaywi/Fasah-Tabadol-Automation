# syntax=docker/dockerfile:1
#
# Multi-stage build for Fasah-Tabadol-Automation.
# Targets match docker-compose.yml: `orchestrator` and `browser-worker`.
#
#   docker compose build          # builds both targets
#   docker build --target orchestrator   -t fasah-orchestrator .
#   docker build --target browser-worker -t fasah-browser-worker .

# ── Stage 1: build the Rust engine (fasah-engine) ─────────────────────────────
FROM rust:1-slim AS rust-build
WORKDIR /app
# Copy the workspace manifest + lockfile first for better layer caching.
COPY Cargo.toml Cargo.lock ./
COPY src/agents ./src/agents
RUN cargo build --release
# Binary is produced at /app/target/release/fasah-engine

# ── Stage 2: common Python base ───────────────────────────────────────────────
FROM python:3.11-slim AS python-base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: orchestrator ─────────────────────────────────────────────────────
# Polls the inbox, runs parse → compliance → dispatch. Needs the Rust engine.
FROM python-base AS orchestrator
COPY src ./src
COPY config ./config
COPY --from=rust-build /app/target/release/fasah-engine /app/target/release/fasah-engine
ENV FASAH_ENGINE_BIN=/app/target/release/fasah-engine \
    AGENT_CONFIG=/app/config/agent_fasah.yaml \
    FASAH_RULES=/app/config/fasah_rules.yaml
CMD ["python", "src/pipeline/orchestrator.py"]

# ── Stage 4: browser worker (Playwright + Chromium) ───────────────────────────
# Drives the Fasah portal (read-only). Chromium + OS deps are installed here.
FROM python-base AS browser-worker
RUN playwright install --with-deps chromium
COPY src ./src
COPY config ./config
CMD ["python", "src/browser/worker.py"]
