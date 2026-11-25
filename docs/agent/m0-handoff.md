# M0 交接与 M0-C 真实环境验收准备

更新：2026-11-18。**M0 = PARTIAL**。M0-R1-B 已由 ChatGPT 独立代码审查通过（用户确认）；真实 PostgreSQL、独立进程、上游服务和故障恢复尚待 M0-C 验收。以下启动、迁移和测试命令是后续执行指引，本次整理未运行。

> 本文件是 M0 阶段的历史交接快照，分支、迁移版本和接口路径已过时，不作为当前运行手册。当前 Agent 产品入口为 `/api/v2/agent/*`，Agent 共享能力为 `/internal/v2/*`；`/internal/v1/*` 仅保留历史 Task/Run 与 Worker drain 接口。请以 [Agent 开发边界](development.md)、[执行与权益](entitlements.md) 和 [部署文档](../engineering/deployment.md) 为准。

## Git 与阶段

- 仓库：`D:\Projects\Shenzhi-ResearchOS`；本地分支：`feat/agent-m0-integration`。
- 当前代码 HEAD：`1d1bc7e0ea7791ba3abe6aa529a13ade1be6ed8f`；原 dev 基线：`5faee7e71bb14e7d6943dab1e2e342af61bd7581`。M0 工作尚未合入 dev；不要据本机 tracking 状态推断远程最新进度。
- M0-B 架构集成阶段收尾：`bfb01b1`（该提交具体修复当前 Run 报告归属；架构迁移还包含其祖先提交）。
- M0-R1-A：`6ccd0d95`，SSE 终态尾部与 Worker 接管事件序号。
- M0-R1-B：`1d1bc7e`，多次 Run 重试后的 Session SSE 恢复游标；已推送 `review/m0-r1-b`，代码审查通过。
- 进入后续会话先执行 `git status --short`、`git branch --show-current`、`git rev-parse HEAD`；若基线有变化先核对，不切换分支或创建 Worktree。验收证据放 `docs/dev/records/agent/`，不自动合并或发布。

## 实际架构

| 组件 | 已实现职责 | M0-C 待验证 |
| --- | --- | --- |
| Web（Next.js） | 页面、Better Auth、同源 BFF；调用 Backend 产品 API | 浏览器身份、BFF 凭据、SSE 转发 |
| Backend（FastAPI） | Session/Turn/Upload、Owner 校验、Knowledge 上游适配；Gateway 调 Agent API，持久事件投影为产品 SSE | 真实网络、持久投影、重启与租约恢复 |
| Agent API / Control | 独立内部 HTTP API；Task/Run/Event/Report/Outbox、重试决策、Run Lease 与 fencing | PostgreSQL 行锁、事务竞争和服务故障 |
| Worker / Runtime | 独立进程通过 Agent API 领取、心跳、执行模型/工具/Skills、上报事件及报告 | 模型与 Knowledge 连通、共享产物、接管行为 |
| Backend PostgreSQL | `CHAT_DATABASE_URL`；Session/Turn、附件等产品数据及投影租约 | 不退化到 Memory，迁移和重启持久性 |
| Agent PostgreSQL | `AGENT_DATABASE_URL`；Task、Run、Event、Outbox、Control 和 Run Lease | 与 Backend 库隔离及执行持久性 |

Backend 不直接访问 Agent 数据库；Worker 经 Agent API，不直接执行 Repository SQL。API 与 Worker 必须共享持久 `AGENT_WORKSPACE_ROOT`。Web 登录另有 `DATABASE_URL` 认证库，不能与上述双业务库概念混淆。详见 [契约](contracts.md)、[生命周期](lifecycle.md)、[部署](../engineering/deployment.md)。

## 配置与依赖

配置来源：`apps/backend/.env.example` → 本地 `.env`；`apps/agent/.env.example` → 本地 `.env`；`apps/web/.env.example` → 本地 `.env.local`，或由进程环境注入。此处只列变量名，不记录凭据或真实服务地址。

| 配置位置 | 验收所需变量 |
| --- | --- |
| Backend | `CHAT_DATABASE_URL`、`AGENT_INTERNAL_URL`、`AGENT_SERVICE_TOKEN`、`BACKEND_BFF_SECRET`、`KNOWLEDGE_BASE_API_URL`；按需 `KNOWLEDGE_BASE_TIMEOUT_SEC`；验收起步关闭 `BACKGROUND_JOBS_ENABLED` |
| Agent API / Worker | `AGENT_DATABASE_URL`（API/迁移）、`AGENT_INTERNAL_URL`（Worker）、`AGENT_SERVICE_TOKEN`、`AGENT_WORKSPACE_ROOT`、`BACKEND_INTERNAL_URL`（Knowledge Adapter） |
| Agent 模型/检索 | 至少一个可用 Provider：`DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`、`ZHIPU_API_KEY` 或 `AUTODL_API_KEY`；型号来自统一 Catalog；按需 `AI_DEFAULT_MODEL`、`AI_AGENT_DEFAULT_MODEL`、`AI_MODEL_REGISTRY_FILE` 及 Provider 覆盖配置；联网检索按选定 Provider 配置 `TAVILY_API_KEY`、`SEARXNG_BASE_URL` 或 `EXA_API_KEY` |
| Web | `BUSINESS_BACKEND_URL`、`BACKEND_BFF_SECRET`、`BETTER_AUTH_SECRET`、`BETTER_AUTH_URL`；完整登录另需 `DATABASE_URL` 及 [认证配置](../auth/CONFIGURATION.md) 中相应变量 |

Web/Backend 的 BFF secret 一致；Backend/Agent API/Worker 的 Agent token 一致，两类凭据分离。`BACKEND_INTERNAL_URL` 要包含 Backend Agent API 前缀，不能只填服务根路径。模型/搜索凭据配置在 Agent 进程，Knowledge 上游配置在 Backend。`BACKEND_ALLOW_INSECURE_LOCAL_BFF` 只用于明确的 loopback 开发，不作为完整验收配置。

依赖：Python ≥3.12、uv、Node ≥22、pnpm 11、PostgreSQL 服务及数据库管理权限、可写持久共享目录；执行建库示例还需 PostgreSQL CLI。安装沿用各应用锁文件：分别在 Backend/Agent 目录 `uv sync --frozen`，在 Web 目录 `pnpm install --frozen-lockfile`。还需模型/搜索/Knowledge 的网络访问和可用配额。仓库无当前部署 Compose/CI 验收门禁。

## M0-C 推荐执行顺序与命令

### 1. 专用数据库与迁移

先由负责人提供**两个独立的专用验收数据库**和有权限的角色。Alembic 建表，不创建 PostgreSQL 实例或数据库。下面是 PostgreSQL CLI 的建库示例（后续仅在已确认的验收实例执行；尖括号由执行者替换，密码走交互或安全配置）：

```text
createdb -h <PG_HOST> -p <PG_PORT> -U <DB_ADMIN> -O <BACKEND_ROLE> <BACKEND_ACCEPTANCE_DB>
createdb -h <PG_HOST> -p <PG_PORT> -U <DB_ADMIN> -O <AGENT_ROLE> <AGENT_ACCEPTANCE_DB>
```

分别将连接配置到对应变量；Agent 迁移使用 asyncpg URL，Backend 迁移会转换普通 PostgreSQL URL。SSL 参数按驱动要求配置，见部署文档。用只读 `SELECT current_database(), current_user;` 验证连接身份和数据库不同。

分别在对应应用目录运行：

```powershell
# apps/backend
uv run --env-file .env alembic -c alembic.ini upgrade head
uv run --env-file .env alembic -c alembic.ini current
# apps/agent
uv run --env-file .env alembic -c alembic.ini upgrade head
uv run --env-file .env alembic -c alembic.ini current
```

本 HEAD 的 Backend head 为 `026_home_scheduler_state`，Agent head 为 `0002_agent_run_controls`。Web 登录数据库另按现有 `apps/web/db/migrations/001_better_auth.sql`、`002_turnstile_verification.sql`、`003_oauth_placeholder_scope.sql` 和认证文档执行，不虚构 pnpm 数据库迁移脚本。`scripts/start-local-postgres.bat` 只启动已有本地实例，不初始化数据目录或创建双库。

### 2. 分终端启动、健康与连通性

以下地址为本机联调入口；跨主机时由环境配置提供实际地址，不把真实地址写入仓库。四个常驻进程独立运行：

```powershell
# apps/agent：Agent API
uv run --env-file .env uvicorn agent_app.main:app --host 127.0.0.1 --port 8101
# apps/backend：Backend
uv run --env-file .env uvicorn app.main:app --host 127.0.0.1 --port 8000
# apps/agent：Worker，另一个终端，同一共享 Workspace
uv run --env-file .env python -m agent_app.worker_main
# apps/web：Web
pnpm dev
```

检查 `GET http://127.0.0.1:8101/internal/v1/health`、`GET http://127.0.0.1:8000/health` 返回 `status=ok`；Web 同源 `GET /api/v1/health` 应可经 BFF 到 Backend。健康端点仅证明存活，不证明数据库、Worker 或模型可用。

用合法 Bearer 服务凭据调用 Agent `GET /internal/v1/config`，再经 Web `GET /api/v1/agent/config` 验证 Gateway；模型应可用且包含所需 Skill。移除/替换凭据应被拒绝。Worker 没有独立 HTTP 健康端点：用进程日志和一次真实任务领取/心跳确认。创建 Session、启动 Turn 走现有 Web `/agents`，保留 session_id、turn_id、task_id、run_id 与脱敏请求日志。

### 3. 现有测试与真实场景

专用验收环境中先补跑现有测试，命令按目录执行：

```powershell
# apps/backend：数据库测试会写入并 purge 固定测试 Owner，绝不指向共享/生产库
uv run --env-file .env python -m unittest tests.test_agent_persistence -v
uv run python -m unittest tests.test_agent_sse_retries tests.test_agent_sse_tail tests.test_agent_contracts tests.test_agent_sessions -v
# apps/agent：这些是单元/内存 SQLite 测试，不是真实 PostgreSQL 验收
uv run pytest tests/unit/test_task_runs.py tests/unit/test_worker_takeover.py tests/unit/test_worker_heartbeat.py tests/unit/test_deep_research_skill.py -q
# packages/agent-contracts
uv run pytest tests/test_wire.py -q
# apps/web
pnpm typecheck
pnpm lint
pnpm test
```

数据库测试必须实际执行、不因缺少 `CHAT_DATABASE_URL` 跳过。R1-B 历史结果为 69 通过、13 跳过，见 [记录](../dev/records/agent/m0-r1-b-sse-retry-cursor.md)；不代表本次重新执行。仓库尚无覆盖以下真实故障矩阵的一键脚本，需按清单手动记录，不能以 ASGI/Mock/SQLite 通过替代独立进程验收。

## M0-C 清单（各项均待验收）

| 项目 | 验收方法 | 通过标准 |
| --- | --- | --- |
| 双 PostgreSQL | 分别连接、迁移、查询 current_database / alembic_version 和表 | 数据库不同，迁移到上述 head；产品表与执行表分别归属正确，无 Memory fallback |
| 独立进程 / Gateway | 分别启动 API/Worker，Web 发起任务；检查内部调用和日志 | 真实 HTTP 提交、领取、心跳、报告闭环；凭据错误被拒绝 |
| Task/Run/Event/Report | 用 Owner 查询 `/internal/v1/tasks/{task_id}`、`/tasks/{task_id}/runs`、`/runs/{run_id}`、`/runs/{run_id}/events`（均带内部前缀及 owner_id）；对照只读 SQL | Task/Turn 关联正确，事件与 report 持久化，重读一致；跨 Owner 不可见 |
| Deep Research | Web 选择 deep-research Skill，完成检索、工具和 Markdown 报告；换 Owner 请求同一文件 | 当前 Run 的成功文件操作形成 report，正文和 Workspace 文件一致，SSE/Turn output 可见；旧 Run/旧文件不冒充本次报告，跨 Owner 拒绝 |
| SSE 实时 / 恢复 | 保存全流后断线续接；清除缓存用 Backend 重启并等投影租约到期后重放 | 每个事件 ID、顺序一致，旧 Run 尾部完整，最终 result 一次；after 是下一事件偏移，result ID=6 时 after=6 返回、after=7 不返回 |
| 多 Run 重试 | 在专用环境经受控 Provider 失败/超时触发两/三 Run；对照完整枚举和缓存/无缓存流 | attempt 有序，历史 Run 不漏；失败/超时最多三次，result 与最终 Run 对应，SSE ID 不因恢复改变；不直接改库伪造成功 |
| Lease / 接管 / Fencing | 任务执行中终止 Worker，等待 Run Lease 到期后另一 Worker 接管；用保存的旧 worker_id/token 尝试心跳、事件和首次报告 | 默认 45 秒 Lease、12 秒心跳符合实际日志；token 增长，旧 token 被拒绝，事件 seq 从已有最大值继续，无冲突或遗漏 |
| 服务重启 | 分别重启 API、Worker、Backend，重查任务与文件并从 Web 重新订阅 | 持久状态/Workspace 保留；Backend 投影租约默认 300 秒、30 秒续租，其他持有者有效时允许 409，到期后可恢复；不假设启动自动恢复活跃投影 |
| 异常 / 日志 | 错误 token/Owner、上游不可用、模型超时、取消、网络中断；检查各进程日志及最终状态 | 错误可定位且不泄露密钥，失败重试/取消状态正确；恢复后无永久 running、重复 result、冲突 seq；记录实际等待时间与错误码 |

每项证据至少包括代码 SHA、进程角色、脱敏配置变量名、请求/响应、关联 ID、时间、迁移版本、结果及日志。失败项保留复现步骤，整体继续 PARTIAL。

## 已知风险与当前缺口

- 本机静态检查：Agent `.env` 不存在；Backend 本地文件未列出 `AGENT_INTERNAL_URL` / `AGENT_SERVICE_TOKEN`；模型/搜索凭据仍位于 Backend 本地文件，需另配置到 Agent，不能认为自动继承。Web/Backend 文件存在不证明值正确；未核实外部注入环境或任何网络/数据库可用性。
- `psql` / `createdb` 当前未在 PATH 找到，不等于未安装 PostgreSQL；需确认实例、CLI 路径、专用双库及角色权限。Agent 虚拟环境目录存在，但上次锁文件同步遭镜像 403，完整依赖安装仍需确认；单元测试曾复用 Backend 环境。
- PostgreSQL 锁竞争、Outbox 派发、断网与并发恢复尚无真实证据；数据库测试会清理固定 Owner，只能用隔离验收库。健康检查不检查数据库就绪。
- Worker 接管仍从头执行 Runtime，可能重复模型/工具副作用；无独立 Attempt、Checkpoint 或工具副作用去重保证。完整 SSE 重建依赖历史 Run/事件保留且不可变、报告与重试原子提交。
- Backend 投影恢复需重订阅且可能等待租约到期；共享 Workspace 丢失不能靠事件流恢复产物。旧版本已发出的错误游标不追溯修复。
- Deep Research 需要真实模型、检索、Knowledge 与持久卷；费用/配额、故障注入目标与专用环境由负责人先确认。M0-C 结果出来前，不宣称生产可用，不新增下一阶段架构。
