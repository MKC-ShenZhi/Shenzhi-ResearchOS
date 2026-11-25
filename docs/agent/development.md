# Agent Platform 开发边界

Agent Platform 服务拆分在 `feat/agent-architecture-migration` 分支落地。共享协议位于 `packages/agent-contracts/`；Agent 独立应用、Runtime、Provider、能力、Skills、Workspace、Task/Run API、PostgreSQL Repository、Outbox 和 Worker 位于 `apps/agent/`。本页描述代码归属；双进程和可靠性验收仍需在配置真实数据库与服务后执行。

## 当前所有权

| 区域 | 权威所有者 | 当前实现与边界 |
| --- | --- | --- |
| 共享协议 | `packages/agent-contracts/` | 领域 dataclass 与共享 Pydantic Wire Model；Gateway 与 Agent 路由使用同一组提交、Task、Run、事件和报告结构 |
| 产品 API 与身份 | Backend | `/api/v2/agent/*` 为唯一 Agent 产品 BFF 路径；产品 JSON/SSE 契约仍按各端点定义，独立 Task 的 V2 JSON 提交使用 `/submissions`；新任务、配置、Workspace、文件与匿名认领的内部通信走 V2；存量 V1 Run 的查询与控制保留临时兼容 |
| Session / Turn / Upload | Backend | 产品对话、附件 owner 权限、用户身份和产品 Timeline 由 Backend 持有；Task/Run 状态通过 Agent API 投影 |
| Agent Execution | Agent | Runtime、Provider 路由、Skills、Workspace、Web/Paper 能力和 Knowledge HTTP Adapter 已迁入 |
| Agent Control / Worker | Agent | 独立数据库迁移、Task/Run/Event/Outbox、领取、Lease/fencing、取消、steer、报告和失败重试已实现 |
| Workspace 与产物 | Agent | 使用共享持久卷和 `AGENT_WORKSPACE_ROOT`；API 与 Worker 必须配置到同一目录 |
| Backend Gateway | Backend | 新任务、配置、Workspace、文件与匿名认领走 V2 路由；正式部署下 V1 新 Task 提交已关闭，V1 Gateway 与 Worker 仅用于存量排空和历史读取，移除须等待双库审计和外部调用方核验 |

## 当前执行链路

```text
Backend 产品 API / Session 投影
       │
       ├── 新任务 ──V2 网关──> Agent /internal/v2/*（提交、事件、控制、报告）
       ├── 共享能力 ──V2 Service Gateway──> Agent /internal/v2/*（config / workspace / file / claim）
       └── 排空期旧任务 ──兼容 Gateway──> Agent /internal/v1/*（查询、事件、控制）
                                      │
                                      ├── PostgreSQL SKIP LOCKED + Worker Lease/fencing
                                      ├── Agent Runtime / Provider / Tools
                                      └── 持久 Run Events / ExecutionReport
```

Backend 通过 `agent-contracts` 校验跨服务请求与响应。新提交不按 Owner 类型选择协议，产品 API 使用 V2 执行网关。当前产品 API 路径为 `/api/v2/agent/*`，`/run` 与 Session run 保持 SSE 契约，独立 Task JSON 提交使用 `/submissions`。配置、Workspace、文件与匿名认领也使用 V2 URL，并以独立 `AGENT_SERVICE_TOKEN` 访问 Service 角色；`AGENT_GATEWAY_TOKEN` 只发往 Gateway 角色接口。Session Turn 保留持久 `_agent_protocol` 标记以恢复 V1 存量任务；Run 列表、状态、事件与用量读取沿用对应协议。Stop/Steer 查询 V2，只有明确 404 才查询 V1；V1 Worker 和接口须待存量排空后才能移除。V2 准入、角色凭据与新 Worker 由部署配置启用（`AGENT_V2_ADMISSION`、`AGENT_WORKER_PROTOCOL`）。Knowledge 仍归 Backend，Agent 通过受服务凭据保护的 Backend 内部 API 调用。上传附件目前由 Backend 校验 owner、解析并以内联文本随 Task 提交；`input_ref` 尚未启用，Agent 收到非空引用会明确失败。Agent API 与 Worker 必须使用同一个 `AGENT_WORKSPACE_ROOT` 共享持久目录。

Agent `AGENT_V1_ADMISSION` 的默认值为 `drain_only`，正式环境无论此值如何都拒绝 V1 新 Task；只有显式隔离的 `AGENT_DEMO_MODE=1` 演示环境并将 admission 设为 `legacy`，才允许演示提交。V1 Worker 仍可领取未计量的历史 Task，V2 Worker 只领取带 V2 metering profile 的 Task。V2 授权准入由 Backend `AGENT_V2_ADMISSION` 与签名 Grant 控制，与 V1 drain 开关无关。部署时开启 V2 admission、配置 V2 Worker 和计量服务后，保持 V1 Worker 运行至只读审计确认任务排空。

Agent 使用独立 `AGENT_DATABASE_URL`。新 Worker 默认走 V2，配置专用 `AGENT_WORKER_TOKEN`；只有处理历史 V1 Task 的 drain Worker 才显式设置 `AGENT_WORKER_PROTOCOL=1` 并使用 `AGENT_SERVICE_TOKEN`。在 `apps/agent` 执行 `uv run alembic upgrade head`，再分别启动 `uv run uvicorn agent_app.main:app ...` 与 `uv run python -m agent_app.worker_main`。

### V1 排空审计

正式部署默认拒绝 V1 新 Task。保持历史 V1 Worker 运行以处理存量后，用仓库根目录的只读审计脚本核对两库数据：

```powershell
$env:AGENT_DATABASE_URL = '<只读 Agent PostgreSQL URL>'
$env:CHAT_DATABASE_URL = '<只读 Backend PostgreSQL URL>'
uv run --project apps/backend --frozen --no-sync python scripts/agent_v1_drain_audit.py
```

脚本在两个数据库各自的只读事务中统计无 V2 metering 记录的 Task/Run、活跃 V1 Session Turn，以及仍由 Session Turn 引用的 V1 Task；输出不包含 DSN、Owner 或记录 ID。退出码 `0` 表示数据库侧的 Task 排空与历史引用门槛均为零，`1` 表示仍有数据库门槛未清，`2` 表示连接或 schema 检查失败。即使数据库门槛通过，也必须另用部署访问日志证明没有旧 Backend、Admin 或演示 Worker 调用 V1；脚本会将 `external_v1_callers_verified` 和 `v1_retirement_proven` 保持为 `false`，不会单独批准退役。

### 退役执行门槛

1. 先部署 V2 产品入口和 Worker，Agent 保持 `AGENT_V1_ADMISSION=drain_only`；新 Worker 显式用 `AGENT_WORKER_PROTOCOL=2`。旧 Worker 可继续用独立进程、`AGENT_WORKER_PROTOCOL=1` 与旧 `AGENT_SERVICE_TOKEN` 排空，但不可再用 `legacy` 准入。
2. 对入口代理、Backend 和 Agent API 的访问日志分别检索旧产品前缀 `/api/v1/agent/`、V1 内部执行前缀 `/internal/v1/tasks`、`/internal/v1/runs` 与 `/internal/v1/worker`。把合法的隔离 M1 Demo 流量单独标识；任何非 Demo 的旧调用都要先迁移调用方。观察期至少覆盖已知最长客户端重试周期、后台任务周期和一次完整发布窗口；没有可证明覆盖这些周期的日志时，外部调用方门槛保持未通过。
3. 在日志确认无旧生产调用后，停止 V1 drain Worker，再用同一双库 DSN 重新运行只读审计。必须得到 `database_drain_clear=true`、`backend_legacy_task_references_clear=true`，并保存两次审计输出、日志检索条件/时间范围、Worker 停止时间与发布版本，作为人工签核证据。不要清理旧 Task、Run、Turn 或事件来让计数归零。
4. 仅在上述证据完整后，才移除 `apps/agent/src/agent_app/api/routes.py` 的 V1 router 和 Worker V1 分支、Backend `AgentGateway` V1 adapter/Run 协议回退、`_agent_protocol` 的 V1 恢复分支及 V1 admission 配置。保留历史数据库记录；先部署不再访问 V1 的 Backend/Agent，再按数据保留策略另行决定是否归档或删除旧数据。

此门槛不限制当前“V1 退役首版”：当前版本已关闭正式 V1 新 Task、将新流量与默认 Worker 切到 V2，并保留 drain 兼容。只有最后的 V1 执行链删除需要上述部署证据。

## 后续运维与验收

- Backend 旧 Runtime、Provider、Tool Executor、Worker Executor 与重复的 Agent 专属 LLM/Web 集成已删除；相关模型目录和搜索集成测试归入 Agent。
- `agent_sessions/live.py` 仅作为 Backend 进程内 SSE 订阅缓冲，恢复时从 Agent 持久事件重放，不作为权威事件来源。
- 附件正文仍由 Backend 校验 owner 并以内联文本随 Task 提交；`input_ref` 未启用，Agent 收到非空引用会明确失败。
- Agent API 与 Worker 的共享 Workspace 卷必须在实际部署中指向同一持久目录。
- 真实服务联调需覆盖独立进程、重启恢复、事件重放、Lease fencing、重试、取消、附件、Knowledge、Session 投影与 SSE 重连。本次迁移按用户要求未运行自动化测试或真实服务验收。

Session/Turn 与 Task/Run 的关联规则见 [生命周期](lifecycle.md)，共享 Wire Model 与当前能力边界见 [共享契约](contracts.md)。

M1 的独立 Mock Worker、浏览器操作说明与隔离环境启动方式见 [本地产品演示](local-demo.md)。它复用现有 Worker Host 的事件、租约、控制与报告交付，仅替换显式注入的 Runtime factory；普通 Worker 默认路径不变。`AGENT_DEMO_MODE=1` 只公布带标记的 `demo/m1` 模型，并拒绝启动普通模型 Worker。
