# Agent Platform 开发边界

Agent Platform 服务拆分在 `feat/agent-architecture-migration` 分支落地。共享协议位于 `packages/agent-contracts/`；Agent 独立应用、Runtime、Provider、能力、Skills、Workspace、Task/Run API、PostgreSQL Repository、Outbox 和 Worker 位于 `apps/agent/`。本页描述代码归属；双进程和可靠性验收仍需在配置真实数据库与服务后执行。

## 当前所有权

| 区域 | 权威所有者 | 当前实现与边界 |
| --- | --- | --- |
| 共享协议 | `packages/agent-contracts/` | 领域 dataclass 与共享 Pydantic Wire Model；Gateway 与 Agent 路由使用同一组提交、Task、Run、事件和报告结构 |
| 产品 API 与身份 | Backend | `/api/v1/agent/*` 保持产品入口；配置、Task、SSE 事件、控制和文件操作通过 `agent_gateway` |
| Session / Turn / Upload | Backend | 产品对话、附件 owner 权限、用户身份和产品 Timeline 由 Backend 持有；Task/Run 状态通过 Agent API 投影 |
| Agent Execution | Agent | Runtime、Provider 路由、Skills、Workspace、Web/Paper 能力和 Knowledge HTTP Adapter 已迁入 |
| Agent Control / Worker | Agent | 独立数据库迁移、Task/Run/Event/Outbox、领取、Lease/fencing、取消、steer、报告和失败重试已实现 |
| Workspace 与产物 | Agent | 使用共享持久卷和 `AGENT_WORKSPACE_ROOT`；API 与 Worker 必须配置到同一目录 |
| Backend Gateway | Backend | 已实现 Task/Run/Event/Control、配置、文件、Workspace 和匿名认领边界；需要真实网络与恢复场景验收 |

## 当前执行链路

```text
Backend 产品 API / Session 投影
       │
       ▼
Backend AgentGateway ──HTTP──> Agent Internal API
                                  ├── Task/Run + Outbox
                                  ├── PostgreSQL SKIP LOCKED + Worker Lease/fencing
                                  ├── Agent Runtime / Provider / Tools
                                  └── 持久 Run Events / ExecutionReport
```

Backend 通过 `agent-contracts` 校验跨服务请求与响应。Knowledge 仍归 Backend，Agent 通过受服务凭据保护的内部 API 调用。上传附件目前由 Backend 校验 owner、解析并以内联文本随 Task 提交；`input_ref` 尚未启用，Agent 收到非空引用会明确失败。Agent API 与 Worker 必须使用同一个 `AGENT_WORKSPACE_ROOT` 共享持久目录。

Agent 使用独立 `AGENT_DATABASE_URL` 和 `AGENT_SERVICE_TOKEN`。在 `apps/agent` 执行 `uv run alembic upgrade head`，再分别启动 `uv run uvicorn agent_app.main:app ...` 与 `uv run python -m agent_app.worker_main`。

## 后续运维与验收

- Backend 旧 Runtime、Provider、Tool Executor、Worker Executor 与重复的 Agent 专属 LLM/Web 集成已删除；相关模型目录和搜索集成测试归入 Agent。
- `agent_sessions/live.py` 仅作为 Backend 进程内 SSE 订阅缓冲，恢复时从 Agent 持久事件重放，不作为权威事件来源。
- 附件正文仍由 Backend 校验 owner 并以内联文本随 Task 提交；`input_ref` 未启用，Agent 收到非空引用会明确失败。
- Agent API 与 Worker 的共享 Workspace 卷必须在实际部署中指向同一持久目录。
- 真实服务联调需覆盖独立进程、重启恢复、事件重放、Lease fencing、重试、取消、附件、Knowledge、Session 投影与 SSE 重连。本次迁移按用户要求未运行自动化测试或真实服务验收。

Session/Turn 与 Task/Run 的关联规则见 [生命周期](lifecycle.md)，共享 Wire Model 与当前能力边界见 [共享契约](contracts.md)。
