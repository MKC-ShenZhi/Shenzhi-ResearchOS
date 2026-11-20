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
| Agent API | 在 `apps/agent` 通过 Uvicorn 启动 `agent_app.main:app` | 内部 Task / Run、控制与持久事件 API |
| Agent Worker | 在 `apps/agent` 执行 `uv run --env-file .env python -m agent_app.worker_main` | 领取任务、续租、执行并上报事件与结果 |
| Agent Usage Worker | 在 `apps/agent` 执行 `uv run --locked --env-file .env python -m agent_app.usage_worker` | V2 用量 Outbox 投递、恢复、对账与关闭清单处理 |

本地 VS Code / Cursor 可使用 `.vscode/tasks.example.json` 作为 `.vscode/tasks.json` 的项目任务模板；本地任务文件不入库。`ShenZhi: 全栈开发` 并行启动 Web、Backend、Agent API、Agent Worker、Agent Usage Worker 五个进程，各用独立终端。已有前后端在运行时，先终止旧任务再启动全栈，避免重复占用端口；`ShenZhi: Agent 开发` 可只启动三个 Agent 进程。Python 启动任务使用各应用目录下的 `.env` 和现有锁文件；Agent API 不启用热重载，Worker 代码或配置变化后须重启三个 Agent 进程，并核对已安装 Policy 的能力 digest。

`ShenZhi: 数据库迁移` 对应 Backend，`ShenZhi: Agent 数据库迁移` 对应独立 Agent 库。启动任务不会自动建库、迁移、安装 Policy 或改变授权模式。V2 验收配置与权限门禁见 [用户权益](../agent/entitlements.md)。

浏览器通过同源 `/api/v1` 访问 Web BFF。BFF 使用 `BUSINESS_BACKEND_URL` 和 `BACKEND_BFF_SECRET` 调用 FastAPI。本地启动和提交前检查见 [ONBOARDING](../../ONBOARDING.md)。

原阿里云 ECS + GHCR + Watchtower 链路已完全停用，相关 `infra/` 与 GitHub Actions 配置已移除。仓库当前**没有 CI 门禁**，提交前的检查需本地执行（见 [ONBOARDING](../../ONBOARDING.md)）。

## 二、环境变量与运行约束

- 配置项见 [Web 示例](../../apps/web/.env.example) 、[Backend 示例](../../apps/backend/.env.example) 和 [Agent 示例](../../apps/agent/.env.example)。真实值只写在本地环境文件或由部署环境注入。`NEXT_PUBLIC_` 变量由 Next.js 在构建时内联，修改后需重新构建 Web。
- `BACKEND_BFF_SECRET` 两端必须一致。`BACKEND_ALLOW_INSECURE_LOCAL_BFF` 仅用于本机 loopback 联调。
- `BETTER_AUTH_URL` 填写浏览器实际访问的站点地址。GitHub OAuth 回调使用 `<BETTER_AUTH_URL>/api/auth/callback/github`，`AUTH_EMAIL_FROM` 须在阿里云 DirectMail 完成验证。
- Web 认证使用 `DATABASE_URL`，后端持久化使用 `CHAT_DATABASE_URL`；V1 部署中两者指向同一 `shenzhi` PostgreSQL 数据库，各自保留连接配置。部署前按各应用的文档完成数据库迁移。缺少 `CHAT_DATABASE_URL` 时，会话退化为进程内存态。使用 Neon 连接串时，asyncpg 需要将 `?channel_binding=require&sslmode=require` 改为 `?ssl=require`。
- `KNOWLEDGE_BASE_API_URL` 须能从调用它的服务访问。上游不可用时，知识检索接口返回错误。
- Backend 以常驻进程运行，`lifespan` 负责恢复会话投影并启动已启用的调度器。Backend 的 SSE 缓冲在进程内，已关联的 Task / Run 可通过 Agent 持久事件重建投影。详见 [Agent 会话持久化](../agent/session-persistence.md)。
- Agent 使用独立的 `AGENT_DATABASE_URL`，迁移在 `apps/agent` 单独执行。Backend 和 Worker 使用 `AGENT_INTERNAL_URL` 调用 Agent API，Agent 的 Knowledge Adapter 使用 `BACKEND_INTERNAL_URL` 调用 Backend。V1 使用 `AGENT_SERVICE_TOKEN`；V2 的 gateway、fact reader、control、worker 角色凭据各自隔离，并与旧 service token 不同，同一角色的调用方/接收方配置保持一致。Agent API、执行 Worker 和 Usage Worker 使用一致的 Agent 环境，Usage Worker 不可省略。
- Agent API 与 Worker 配置同一个持久化 `AGENT_WORKSPACE_ROOT`。模型和搜索 Provider 变量配置在 Agent 侧。Agent 健康端点 `GET /internal/v1/health` 仅检查 API 进程存活。启动说明见 [Agent README](../../apps/agent/README.md)。
- Backend 的 Agent Gateway 直接访问配置的内部服务，不继承编辑器/进程的 HTTP 代理环境，避免本机 Agent 配置和运行请求被 Internet 代理返回 502。此约定仅作用于 Backend→Agent Client，不改变模型、搜索和 Knowledge 等外部服务的代理设置。

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

Admin Console 独立启动与同源反向代理要求见 [Admin README](../../apps/admin/README.md)。local_password 仅供本机，生产远程访问不得经 loopback 代理绕过本地限制，需先实现独立强认证。
