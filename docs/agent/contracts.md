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

`BudgetLimits` 包含时长、工具次数和模型 Token 限制。Control 授权和结算，Execution 执行并测量。`UsageReport` 用 `None` 表示未知。Runtime 现在记录工具派发次数；模型用量仅在收到每次调用的 Provider usage 时视为已测量。时长与工具次数可由进程内 Worker 强制执行，模型 Token 限制仍拒绝。

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

构造输入不一致时抛出 `ValueError`。Session-bound 执行和模型 Token 显式限制仍在执行前拒绝；时长与工具次数可执行。

## V1 进程内适配现状

`RuntimeDriver.run` 接收同步 `on_event`。`ApplicationWorkerExecutor` 依次排队 Runtime 原始事件，单协程调用异步 `EventSink.publish`，等待已产生事件交付后才返回报告。发布失败停止 Runtime 并抛错；此时不得提交成功报告。接收侧应以 `(run_id, seq)` 唯一约束实现幂等，事件发布与报告交付的跨进程原子性尚未实现。

Worker Host 只调用一次 `RunReporter.report`；Control 适配器在其内部调用 `TaskManager.record_report`，并在同一事务结算 `BudgetManager.record_usage`。相同报告重试幂等成功，冲突报告拒绝；数据库唯一约束、事务和迟到 Worker fencing 留给 Control 实现。

进程内 Worker 已将显式时长限制传给 Runtime 的单调钟 deadline，将显式工具次数限制传到实际工具派发边界，并在严格预算模式阻止收尾工具越额。`RunResult.tool_calls` 记录派发次数，`usage_measured` 标记 Runtime 是否收到每次模型调用用量；未知 token 在报告中为 `None`。模型 token 上限仍无法可靠预先约束，执行前拒绝。Session-bound Run 仍拒绝。当前适配不提供持久化、跨进程恢复或生产级幂等。
