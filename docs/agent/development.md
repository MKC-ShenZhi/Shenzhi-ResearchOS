# Agent Platform 并行开发边界

两位开发者从 `feat/agent-platform` 共享契约基线分别开展 `feat/agent-control` 与 `feat/agent-execution`。本轮只冻结共享接口；未创建子分支，也未接入新 Task API、Redis 队列或 Task/Run 数据库表。

## 代码所有权

| 区域 | 主要负责内容 | 当前路径与状态 |
| --- | --- | --- |
| 共享契约 | Task/Run、预算、事件、Protocol；变更须双方同步 | `apps/backend/app/services/agent_contracts/` 已存在 |
| Control | 基于现有身份的任务权限与配额、Task Manager、Budget Manager、并发控制、Dispatcher、Scheduler、Redis Queue、PostgreSQL Task/Run 持久化、任务 API | 后续拟在 `services/agent_control/`、`services/agent_scheduler/`、`integrations/redis/`、`models/agent_task.py`、`models/agent_run.py`、`api/agent_tasks.py` 实现；这些路径目前不存在 |
| Execution | Planner、Executor、Runtime、State Manager、Tool Registry、Budget Guard、知识/工具/模型 Adapter、WorkerExecutor | `services/agent/`、`services/agent_workers/`、`integrations/llm/`、`integrations/paper_resource/`、`integrations/public_web/`、`integrations/web_search/` 已有相关实现，完整平台 Worker 尚未实现 |
| 协调区域 | Session/Turn 与 Task/Run 的关联、数据库迁移、共享接口、现有 Agent API 兼容 | `services/agent_sessions/`、`models/agent_session.py`、`api/agent.py` 及 migrations；任何一侧不能单独改变其执行状态语义 |

这里的 Control “User Manager”指在 `app.core.identity` 已有身份之上实现任务授权、配额和并发规则，不是第二套用户认证或用户表。现有 Session/Turn Repository 继续管理产品对话和 Transcript；新平台 Task/Run 负责执行状态。

## 双侧接入顺序

Control 侧从 `TaskSubmission` 创建 Task 和独立 Run，记录 attempt 与 `current_run_id`，经 `BudgetManager` 授权并通过 `Dispatcher` 提交 `RunRequest`。Control 实现 `EventSink`、`RunReporter` 的接收和持久化，按 `run_id` 保留报告、按 `(run_id, seq)` 保留事件。Session 任务创建前须协调同一个 `session_id`、`turn_id` 的持久关联；不要把既有 Turn 状态作为另一份执行真相。

Execution 侧消费 `RunRequest`，包装并有序发布 Runtime `AgentEvent`，完成发布后返回 `ExecutionReport`。进程内 Worker 支持无 Session 的显式时长和工具次数预算；模型 Token 限制与 Session-bound 执行仍拒绝。

独立 Fake 契约测试入口是 `apps/backend/tests/test_agent_contracts.py`，命令为 `uv run python -m unittest -q tests.test_agent_contracts`。双方变更共享契约时应同步测试和文档，并保持 `api/agent.py` 的既有路由与 HTTP 方法兼容。Run 租约恢复、等待输入续接和暂停/恢复的待确认规则见 [生命周期](lifecycle.md)。

V1 已接通进程内事件发布、显式时长与工具次数限制以及真实用量报告边界。Execution 后续补模型 token 预扣与 Provider 用量完整性、事件传输重试和 Worker Host；Control 后续实现 `RunReporter → TaskManager.record_report` 唯一入口、事务幂等结算、Run Lease/fencing 与状态机。运行中暂停、自动等待输入续接、Session-bound 平台执行仍不支持。具体冻结规则见 [生命周期](lifecycle.md)。
