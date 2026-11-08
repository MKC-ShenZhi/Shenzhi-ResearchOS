# Agent Platform 共享契约

本页描述 `apps/backend/app/services/agent_contracts/` 的当前数据与接口约定，供 `feat/agent-control` 和 `feat/agent-execution` 共同依赖。类型沿用仓库现有的 Python dataclass、`AgentEvent` 和 `RunResult`，不另建平台 Runtime 结果或事件类型。当前只有契约和进程内 Worker 适配器，没有 Task/Run 数据库实现。

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

`WorkerExecutor.execute(RunRequest)` 产生一个 `ExecutionReport`：`task_id`、`run_id`、最终 `RunStatus`、原始 `RunResult | None`、`UsageReport`、`error_code` 与 `error_message`。报告不接受 `PENDING` 或 `RUNNING`；`AWAITING_INPUT` 表示本次 Runtime 尝试已停止并交出问题，不表示 Task 已完成。

现有 `report_from_result` 负责把 Runtime `RunResult.status`、错误和测得用量转换为平台报告，同时原样保留 `RunResult`。Runtime 原始消息、最终文本和产物由 `RunResult` 表达。Execution 侧生成报告并经 `RunReporter.report` 交给 Control；Control 负责按 `run_id` 持久保存结果，`TaskManager.record_report` 负责相应的 Task/Run 状态处理，`TaskManager.get_report(run_id, owner_id)` 提供带 owner 限制的读取。持久化与状态更新如何在同一事务内协调，留待 Control 实现；当前 Fake 测试只验证接口交互。

`BudgetLimits` 只有 `max_duration_s`、`max_tool_calls`、`max_model_tokens`。`BudgetManager.authorize` 由 Control 授权限制，Execution 侧在运行期间执行限制并报告 `UsageReport`，`BudgetManager.record_usage` 由 Control 结算。`UsageReport` 的 `prompt_tokens`、`completion_tokens`、`tool_calls`、`duration_ms` 均允许 `None` 表示未知；已知的 0 才写 0。只要任一模型 token 数未知，`model_tokens` 也为 `None`。当前 Runtime `RunResult` 没有可靠的工具调用计数，因此 `report_from_result` 保留 `tool_calls=None`；其余三个数字直接取 Runtime 报告值。Runtime 现有数值字段的默认 0 无法区分未测量与真实零，后续接入用量来源时必须解决这一测量边界。显式平台预算在现有 `ApplicationWorkerExecutor` 中仍未接通，不能宣称强制执行或生产级计费。

## 事件

Runtime `AgentEvent(seq, turn, name, data)` 是事件来源。Execution 侧把每条 Runtime 事件封入 `PlatformEvent(task_id, run_id, runtime_event, occurred_at)`，交给 Control 的 `EventSink.publish`；不得另造平行事件流。这里 `AgentEvent.turn` 是 Runtime 内部轮序号，不是产品 `turn_id`。

`seq` 在单个 Run 内排序；`PlatformEvent.seq` 和现有 `sequence` 均读取原始事件的 `seq`。事件标识为 `PlatformEvent.event_key == (run_id, seq)`，用于重复识别；不同 Run 可以使用同一 `seq`。接收端应按 `seq` 对单 Run 事件排序，并在持久化时保留 `task_id`、`run_id`、`seq`、Runtime 事件的 `turn/name/data` 与 `occurred_at`，以便后续按 Run 重放及 SSE 断线续接。平台事件存储、冲突处理和跨进程重放尚未实现。

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

构造输入不一致时数据契约抛出 `ValueError`；运行失败以终态 `ExecutionReport` 表达。取消请求通过 Dispatcher/WorkerExecutor 传递，最终是否取消以报告为准。当前适配器对尚不支持的会话运行和显式预算抛出 `NotImplementedError`，不会返回虚假的成功报告。
