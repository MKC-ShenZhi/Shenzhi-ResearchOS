# syntax=docker/dockerfile:1
ARG NODE_IMAGE=node:24-bookworm-slim
FROM ${NODE_IMAGE} AS development
USER root
RUN command -v pnpm >/dev/null 2>&1 || npm install --global pnpm@11.0.0
WORKDIR /repo/apps/admin
COPY apps/admin/package.json apps/admin/pnpm-lock.yaml apps/admin/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY apps/admin ./
RUN chown -R node:node /repo/apps/admin
USER node
CMD ["pnpm", "dev", "--host", "0.0.0.0"]

FROM development AS build
RUN pnpm build

FROM nginx:1.28-alpine AS production
COPY --from=build /repo/apps/admin/dist /usr/share/nginx/html
COPY infra/docker/nginx/admin.conf.template /opt/admin.conf.template
COPY infra/docker/nginx/start-admin.sh /opt/start-admin.sh
USER nginx
EXPOSE 3101
ENTRYPOINT ["/bin/sh", "/opt/start-admin.sh"]
