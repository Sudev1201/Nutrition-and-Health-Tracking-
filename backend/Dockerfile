# The API image. From the repository root:
#   docker build -t healthmonitor-api backend
#
# Two stages on the same base image, so the virtualenv built in the first finds
# its interpreter at the same path in the second. The runtime stage holds the
# virtualenv and the code, both owned by root, and runs as an unprivileged user
# that can write only the ETL's download cache.
#
# No BuildKit-only syntax (RUN --mount, COPY --link): CI builds with BuildKit,
# and colima's docker without the buildx plugin falls back to the classic
# builder, which rejects both.

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

# The classic builder keeps this stage as an untagged image, virtualenv and uv
# included. The label lets a cleanup remove it without touching any other
# dangling image:
#   docker image prune -f --filter label=healthmonitor.stage=builder
LABEL healthmonitor.stage=builder

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

# UV_COMPILE_BYTECODE: compile the dependencies here, because the runtime user
# cannot write __pycache__. UV_PYTHON_DOWNLOADS=0: use this image's Python, never
# a downloaded one, so the virtualenv's interpreter exists in the runtime stage.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Only what decides the dependencies, so a code change does not reinstall them.
# --locked fails the build when uv.lock is out of step with pyproject.toml.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . /app

# The one directory the app writes to: etl/common.py's CACHE_DIR, used when the
# ETL is run inside the container.
RUN mkdir -p /app/etl/.cache && chown app:app /app/etl/.cache

# PYTHONPATH: app, scripts and etl import from any working directory, so
# `python -m scripts.<name>` also works in a `fly ssh console` session that does
# not start in WORKDIR.
# FORWARDED_ALLOW_IPS: trust X-Forwarded-Proto from the platform's proxy, the only
# way in, so a redirect FastAPI builds says https. Uvicorn reads it from here.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    FORWARDED_ALLOW_IPS="*"

USER 10001:10001
EXPOSE 8000

# One worker: plan 8's lifespan starts a reminder loop in every worker process,
# and --workers stops a WEB_CONCURRENCY set by a platform from multiplying it.
# exec, so uvicorn is PID 1 and gets the platform's SIGTERM. Migrations are not
# run here: they are the platform's release step (fly.toml).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --proxy-headers --no-server-header"]
