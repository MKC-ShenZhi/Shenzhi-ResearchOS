# ---- 构建 ----
FROM node:22-alpine AS builder
WORKDIR /app/apps/web
# sharp 无预编译包时的源码编译兜底（pnpm-workspace.yaml 已 allowBuilds: sharp）
# dl-cdn.alpinelinux.org 在本网络下连接会静默冻结，改用阿里云镜像
RUN sed -i 's#dl-cdn.alpinelinux.org#mirrors.aliyun.com#g' /etc/apk/repositories \
    && apk add --no-cache python3 make g++ build-base
RUN corepack enable && corepack prepare pnpm@11.18.0 --activate \
    && pnpm config set registry https://registry.npmmirror.com
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
ARG NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=false
ENV NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED=$NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED
RUN pnpm build

# ---- 运行时 ----
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# Docker 会把 HOSTNAME 设为容器 ID,Next standalone 会据此只绑定 eth0,
# 导致容器内 127.0.0.1 健康检查 connection refused;显式绑 0.0.0.0
ENV HOSTNAME=0.0.0.0
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./.next/static
COPY --from=builder /app/apps/web/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
