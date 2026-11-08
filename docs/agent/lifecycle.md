# Agent Platform 生命周期与状态

Task/Run 是新平台执行生命周期的权威来源；Session/Turn 只保存产品对话、Transcript、展示事件及必要状态投影。以下是共享契约允许的状态关系，不表示 Control、Scheduler 或数据库状态机已经实现。

## 状态推进

| 阶段 | Task | 当前 Run | 约定 |
| --- | --- | --- | --- |
| 用户提交、排队 | `QUEUED` | 尚无 Run 或 `PENDING` | 每次提交一个 Task；Control 授权预算并创建首个 Run。 |
| Worker 领取并开始执行 | `RUNNING` | `RUNNING` | 领取和租约机制尚未实现；`RunRequest` 是交给 Worker 的执行输入。 |
| 运行成功 | `COMPLETED` | `COMPLETED` | Runtime 结果归档后，Task 可结束。 |
| 本次运行失败 | 根据重试决策保持活动或 `FAILED` | `FAILED` | 失败的 Run 和报告永久保留；重试不能覆盖它。 |
| 本次运行超时 | 根据后续策略决定 | `TIMED_OUT` | Task 没有单独的超时状态；终态投影与重试策略待定。 |
| 请求取消 | `CANCELLING` | 仍是当前状态 | `TaskManager.request_cancel` 记录意图，`Dispatcher.request_cancel(task_id, run_id)` 通知当前 Run。 |
| Runtime 确认取消 | `CANCELLED`（若 Task 结束） | `CANCELLED` | `WorkerExecutor.request_cancel` 只发停止信号；最终以执行报告为准。 |
| 重试 | 按 Control 策略重新排队 | 新 Run 为 `PENDING` | 同一 Task 创建新 `run_id`，attempt 递增；旧 Run 的结果和事件不变。 |
| 等待用户输入 | `AWAITING_INPUT` | `AWAITING_INPUT` | 本次 Runtime 尝试已交出问题；续接方式待定。 |

`TaskStatus.PAUSED` 已在契约中保留，`TaskManager.pause/resume` 已定义，但没有冻结具体暂停、续接或 Run 归属行为。`TaskRecord.current_run_id` 仅指向当前尝试，不能据此删除或改写历史 Run。

## Runtime 终止原因到 Run 状态

`report_from_result` 按现有 `RunResult.status` 转换；`RunResult` 是 Runtime 原始结果来源。

| `StopReason` | `RunStatus` |
| --- | --- |
| `STOP`、`LENGTH` | `COMPLETED` |
| `ERROR`、`MAX_TURNS`、`TOOL_CALLS` | `FAILED` |
| `TIMEOUT` | `TIMED_OUT` |
| `CANCELLED` | `CANCELLED` |
| `AWAITING_INPUT` | `AWAITING_INPUT` |

`TOOL_CALLS` 在 Runtime 注释中不是预期终态；若 Runtime 仍以此结束，现有 `RunResult.status` 将其归为失败。Task 的失败、超时和取消投影应在 Control 结束或重试决策后写入，不能把一次 Run 失败自动当成整个 Task 失败。

## 现有 Session/Turn 与待确认事项

当前 `agent_sessions` Repository 负责 Session/Turn 的创建、幂等键、对话正文、事件展示、Transcript 和 Turn 的持久化。PostgreSQL 中 `agent_turns` 已有 `worker_id`、`lease_expires_at`，运行中 Turn 由现有心跳续租，过期后按既有规则恢复；Memory Repository 只提供进程内行为。新 Task/Run 契约中的 `session_id`、`turn_id` 是关联键，尚未写入现有表，也没有 Task/Run 数据库表或 Run 租约。现有 Session API 的运行状态不能被误写成新平台已接管。

后续需由双方与负责人确认：

1. `pause/resume` 是暂停当前 Run、终止后新建 Run，还是只控制排队；何时允许调用。
2. `AWAITING_INPUT` 后用户回答如何形成新 Task/Turn，以及原 Task 何时结束。
3. Worker 丢失、Run Lease 过期后的领取、重试与旧 Worker 晚到报告的处理规则。
4. Run Lease 与现有 Session/Turn Worker Lease 的一致性与恢复顺序。
5. 取消与完成同时到达时的胜出规则、排队中取消，以及超时后 Task 的最终投影和重试政策。
