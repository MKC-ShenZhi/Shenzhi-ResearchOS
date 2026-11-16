# 部署与运行环境

本文描述 ShenZhi 当前的部署形态、运行环境与已知约束。改动任何部署相关配置前，先同步本文。

真实服务器 IP、上游服务地址与密钥只写在本地 `.env` 或部署平台的环境变量中，本文统一使用占位符。

---

## 一、运行形态

日常开发和联调在本地进行，正式环境位于韩国服务器。仓库提供以下运行入口。

| 服务 | 运行入口 | 职责 |
|------|----------|------|
| Web | 在 `apps/web` 执行 `pnpm dev` 本地开发，使用 `pnpm build` 构建生产版本 | Next.js 页面、认证和同源 BFF |
| Backend | 在 `apps/backend` 通过 Uvicorn 启动 `app.main:app`，以 `GET /health` 检查服务 | FastAPI 核心业务 API 与后台任务 |

浏览器通过同源 `/api/v1` 访问 Web BFF。BFF 使用 `BUSINESS_BACKEND_URL` 和 `BACKEND_BFF_SECRET` 调用 FastAPI。本地启动和提交前检查见 [ONBOARDING](../../ONBOARDING.md)。

原阿里云 ECS + GHCR + Watchtower 链路已完全停用，相关 `infra/` 与 GitHub Actions 配置已移除。仓库当前**没有 CI 门禁**，提交前的检查需本地执行（见 [ONBOARDING](../../ONBOARDING.md)）。

## 二、环境变量与运行约束

- 配置项见 [Web 示例](../../apps/web/.env.example) 和 [Backend 示例](../../apps/backend/.env.example)。真实值只写在本地环境文件或由部署环境注入。`NEXT_PUBLIC_` 变量由 Next.js 在构建时内联，修改后需重新构建 Web。
- `BACKEND_BFF_SECRET` 两端必须一致。`BACKEND_ALLOW_INSECURE_LOCAL_BFF` 仅用于本机 loopback 联调。
- `BETTER_AUTH_URL` 填写浏览器实际访问的站点地址。GitHub OAuth 回调使用 `<BETTER_AUTH_URL>/api/auth/callback/github`，`AUTH_EMAIL_FROM` 须在阿里云 DirectMail 完成验证。
- Web 认证使用 `DATABASE_URL`，后端持久化使用 `CHAT_DATABASE_URL`。部署前按各应用的文档完成数据库迁移。缺少 `CHAT_DATABASE_URL` 时，会话退化为进程内存态。使用 Neon 连接串时，asyncpg 需要将 `?channel_binding=require&sslmode=require` 改为 `?ssl=require`。
- `KNOWLEDGE_BASE_API_URL` 须能从调用它的服务访问。上游不可用时，知识检索接口返回错误。
- FastAPI 以常驻进程运行，`lifespan` 负责恢复会话运行状态并启动已启用的调度器。Agent 的运行归属与实时事件缓冲存于进程内存，workspace 写入本地磁盘。多进程部署需考虑进程间的续接、steer 和 stop 限制。详见 [Agent 会话持久化](../agent/session-persistence.md)。

---

## 三、正式服务器

| 项目 | 配置 |
|------|------|
| CPU | 2 vCPU(Intel Xeon Cascade Lake,约 2.89 GHz,支持 AVX2 / AVX-512) |
| 内存 | 约 4 GB(3.8 GiB) |
| 交换空间 | 7.7 GiB |
| 磁盘 | 80 GiB 虚拟磁盘 |
| GPU | 无计算 GPU |
| 系统 | Ubuntu 22.04.5 LTS(虚拟机) |

服务器地址、登录方式及发布与回滚流程向服务器负责人确认。

完成数据库迁移后，正式常驻后端设置 `BACKGROUND_JOBS_ENABLED=true`，统一启动首页数据任务、会议 DDL 同步和论文库会议目录同步。此开关默认关闭。已有部署升级时，用它替换原来的 `HOME_FEED_SCHEDULER_ENABLED` 和 `CONFERENCE_SYNC_ENABLED`。论文库首份目录可在上线前提前同步，见 [会议目录快照](../knowledge/PAPER-LIBRARY-V2.md#常驻后端的会议目录快照)。
