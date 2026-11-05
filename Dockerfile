# syntax=docker/dockerfile:1.7
# Multi-stage build: dependencies are resolved from uv.lock in a builder stage,
# the runtime stage holds only the virtual environment and the source, runs as
# an unprivileged user and has no package manager or compiler.

FROM python:3.13-slim-trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, so source changes do not invalidate this layer.
COPY pyproject.toml uv.lock .python-version ./
COPY client/pyproject.toml client/README.md ./client/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-install-workspace

COPY opencde ./opencde
COPY client/opencde_client ./client/opencde_client
COPY README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


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
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OPENCDE_DATA_DIR=/data
USER opencde
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["opencde"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
