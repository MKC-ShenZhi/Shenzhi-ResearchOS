# Agent Platform 开发边界

Agent Platform 服务拆分在 `feat/agent-architecture-migration` 分支落地。共享协议位于 `packages/agent-contracts/`；Agent 独立应用、Runtime、Provider、能力、Skills、Workspace、Task/Run API、PostgreSQL Repository、Outbox 和 Worker 位于 `apps/agent/`。本页描述代码归属；双进程和可靠性验收仍需在配置真实数据库与服务后执行。

## 当前所有权

| 区域 | 权威所有者 | 当前实现与边界 |
| --- | --- | --- |
| 共享协议 | `packages/agent-contracts/` | 领域 dataclass 与共享 Pydantic Wire Model；Gateway 与 Agent 路由使用同一组提交、Task、Run、事件和报告结构 |
| 产品 API 与身份 | Backend | `/api/v1/agent/*` 保持产品入口；新任务提交统一走 V2 执行网关，配置、Workspace 与文件操作继续使用 V1 受信内部接口，排空期旧 Run 的查询与控制保留 V1 兜底 |
| Session / Turn / Upload | Backend | 产品对话、附件 owner 权限、用户身份和产品 Timeline 由 Backend 持有；Task/Run 状态通过 Agent API 投影 |
| Agent Execution | Agent | Runtime、Provider 路由、Skills、Workspace、Web/Paper 能力和 Knowledge HTTP Adapter 已迁入 |
| Agent Control / Worker | Agent | 独立数据库迁移、Task/Run/Event/Outbox、领取、Lease/fencing、取消、steer、报告和失败重试已实现 |
| Workspace 与产物 | Agent | 使用共享持久卷和 `AGENT_WORKSPACE_ROOT`；API 与 Worker 必须配置到同一目录 |
| Backend Gateway | Backend | 新任务统一经 V2 执行网关提交；V1 保留存量排空的查询、事件与控制，以及配置、Workspace、文件和匿名认领边界；需要真实网络与恢复场景验收 |

## 当前执行链路

```text
Backend 产品 API / Session 投影
       │
       ├── 新任务 ──V2 网关──> Agent /internal/v2/*（提交、事件、控制、报告）
       ├── 排空期旧任务 ──V1 网关──> Agent /internal/v1/*（查询、事件、控制）
       └── 共享能力 ──V1 受信内部接口（config / workspace / file / claim）
                                      │
                                      ├── PostgreSQL SKIP LOCKED + Worker Lease/fencing
                                      ├── Agent Runtime / Provider / Tools
                                      └── 持久 Run Events / ExecutionReport
```

Backend 通过 `agent-contracts` 校验跨服务请求与响应。新提交不再按 Owner 类型选择协议：产品 API 入口固定使用 V2 执行网关；Session Turn 以持久 `_agent_protocol` 选择恢复 Gateway，Run 列表、状态、事件与用量读取沿用同一 Gateway。Stop/Steer 先查 V2，且仅在明确 404 时回落 V1；凭据缺失、网络错误和其他响应错误直接返回，不能把 V2 故障猜成旧 Run。Session 文件/产物读取继续走共享 V1 文件端点，并使用 `AGENT_SERVICE_TOKEN`；V2 Gateway 对继承的 V1 共享能力显式委托给 Service Gateway，`AGENT_GATEWAY_TOKEN` 只发往 V2 Gateway 角色接口。V2 准入、角色凭据与新 Worker 由部署配置启用（`AGENT_V2_ADMISSION`、`AGENT_WORKER_PROTOCOL`、`AGENT_V1_ADMISSION`）。Knowledge 仍归 Backend，Agent 通过受服务凭据保护的内部 API 调用。上传附件目前由 Backend 校验 owner、解析并以内联文本随 Task 提交；`input_ref` 尚未启用，Agent 收到非空引用会明确失败。Agent API 与 Worker 必须使用同一个 `AGENT_WORKSPACE_ROOT` 共享持久目录。

正式 V2 授权提交要求 Agent `AGENT_V1_ADMISSION=drain_only`；该开关拒绝新的 V1 Task，但保留 V1 Worker 领取已有 V1 Task 的能力。Agent V2 Worker 只领取已绑定的 V2 Task，V1 Worker 不领取任何带 V2 metering profile 的 Task。Backend V2 提交准入和 Agent V1 drain 开关需协调切换：Agent 尚未进入 drain-only 时，正式 V2 提交返回 403；Agent 先进入 drain-only 时，仍指向 V1 的 Backend 会收到 409。部署编排应把这两个开关作为同一切换窗口处理，V1 Worker 保持运行直至存量排空。

Agent 使用独立 `AGENT_DATABASE_URL` 和 `AGENT_SERVICE_TOKEN`。在 `apps/agent` 执行 `uv run alembic upgrade head`，再分别启动 `uv run uvicorn agent_app.main:app ...` 与 `uv run python -m agent_app.worker_main`。

## 后续运维与验收

- Backend 旧 Runtime、Provider、Tool Executor、Worker Executor 与重复的 Agent 专属 LLM/Web 集成已删除；相关模型目录和搜索集成测试归入 Agent。
- `agent_sessions/live.py` 仅作为 Backend 进程内 SSE 订阅缓冲，恢复时从 Agent 持久事件重放，不作为权威事件来源。
- 附件正文仍由 Backend 校验 owner 并以内联文本随 Task 提交；`input_ref` 未启用，Agent 收到非空引用会明确失败。
- Agent API 与 Worker 的共享 Workspace 卷必须在实际部署中指向同一持久目录。
- 真实服务联调需覆盖独立进程、重启恢复、事件重放、Lease fencing、重试、取消、附件、Knowledge、Session 投影与 SSE 重连。本次迁移按用户要求未运行自动化测试或真实服务验收。

Session/Turn 与 Task/Run 的关联规则见 [生命周期](lifecycle.md)，共享 Wire Model 与当前能力边界见 [共享契约](contracts.md)。

M1 的独立 Mock Worker、浏览器操作说明与隔离环境启动方式见 [本地产品演示](local-demo.md)。它复用现有 Worker Host 的事件、租约、控制与报告交付，仅替换显式注入的 Runtime factory；普通 Worker 默认路径不变。`AGENT_DEMO_MODE=1` 只公布带标记的 `demo/m1` 模型，并拒绝启动普通模型 Worker。
