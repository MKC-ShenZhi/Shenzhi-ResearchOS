# Agent Platform 文件迁移记录

分支：`feat/agent-architecture-migration`。本记录对照 `Agent-Platform架构拆分-Codex执行文档.md`，列出迁移后的代码边界和已删除的 Backend 执行副本。

## 依赖审计与新归属

| 原 Backend 路径 | 迁移后路径 | 处理 |
| --- | --- | --- |
| `app/services/agent/execution/` | `apps/agent/src/agent_app/execution/` | Runtime、消息类型、Provider 抽象、Tools、上下文、压缩和 Checkpoint |
| `app/services/agent/application/` | `apps/agent/src/agent_app/application/` | Agent Runtime 组装、策略与 Facade；调度/取消/steer 由 Agent Worker 与 Control 接管 |
| `app/services/agent/capabilities/` | `apps/agent/src/agent_app/capabilities/` | 用户提问、图表、网页、Knowledge 与论文能力 |
| `app/services/agent/extensions/skills.py`、`prompt_templates.py`、`workspace.py` | `apps/agent/src/agent_app/extensions/` | Skills、Prompt、Workspace 与产物读写 |
| `app/integrations/llm/` | `apps/agent/src/agent_app/integrations/llm/` | 模型目录、路由、凭据和 OpenAI-compatible Provider |
| `app/integrations/public_web/`、`web_search/` | `apps/agent/src/agent_app/integrations/` | SSRF 防护、网页抓取、搜索和图片 Provider |
| `app/integrations/paper_resource/agent_sources.py` | `apps/agent/src/agent_app/integrations/paper_resource/agent_sources.py` | Agent 论文来源候选发现；Backend 产品 PDF Provider 保留 |
| `app/services/agent_workers/executor.py` | `apps/agent/src/agent_app/worker/host.py` | Worker 独立轮询、租约心跳、事件上报、控制接收和执行报告 |
| `app/services/agent_contracts/` | `packages/agent-contracts/src/agent_contracts/` | 共享领域契约和 Pydantic HTTP Wire Model；包含 Task/Run/Event/Report、Knowledge、配置、Workspace 与产物文件 |
| `app/services/agent/cli.py`、`__main__.py` | `apps/agent/src/agent_app/cli.py`、`__main__.py` | 保留独立 CLI 入口并改为 Agent 自有导入 |

Agent 源码及测试未发现 `app.*` Backend 包导入。Agent Knowledge 工具只经 `BackendKnowledgeClient` 调用受服务凭据保护的产品 API；Agent 进程使用独立数据库配置。Backend 对 Agent 的请求均经 `AgentGateway` 和共享 Wire Model。

## Backend 保留范围

- `app/api/agent.py` 与 `app/schemas/agent.py`：前端产品 API、请求/响应兼容和身份校验。
- `app/services/agent_sessions/`、Session/Turn ORM 与历史 Alembic 迁移：产品会话、Transcript、时间线和投影恢复。
- `app/services/agent_uploads.py`、`agent_attachments.py` 与上传解析器：产品附件权限、解析、归属和消费。
- `app/services/agent_gateway/`：Agent 服务间认证、Task/Run/Event/Control、配置、Workspace/产物文件和匿名认领。
- Knowledge API/服务/集成及 `paper_resource/` 产品 PDF Provider：仍由 Backend 持有。
- `core/worker_lease.py`：保留为 Backend Session 投影租约；它不再领取或执行 Agent Run。
- `agent_sessions/live.py`：保留为当前 Backend 进程的 SSE 订阅缓冲；事件恢复以 Agent 持久事件为准。

## Backend 删除范围

删除 `app/services/agent/` 和 `app/services/agent_workers/`，包括旧 Runtime、执行器、Provider、Tool 注册/执行、技能与工作区实现、CLI 及历史兼容转发；删除 `app/integrations/llm/`、`public_web/`、`web_search/` 和 `paper_resource/agent_sources.py`。Backend `core.config.ModelConfig` 随 Agent Provider 迁出而删除。依赖检索确认这些目录没有 Backend 产品代码消费者；公网、模型和 Agent 论文能力已归入 Agent。Backend 依赖同步移除了不再使用的 `lxml`、`matplotlib`。

Session、Turn、Upload 的产品数据没有迁移；`007_agent_sessions.py`、`011_agent_uploads.py` 等历史迁移没有删除或改写。Backend Turn Lease 仍用于 Session 投影互斥，因而保留。

## 测试文件归属

Agent Runtime、Skills、Workspace、Knowledge Tools、论文、模型路由和模型目录测试移至 `apps/agent/tests/unit/`；网页搜索 Provider 测试也归 Agent。Backend API、Gateway、Session 投影、附件与匿名认领测试留在 `apps/backend/tests/`，不再导入 Runtime 或 Agent Workspace 实现。

## 静态核对

- 当前分支为 `feat/agent-architecture-migration`。
- 对 Backend、Agent、共享契约的 273 个 Python 文件执行 AST 语法解析，无语法错误。
- Backend 源码及测试中未发现旧 Runtime、Worker、Agent LLM/Web 集成或 `ModelConfig` 导入；Agent 源码、测试和共享契约中未发现 Backend `app.*` 导入。
- `git diff --check HEAD` 无空白错误；仅有仓库换行符规范提示。
- 按用户要求未运行自动化测试、独立双进程启动或真实数据库/服务验收；以上结果只证明静态文件和代码边界，不代表运行验收通过。
