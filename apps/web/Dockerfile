# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS dependencies
RUN npm install --global pnpm@11.0.0
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /repo/apps/web
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile

FROM dependencies AS development
COPY apps/web ./
EXPOSE 3000
CMD ["pnpm", "dev", "--hostname", "0.0.0.0"]

FROM development AS build
# Public browser configuration only. Never pass server secrets as build args.
ARG NEXT_PUBLIC_KNOWLEDGE_SOURCE=bff
ARG NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=false
ARG NEXT_PUBLIC_TURNSTILE_SITE_KEY=
ENV NEXT_PUBLIC_KNOWLEDGE_SOURCE=$NEXT_PUBLIC_KNOWLEDGE_SOURCE NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=$NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED NEXT_PUBLIC_TURNSTILE_SITE_KEY=$NEXT_PUBLIC_TURNSTILE_SITE_KEY
RUN pnpm build

FROM node:24-bookworm-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/web/.next/static ./.next/static
COPY --from=build --chown=node:node /repo/apps/web/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
