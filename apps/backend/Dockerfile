# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/opt/venv/bin:$PATH"
WORKDIR /repo/apps/backend
COPY packages/agent-contracts /repo/packages/agent-contracts
COPY apps/backend/pyproject.toml apps/backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY apps/backend /repo/apps/backend
COPY infra/docker/scripts /opt/docker
COPY apps/web/db/migrations /opt/auth-migrations
RUN useradd --uid 10001 --create-home app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
