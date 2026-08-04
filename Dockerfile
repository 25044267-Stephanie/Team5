# Hotel management app image.
#
# WHY:
# - Multi-stage: pip install happens in a builder; the runtime stage only
#   gets the virtualenv + application code (smaller, fewer leftover tools).
# - Digest-pinned base: `python:3.11-slim` floats; pinning by sha256 stops
#   silent base-image changes between CI and the demo host.
# - Non-root USER: if the process is compromised, it does not own the
#   container filesystem as root.
# - HEALTHCHECK: Compose / deploy smoke tests probe /healthz (app + DB).
# - Strip packaging/build tools after install so Trivy does not fail CI on
#   HIGH CVEs in setuptools/wheel metadata the running app never needs
#   (Plan A — remove/fix rather than ignore).

# Multi-arch index digest for python:3.11-slim (Docker Hub).
# Re-verified 2026-08-03: still matches current python:3.11-slim tip (Debian 13/trixie).
# Evaluated python:3.11-slim-bookworm@sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba
# (Debian 12.15) — more unfixed HIGH/CRITICAL in full audit; kept slim/trixie.
ARG PYTHON_IMAGE=python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

FROM ${PYTHON_IMAGE} AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pip setuptools wheel jaraco.context msgpack \
    || true


FROM ${PYTHON_IMAGE} AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Remove base-image packaging tools Trivy otherwise flags (not used at runtime).
RUN pip uninstall -y pip setuptools wheel jaraco.context msgpack \
    || true \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

# Copy only what the running app needs — not tests, ansible stubs, or .env.
# data.json is the verified legacy room inventory for idempotent migrate on
# empty databases (local Docker / EC2). It is never written at runtime.
COPY --chown=app:app app.py config.py models.py repository.py ./
COPY --chown=app:app data.json ./
COPY --chown=app:app templates ./templates
COPY --chown=app:app static ./static
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app database ./database

# WORKDIR was created as root; Gunicorn needs to write /.gunicorn under /app.
RUN chown app:app /app

USER app

EXPOSE 5050

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5050/healthz', timeout=4)"

CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--workers", "2", "--timeout", "60", "app:app"]
