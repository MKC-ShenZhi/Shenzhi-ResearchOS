# syntax=docker/dockerfile:1
# Development only; production Compose does not define this service.
FROM node:24-bookworm-slim AS development
RUN npm install --global pnpm@11.0.0
WORKDIR /repo/apps/admin
COPY apps/admin/package.json apps/admin/pnpm-lock.yaml apps/admin/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY apps/admin ./
RUN chown -R node:node /repo/apps/admin
USER node
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
