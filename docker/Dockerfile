# syntax=docker/dockerfile:1.7
# Multi-stage build: dependencies are resolved from uv.lock in a builder stage,
# the runtime stage holds only the virtual environment and the source, runs as
# an unprivileged user and has no package manager or compiler.

FROM python:3.13-slim-trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# git fetches IFC-DB at the commit uv.lock names, until it is on PyPI (ADR 0014). Only this stage has it.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Optional extras to install. The default includes the IFC-DB module (IfcOpenShell),
# which OPENCDE_IFC_DB_ENABLED switches on at runtime; build with
# `--build-arg OPENCDE_EXTRAS=` for a slimmer image without it.
ARG OPENCDE_EXTRAS="--extra ifc-db"

# Dependencies first, so source changes do not invalidate this layer.
COPY pyproject.toml uv.lock .python-version ./
COPY client/pyproject.toml client/README.md ./client/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-install-workspace ${OPENCDE_EXTRAS}

COPY opencde ./opencde
COPY client/opencde_client ./client/opencde_client
COPY README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev ${OPENCDE_EXTRAS}

# buildingSMART's ifc-gherkin-rules, in an environment of their own with IfcOpenShell 0.8.6 (ADR 0012), made from
# pinned downloads checked against their SHA-256. They add about 425 MB, so they are left out unless the image is built
# with `--build-arg OPENCDE_GHERKIN=1`, as the published image tagged `-gherkin` is. Only with the IFC-DB module.
ARG OPENCDE_GHERKIN=0
RUN --mount=type=cache,target=/root/.cache/uv \
    mkdir -p /opt/gherkin \
    && if [ "$OPENCDE_GHERKIN" = "1" ] && /app/.venv/bin/python -c "import ifcopenshell" 2>/dev/null; then \
         /app/.venv/bin/python -m ifc_db.gherkin_install /opt/gherkin \
         && /opt/gherkin/venv/bin/python -m compileall -q /opt/gherkin/run; \
       fi


FROM python:3.13-slim-trixie AS runtime
# Apply the distribution's security updates and remove pip: the runtime needs no
# package manager, and pip's vendored libraries are what image scanners flag
# between rebuilds of the base image.
RUN apt-get update && apt-get -y upgrade --no-install-recommends && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip \
    && groupadd --system --gid 10001 opencde \
    && useradd --system --uid 10001 --gid opencde --home-dir /app --shell /usr/sbin/nologin opencde \
    && mkdir -p /data && chown opencde:opencde /data
WORKDIR /app
COPY --from=builder --chown=opencde:opencde /app /app
# Owned by root, so that the server can run the rules but not change them. Empty when they were left out.
COPY --from=builder /opt/gherkin /opt/gherkin
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OPENCDE_DATA_DIR=/data \
    OPENCDE_IFC_DB_GHERKIN_ENV=/opt/gherkin
USER opencde
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["opencde"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
