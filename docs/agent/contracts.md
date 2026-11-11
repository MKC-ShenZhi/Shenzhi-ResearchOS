# Agent Platform 共享契约

本页描述 `packages/agent-contracts/src/agent_contracts/` 中 Backend 与 Agent Platform 共用的数据和接口约定。包以 dataclass 表达领域记录，以 Pydantic Wire Model 校验 HTTP 请求与响应；Runtime 类型只存在于 Agent Worker 内部，由 Worker adapter 在进程边界转换。Backend Gateway 已接入产品 Agent API、Session 投影和 Knowledge 内部适配器；本文记录静态代码状态，不替代独立进程或可靠性验收。

## 身份与关联

```text
User → Session → Turn → Task → Run 1 / Run 2 / ...
```

- 一次用户提交创建一个 Task；一个 Task 可有多个执行尝试，每次尝试有新的 `run_id`，`RunRecord.attempt` 从 1 递增。旧 Run、报告和事件按各自 `run_id` 保留，`TaskRecord.current_run_id` 只指向当前尝试。
- Session 包含多个 Turn。会话任务一对一关联一个 Turn，`TaskSubmission.session_id` 与 `turn_id` 必须同时存在；`RunRequest` 复制同一对关联 ID。两字段也可同时为 `None`，表示非会话任务。仅提供其中一个会在构造契约对象时抛出 `ValueError`。
- `TaskRecord.session_id`、`turn_id` 从其 `submission` 读取；`RunRecord.task_id` 从其 `request` 读取。`RunRequest.task_id` 必填；Control 创建 Run 时负责核对 Task 归属、唯一 `run_id` 和递增 attempt。单个 dataclass 无法替代跨记录唯一性约束。
- `owner_id` 采用现有 `app.core.identity.request_owner` 的 `user:<id>` / `anon:<id>` 格式。Control 在这一身份基础上实现任务权限、配额和并发控制。

`TaskSubmission` 保留 `prompt`、`input_ref`、`idempotency_key`；`TaskRecord` 保留 `status`、`created_at`、`cancel_requested` 和 `current_run_id`。`RunRequest` 保留模式、模型、Workspace、Skills、预算和输入引用；`RunRecord` 保存请求快照、attempt、状态、创建/完成时间及错误字段。Session/Turn 的对话内容和 Transcript 仍由既有 `agent_sessions` Repository 保存，不复制为另一套会话记录。

## 执行结果与用量

`WorkerExecutor.execute(RunRequest)` 产生一个 `ExecutionReport`：`task_id`、`run_id`、最终 `RunStatus`、JSON 兼容的结果字典或 `None`、`UsageReport`、`error_code` 与 `error_message`。共享协议不嵌入 Runtime Python 对象。报告不接受 `PENDING` 或 `RUNNING`；`AWAITING_INPUT` 表示本次 Runtime 尝试已停止并交出问题，不表示 Task 已完成。

Agent Worker 的报告适配器负责把 Runtime `RunResult` 转换为 JSON 兼容报告字典，并映射错误和测得用量。Agent Runtime 的消息、最终文本和产物以字典字段表达。Control 在单一数据库事务内写报告、更新 Run/Task 状态并决定重试；失败或超时最多执行 3 次，使用新 `run_id` 和指数退避。用量结算尚未接入 Backend 配额服务。

`BudgetLimits` 包含时长、工具次数和模型 Token 限制。Worker 按模式设置默认时长与工具次数，并可执行更严格的显式上限。`UsageReport` 用 `None` 表示未知；模型 Token 上限当前无法可靠预先强制，带该限制的 Run 会失败并返回明确执行错误。

## 事件

Runtime `AgentEvent(seq, turn, name, data)` 是事件来源。Worker 边界将字段复制为 `PlatformEvent(task_id, run_id, seq, turn, name, data, occurred_at)`，交给 Control 的 `EventSink.publish`；共享协议不携带 Runtime 类实例。这里 `turn` 是 Runtime 内部轮序号，不是产品 `turn_id`。

`seq` 在单个 Run 内排序；`PlatformEvent.sequence` 与 `seq` 相同。事件标识为 `PlatformEvent.event_key == (run_id, seq)`，数据库对 `(run_id, seq)` 建唯一约束；相同事件重放幂等，冲突事件拒绝。`PlatformEventWire` 与 `EventIngestWire` 是共享 HTTP envelope，`GET /internal/v1/runs/{run_id}/events?owner_id=...&after_seq=...` 提供持久事件读取。Backend Gateway 校验提交、Task、Run 与事件响应，再将持久事件投影到产品 SSE。

Agent Knowledge Adapter 使用共享 `KnowledgeSearchRequestWire`、`KnowledgeSearchResponseWire`、`KnowledgePaperDetailWire` 与 `KnowledgePaperGraphWire`。Backend 保留产品 Knowledge Schema 和上游实现，在内部 API 边界映射到共享 Wire Model；Agent 不安装或导入 Backend Python 包。

## Protocol 边界

所有接口均为 `async` Protocol，只依赖共享契约类型，不依赖 Control 或 Execution 的具体类。

| Protocol | 负责侧 | 方法与结果 |
| --- | --- | --- |
| `TaskManager` | Control | `submit → TaskRecord`、`get → TaskRecord`、`create_run → RunRequest`、`pause/resume/request_cancel → TaskRecord`、`record_report → TaskRecord`、`get_report → ExecutionReport \| None` |
| `BudgetManager` | Control | `authorize(TaskRecord) → BudgetLimits`、`record_usage(ExecutionReport) → None` |
| `Dispatcher` | Control / Scheduler 边界 | `submit(RunRequest) → None`、`request_cancel(task_id, run_id) → None` |
| `WorkerExecutor` | Execution | `execute(RunRequest) → ExecutionReport`、`request_cancel(run_id) → None` |
| `EventSink` | Control 接收边界 | `publish(PlatformEvent) → None` |
| `RunReporter` | Execution 到 Control 的报告边界 | `report(ExecutionReport) → None` |

构造输入不一致时抛出 `ValueError`。Session-bound 执行和模型 Token 显式限制仍在执行前拒绝；时长与工具次数可执行。

## V1 Agent API 与 Worker 现状

任务提交会在同一事务创建 Task、首个 pending Run 和 Outbox 记录；Worker 使用 PostgreSQL `FOR UPDATE SKIP LOCKED` 领取 pending Run。领取、心跳、事件和报告均携带递增 fencing token；租约过期后可以重新领取，旧 Worker 的事件和报告会被拒绝。Runtime 事件先写入 Agent Event Store，写入失败时 Worker 不会提交成功报告。Backend `AgentGateway` 使用共享 Wire Model 校验产品边界的数据。

相同报告重试幂等成功，冲突报告拒绝；Task、Run、报告、重试 Run 与 Outbox 更新由数据库事务协调。运行中 steer 经持久 Control 记录传给 Worker；Backend Knowledge Adapter 已调用 Backend 内部 API。暂停和产品配额结算尚未实现。

Worker 通过独立进程入口运行；`AGENT_DATABASE_URL` 与 `AGENT_SERVICE_TOKEN` 均归 Agent 运行环境。Backend 上传附件会先做 owner 校验与解析，再把受限文本上下文随 Task 提交；`input_ref` 尚未启用，Agent 收到非空引用会明确失败。Agent API 与 Worker 需挂载同一个 `AGENT_WORKSPACE_ROOT` 持久共享目录，Workspace 文件通过 owner 与工作区 ID 重新定位；该共享卷配置属于运行前置条件。当前交付尚未完成真实双进程 E2E 验收。
