# Agent Platform 开发边界

当前分支将 Agent 执行通信统一为 V2。Backend 产品 API 只注册 `/api/v2/agent/*`，Backend Gateway、Agent API 和 Worker 均只使用 `/internal/v2/*`。Backend 产品 API 位于 `app/api/agent.py`，权益、计量及内部控制接口位于 `app/api/agent_control.py`；唯一 Gateway 位于 `app/services/agent_gateway/gateway.py`；Agent 内部路由位于 `agent_app/api/routes.py`。这些文件按职责命名，HTTP 路径与 V2 wire 契约保持不变。V1 HTTP router、Backend V1 Gateway adapter、Worker V1 分支和基于 V1 的 M1 Mock 启动器已从当前实现移除。历史数据库数据保留，不执行数据清理或迁移删除。

## 当前所有权

| 区域 | 权威所有者 | 当前实现与边界 |
| --- | --- | --- |
| 共享协议 | `packages/agent-contracts/` | 领域 dataclass 与共享 Pydantic Wire Model；V2 提交、Task、Run、事件、计量与报告结构 |
| 产品 API 与身份 | Backend | `/api/v2/agent/*` 是唯一 Agent 产品 BFF 路径；Session run 保持 SSE 契约，独立 Task JSON 使用 `/submissions` |
| Session / Turn / Upload | Backend | 产品对话、附件 owner 权限、身份和产品 Timeline 由 Backend 持有；Agent 状态通过 V2 API 投影 |
| Agent Execution | Agent | Runtime、Provider 路由、Skills、Workspace、Web/Paper 能力和 Knowledge HTTP Adapter |
| Agent Control / Worker | Agent | 独立数据库中的 Task/Run/Event/Outbox、V2 领取、Lease/fencing、取消、steer、报告、重试和 metering |
| Backend Gateway | Backend | 所有执行和共享能力通信走 V2；V2 准入由 `AGENT_V2_ADMISSION` 与签名 Grant 控制 |

## 当前执行链路

```text
Backend 产品 API / Session 投影
       ├── 执行与控制 ──V2 Gateway──> Agent /internal/v2/*
       ├── 配置、Workspace、文件 ──V2 Service Gateway──> Agent /internal/v2/*
       └── Knowledge ──Service Adapter──> Backend Knowledge API
                                      │
                                      ├── PostgreSQL SKIP LOCKED + Worker Lease/fencing
                                      ├── Agent Runtime / Provider / Tools
                                      └── 持久 Run Events / ExecutionReport / Usage Facts
```

Agent Repository 只创建携带 metering envelope 的 Task，Worker 只领取已绑定且未撤销的计量 Task。Session Turn 持久 `_agent_protocol` 仅用于识别旧历史数据。新 Turn 固定写入 V2 标记；终态旧 Turn 从 Backend 已持久化的产品投影重放，未终态旧 Turn 不会回调任何 Agent 执行 API。过期的旧协议运行由 Backend Session Repository 收敛为失败状态。Agent API 与 Worker 必须使用同一持久 `AGENT_WORKSPACE_ROOT`。

## 退役审计与部署证据

源代码移除 V1 不会证明部署环境已没有旧实例或外部调用方。发布后仍应从 Backend 与 Agent 的**只读** PostgreSQL 对照运行：

```powershell
$env:AGENT_DATABASE_URL = '<只读 Agent PostgreSQL URL>'
$env:CHAT_DATABASE_URL = '<只读 Backend PostgreSQL URL>'
uv run --project apps/backend --frozen --no-sync python scripts/agent_v1_drain_audit.py
```

审计脚本只读统计 V1 Task/Run、活跃旧 Session Turn 与历史引用；不输出 DSN、Owner 或记录 ID。数据库侧清零仍不证明外部调用方已迁移，需另外检索入口代理、Backend、Agent API 日志，覆盖已知重试周期、后台周期与发布窗口。脚本将 `external_v1_callers_verified` 和 `v1_retirement_proven` 保持为 `false`，不得据此单独宣称生产切换验收完成。不要删除历史 Task、Run、Turn 或事件来让计数归零。

完整双库审计、生产部署日志和真实 V2 Worker/数据库联调尚未在本地环境验证；它们是运行环境验收项，不再作为保留 V1 源码或运行时分支的理由。

## 后续验收

- 本地自动化验证覆盖 Agent V2 API/Worker、Backend V2 Gateway 与产品 Session/SSE 路径。
- 真实服务验收需使用隔离 Backend/Agent PostgreSQL，覆盖双进程启动、重启恢复、事件重放、租约 fencing、重试、取消、附件、Knowledge、计量和 SSE 重连。
- M1 V1 Mock 启动器已退役；当前没有可运行的 V2 Mock 准入 fixture，见 [本地演示状态](local-demo.md)。
- 真正生产退役状态还需结合部署版本、访问日志和只读双库审计确认。
