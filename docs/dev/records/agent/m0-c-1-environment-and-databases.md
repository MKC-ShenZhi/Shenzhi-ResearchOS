# M0-C-1：本机隔离环境与双 PostgreSQL 验收

日期：2026-11-18。结论：**M0-C-1 本阶段范围 PASS，待 ChatGPT 独立审查；M0 整体仍为 PARTIAL**。本轮没有执行完整研究任务、付费模型/搜索调用、Worker 故障注入或 Web 登录闭环。

## A. Git

- 开始分支 `feat/agent-m0-integration`、HEAD `1d1bc7e0ea7791ba3abe6aa529a13ade1be6ed8f` 与要求一致；仅有用户已审查的两份交接文档变更。
- 通过 `git diff --check` 后，仅提交 `docs/agent/m0-handoff.md` 与 `docs/dev/records/agent/m0-r1-b-sse-retry-cursor.md`。
- 文档 Commit / 当前 HEAD：`374f4ec7408ca225c29a91c6d9b5b7c617789ab1`，提交信息 `docs(agent): document M0 handoff and M0-C acceptance plan`。
- 未 Push、PR、Merge、Rebase、切分支或创建 Worktree。业务代码、测试、迁移和锁文件均无修改。本报告留作未提交文件供审查。

## B. 环境与配置

| 项目 | 实测结果 |
| --- | --- |
| 工具 | 系统 Python 3.13.18；Backend venv Python 3.12；Agent venv Python 3.13；uv 0.13.6；Node 26.13.0；pnpm 12.16.1；Docker Engine 29.9.2 |
| Docker | 已安装 Desktop，起初 Engine 未运行；使用 `docker desktop start --detach` 启动。Engine 启动后看到既有 `shenzhi-postgres`，未连接、修改或重启它及其卷 |
| PostgreSQL CLI | 宿主机 PATH 未找到 psql；使用新容器自带 psql，无需全局安装 |
| Backend 依赖 | `uv sync --frozen` 成功；45 个包兼容性检查通过，已安装版本全部符合原锁文件 |
| Agent 依赖 | 原镜像 watchfiles 下载 403；使用原锁文件导出的版本/哈希从官方 PyPI 安装；48 个包兼容性检查通过，已安装版本全部符合原锁文件 |
| Web | 复用现有 node_modules：Next 16.2.12、React 19.2.8、TypeScript 5.9.2；typecheck 通过。未重装依赖；pnpm 版本与交接文档建议的 11 不同，未升级/降级工具 |
| 目录 | 新建可写 `apps/agent/workspace/m0-c1-20261118`；脚本/日志存 Backend `.venv` 内；配置与这些目录均被现有 Git 规则忽略 |

只读取原配置是否存在，不连接其数据库或上游。未输出配置值、密钥或完整数据库 URL：

| 来源 | 检查结果 / 适用性 |
| --- | --- |
| 原 Backend `.env` | CHAT_DATABASE_URL、BACKEND_BFF_SECRET、KNOWLEDGE_BASE_API_URL、AUTODL_API_KEY、TAVILY_API_KEY 有值；AGENT_INTERNAL_URL、AGENT_SERVICE_TOKEN 缺失；不能直接作为本次验收配置。dotenv 提示第 26 行解析警告，未输出内容、未修改原文件 |
| 原 Agent `.env` | 不存在 |
| 原 Web `.env.local` | BUSINESS_BACKEND_URL、BACKEND_BFF_SECRET、BETTER_AUTH_SECRET、BETTER_AUTH_URL、DATABASE_URL 均有值；仅确认存在，未验证值、凭据匹配或目标安全性，未连接认证库 |
| 当前进程环境 | 上述检查的连接/凭据变量未注入，不依赖全局配置 |
| 新根目录 `.env.m0-c1-backend` | CHAT_DATABASE_URL、AGENT_INTERNAL_URL、AGENT_SERVICE_TOKEN、BACKEND_BFF_SECRET 均已配置；后台调度与不安全 BFF 放行关闭，仅指向新建验收库/本机 Agent API |
| 新根目录 `.env.m0-c1-agent` | AGENT_DATABASE_URL、AGENT_INTERNAL_URL、AGENT_SERVICE_TOKEN、AGENT_WORKSPACE_ROOT、BACKEND_INTERNAL_URL 均已配置；Agent token 与 Backend 相同 |
| 新根目录 `.env.m0-c1-postgres` | 新容器初始化专用配置；随机凭据仅保存在本地忽略文件 |
| 模型 / Knowledge / 搜索 | 未向专用配置复制现有外部凭据；服务 smoke 子进程移除外部 API key、原 DATABASE_URL、Knowledge/检索目标。Agent config 返回模型数 0，本阶段基础检查可用，C-2 前需配置可用模型和上游 |

本阶段不改写原 `.env` 或全局设置。新文件含本地随机秘密，不提交、不粘贴；后续启动需显式选择 `.env.m0-c1-*`，不能误用原 `.env`。

## C. 数据库

- 新容器 `m0-c1-postgres-20261118`，使用本机已有 `postgres:16` 镜像；仅绑定 loopback 55432。
- 新命名卷 `m0-c1-postgres-data-20261118` 挂载 `/var/lib/postgresql/data`，带专用验收用途标签。创建前确认容器、卷名称不存在且端口未占用。
- 新数据库 `shenzhi_m0c1_backend` / `shenzhi_m0c1_agent`，独立非超级用户 Owner `m0c1_backend` / `m0c1_agent`；撤销各库 PUBLIC CONNECT，仅给各自角色连接权限。
- 两套真实 Alembic 升级成功：Backend `026_home_scheduler_state`；Agent `0002_agent_run_controls`，与实际迁移链一致。
- asyncpg 只读查询 `current_database()`、`current_user`、`alembic_version`、public 表成功。Backend 共 25 张 public 表，含 agent_sessions / agent_turns / agent_uploads；无 agent_tasks。Agent 共 6 张 public 表，含 agent_tasks / agent_runs / agent_run_events / agent_outbox / agent_run_controls 与 alembic_version；无 agent_sessions。
- 以每个角色尝试连接另一个验收数据库，均返回数据库 CONNECT 权限拒绝。
- 仅重启本轮新容器一次，再次查询双库迁移与表全部保留；这是已执行的持久化验证，不等同于宿主机故障或备份恢复验收。
- Backend 实例类型为 `PostgresAgentSessionRepository`、`is_durable=True`，没有 Memory fallback。
- 最终容器 healthy，保留运行和持久卷供下阶段复用；没有删除任何资源。Agent Task 数始终为 0。

## D. 服务与 Gateway

使用专用配置、现有 venv 分别短时启动三个本机进程（CREATE_NO_WINDOW，日志重定向）：

| 进程 | 实际入口 | 结果 |
| --- | --- | --- |
| Agent API | Agent venv Python `-m uvicorn agent_app.main:app --host 127.0.0.1 --port 18101` | `/internal/v1/health` 200；合法 Bearer 的 `/internal/v1/config` 200；缺凭据 401 |
| Backend | Backend venv Python `-m uvicorn app.main:app --host 127.0.0.1 --port 18000` | `/health` 200；带专用 BFF secret 调 `/api/v1/agent/config` 200，实际经 HTTP Gateway 到 Agent；缺凭据 401 |
| Worker | Agent venv Python `-m agent_app.worker_main` | 空队列连续轮询约 4 秒，API 日志确认 `/internal/v1/worker/claim` 200；未提交任何 Task、未调用模型 |

短时启动器 PID 为 868 / 39740 / 40140（API / Backend / Worker）。完成后全部停止，并检查专用端口和对应 Python 命令无残留。原始脱敏范围内的日志保留于 `apps/backend/.venv/m0-c1-logs/`，Worker 日志确认正常启动和轮询，无未预期 ERROR。

Web 服务与登录 NOT RUN。配置 GET 与空领取证明基础连通，不证明 Task/Run/Event/Report 的真实执行闭环、长期稳定性或模型能力。

## E. 实际命令与结果

以下目录均相对仓库根；临时辅助脚本位于现有忽略的 Backend `.venv`，没有进入业务代码或测试目录。

```text
根目录：
docker desktop start --detach
docker version / docker info / docker ps -a / docker volume ls
docker volume create --label shenzhi.purpose=m0-c1-acceptance m0-c1-postgres-data-20261118
docker run -d --name m0-c1-postgres-20261118 --label shenzhi.purpose=m0-c1-acceptance --env-file .env.m0-c1-postgres -p 127.0.0.1:55432:5432 --mount type=volume,source=m0-c1-postgres-data-20261118,target=/var/lib/postgresql/data --health-cmd "pg_isready -U m0c1_admin -d m0c1_admin" --health-interval 5s --health-retries 12 postgres:16
apps/backend/.venv/Scripts/python.exe apps/backend/.venv/m0_c1_prepare.py
apps/backend/.venv/Scripts/python.exe apps/backend/.venv/m0_c1_databases.py
docker restart m0-c1-postgres-20261118
apps/backend/.venv/Scripts/python.exe apps/backend/.venv/m0_c1_verify.py
apps/backend/.venv/Scripts/python.exe apps/backend/.venv/m0_c1_services.py
```

prepare 脚本在实际执行中先于 docker run 创建配置。prepare/databases 是一次性创建器，发现同名配置或数据库时停止，后续不要重跑初始化。verify 与 services 分别负责上述只读核查、带 finally 停止的短时服务检查。

依赖安装与迁移：

```text
apps/backend：uv sync --frozen
apps/agent：uv sync --frozen   # FAIL：镜像 403；改用下列官方源方案
uv export --frozen --format requirements-txt --no-emit-workspace --no-emit-package agent-contracts --output-file .venv/m0-c1-requirements.txt --no-header
uv pip sync --python .venv/Scripts/python.exe --index-url https://pypi.org/simple --require-hashes .venv/m0-c1-requirements.txt
uv pip install --python .venv/Scripts/python.exe --no-deps --index-url https://pypi.org/simple -e . -e ../../packages/agent-contracts
两个应用各自目录：uv pip check --python .venv/Scripts/python.exe
apps/backend：uv run --no-sync --env-file ../../.env.m0-c1-backend alembic -c alembic.ini upgrade head
apps/backend：uv run --no-sync --env-file ../../.env.m0-c1-backend alembic -c alembic.ini current
apps/agent：uv run --no-sync --env-file ../../.env.m0-c1-agent alembic -c alembic.ini upgrade head
apps/agent：uv run --no-sync --env-file ../../.env.m0-c1-agent alembic -c alembic.ini current
```

第三方依赖按锁文件哈希验证；本地 editable 包单独安装。用 importlib.metadata 与各自 uv.lock 比较，已安装版本在锁文件之外的列表均为空。后续 Agent 执行 `uv run --no-sync` 复用此环境，直接 sync 原镜像仍可能 403。前期导出安装有三次参数/editable 哈希检查失败，纠正命令后完成；未改动锁文件。

| 实际测试命令 | PASS / FAIL / SKIP |
| --- | --- |
| Backend：`uv run --no-sync --env-file ../../.env.m0-c1-backend python -m unittest tests.test_agent_persistence -q` | 10 / 0 / 0，真实专用 PostgreSQL，允许测试自身清理固定 Owner |
| Backend：`uv run --no-sync --env-file ../../.env.m0-c1-backend python -m unittest tests.test_agent_sse_retries tests.test_agent_sse_tail tests.test_agent_contracts tests.test_agent_sessions -q` | 35 / 0 / 0，内存/Mock 回归，非真实模型流 |
| Agent：`uv run --no-sync pytest tests/unit/test_task_runs.py tests/unit/test_worker_takeover.py tests/unit/test_worker_heartbeat.py tests/unit/test_deep_research_skill.py -q` | 30 / 0 / 0，另 20 个 subtests PASS；单元/内存 SQLite |
| Agent：`uv run --no-sync pytest ../../packages/agent-contracts/tests/test_wire.py -q` | 7 / 0 / 0 |
| Web：`pnpm typecheck` | 退出码 0，单项检查 PASS，无测试用例数量 |

合计 Python 测试 **82 PASS / 0 FAIL / 0 SKIP**，另 20 个参数子场景通过。初次隔离核查脚本将预期 CONNECT 拒绝误按另一异常类型捕获，脚本失败；修正本地辅助脚本异常类型后通过，不是产品代码修复。未将安装/脚本启动失败计为测试通过。

NOT RUN：真实任务及报告持久化闭环、完整 Deep Research、付费模型/真实搜索/Knowledge 请求、真实 SSE 断线/多 Run 重试、Worker 故障接管、Fencing 故障注入、Web 服务/登录、Web lint/完整测试、宿主机重启与备份恢复。不能用上述离线回归替代这些项目。

## F. 阻塞分类

- **环境配置**：专用配置满足 C-1；C-2 尚无启用模型/检索/Knowledge 配置，Web 仍指向原配置且未验证与专用 Backend 的匹配。原 Backend `.env` 解析警告需在后续明确配置整理范围后处理。
- **数据库/部署**：C-1 无未解决阻塞。单实例双库/独立角色已验证，非双 PostgreSQL 服务器容灾；需保留专用卷并确认后续始终使用专用 URL。API/Worker 的跨主机共享卷尚未验收。
- **代码**：本轮未发现阻断基础迁移/启动/Gateway 的代码问题；未修改业务代码。真实任务及竞争问题尚无本轮证据，不能判定全部可靠性通过。
- **外部依赖**：原依赖镜像 403 以官方源安装同版本解决；真实模型/搜索配额、Knowledge 可达性均 NOT RUN。Node/pnpm 与推荐版本不同，Web typecheck 成功不代表完整构建/运行验证。

## G. 下一阶段条件

可将本报告提交 ChatGPT 独立审查，审查后再决定进入 M0-C-2。后续需确认付费模型/搜索调用范围和配额、在专用配置中配置 Provider 与 Knowledge、明确 Web 是否纳入下一轮，以及专用服务启动/关闭责任。首先完成一条受控 Task/Run/Event/Report 与报告归属闭环，再逐步进入真实 SSE/恢复矩阵；本轮不自动继续执行。

当前保留资源：专用 PostgreSQL 容器和命名卷、新本地忽略配置、Workspace、辅助脚本及日志。API/Backend/Worker 均已停止。所有真实秘密仅留本地忽略文件，不在本报告中。
