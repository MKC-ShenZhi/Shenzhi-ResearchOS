# ShenZhi Agent Platform

独立 Agent 服务。Backend 通过 `agent_gateway` 使用 `agent-contracts` 定义的内部协议；Task、Run、事件、配置、Workspace 文件与 Knowledge Adapter 都由共享 Wire Model 校验。Agent PostgreSQL 持有 Task、Run、事件、Outbox 和 Worker Lease。

## 本地运行

```powershell
cd apps/agent
uv sync
```

模型供应商通常只需在 `.env` 填写对应 API Key；型号、能力和默认顺序由 Catalog 维护。
内置白名单、旧变量迁移、OpenLux 实测状态与正式授权步骤见 [Model Provider 指南](../../docs/engineering/llm-api-foundation.md)。
启动 API、Worker 时需显式加载同一 `.env`（例如 `uv run --env-file .env ...`）。仅配置 Key 不自动获得正式 Policy 授权。

Agent API 与 Worker 必须挂载同一个持久化/共享目录并配置 `AGENT_WORKSPACE_ROOT`，否则跨进程与重启后的工作区产物不可见。

启动 Agent API 与 Worker 两个进程前，设置独立数据库和服务凭据并应用迁移：

```powershell
$env:AGENT_DATABASE_URL = 'postgresql+asyncpg://<user>:<password>@<host>/<agent_db>'
$env:AGENT_SERVICE_TOKEN = '<long-random-service-token>'
$env:AGENT_WORKSPACE_ROOT = 'D:\\shenzhi-agent-workspace'
uv run alembic upgrade head
uv run uvicorn agent_app.main:app --host 127.0.0.1 --port 8101
```

在另一个终端启动 Worker：

```powershell
cd apps/agent
$env:AGENT_DATABASE_URL = 'postgresql+asyncpg://<user>:<password>@<host>/<agent_db>'
$env:AGENT_SERVICE_TOKEN = '<long-random-service-token>'
$env:AGENT_WORKSPACE_ROOT = 'D:\\shenzhi-agent-workspace'
uv run python -m agent_app.worker_main
```

Agent V2 内部 API 按调用角色使用隔离的 Bearer 凭据：Backend Gateway、Service 能力、Worker、Fact Reader 各用其专属凭据；Task/Run/Event/Control 数据不会写入 Backend 数据库。Knowledge Tools 通过受服务凭据保护的 Backend Platform Adapter 调用；附件正文由 Backend 校验后随 Task 提交，`input_ref` 尚未启用。
