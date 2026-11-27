# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/opt/venv/bin:$PATH"
WORKDIR /repo/apps/agent
COPY packages/agent-contracts /repo/packages/agent-contracts
COPY apps/agent/pyproject.toml apps/agent/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY apps/agent /repo/apps/agent
COPY infra/docker/scripts /opt/docker
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /var/lib/shenzhi/workspace /var/lib/shenzhi/usage-spool \
    && chown -R app:app /var/lib/shenzhi
USER app
EXPOSE 8101
CMD ["uvicorn", "agent_app.main:app", "--host", "0.0.0.0", "--port", "8101", "--no-proxy-headers"]
