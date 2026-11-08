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

`TaskRecord.current_run_id` 只指向当前尝试；每次重试分配新的 `run_id` 和从 1 递增的 `attempt`，历史 Run、事件、报告不可覆盖。

## V1 状态转换约束（Control 待实现）

| 当前 Task / Run | 操作与执行主体 | 允许的结果 | 拒绝或竞争规则 |
| --- | --- | --- | --- |
| `QUEUED` / 无或 `PENDING` | Control pause | `PAUSED` / 原 Run 不执行 | 已领取则条件更新失败，不能假装暂停 |
| `PAUSED` / `PENDING` | Control resume | `QUEUED` / 原 Run 待领取 | 不恢复已运行的 Run |
| `QUEUED` / `PENDING` | Worker 原子领取 | `RUNNING` / `RUNNING` | 与 pause、cancel 竞争，只有一个条件更新胜出 |
| `RUNNING` / `RUNNING` | Control pause | 不变，明确业务错误 | V1 无运行中 checkpoint 暂停 |
| `QUEUED` 或 `RUNNING` / 非终态 | Control request_cancel | `CANCELLING`，通知 Worker | 仅记录意图，不宣称已取消 |
| `CANCELLING` / `RUNNING` | Worker 报告，经 Control 原子处理 | `CANCELLED`、`COMPLETED`、`FAILED` 或按重试策略排队 | 以实际报告决定；终态不得再取消 |
| `RUNNING` / `RUNNING` | Worker 报告 `AWAITING_INPUT` | `AWAITING_INPUT` / `AWAITING_INPUT` | Run 终态，不能重复执行或复用 ID |
| `RUNNING` / `RUNNING` | Worker 报告超时 | `FAILED` 或按策略 `QUEUED` / `TIMED_OUT` | 保留原 Run，重试建新 Run |
| `RUNNING` / `RUNNING` | Worker 报告失败 | `FAILED` 或按策略 `QUEUED` / `FAILED` | 一次失败不自动等于 Task 失败 |
| 任意 / 终态 | 迟到或重复报告 | 相同报告幂等返回 | 冲突报告拒绝；旧 Run 不改当前 Task |

这些规则已冻结为接口约定；本分支没有 Task/Run 数据库状态机。Control 必须在一个事务中校验 `task_id/run_id/current_run_id`、写报告、更新状态并只结算一次用量。唯一 `run_id` 和报告约束、条件更新及租约 fencing token 不能由进程内字典代替。

## 等待输入与会话关联决策

现有 `AgentTurnRow` 属于一个 Session，包含一次用户内容、执行状态、问题和 Transcript；它没有跨多个用户 Turn 的 Task 关联。V1 推荐 A：每次用户提交一个 Task，后续回答创建新 Turn 和新 Task，并以 continuation 关联前一个 Task。B（一个 Task 跨多个 Turn）需要 `TaskTurn` 关联表、重定义当前 Run 与权限/幂等边界，超出本轮。推荐方案待负责人确认；自动续接暂不支持。

现有 Session API 继续用 `agent_turns.worker_id/lease_expires_at` 的 Turn Lease。新平台 Run Lease 由 Control 后续实现，必须有过期时间、续租、过期识别和 fencing token；同一次执行只允许一套 Lease 决定所有权。新平台未接管 Session 执行前不得删除 Turn Lease。迟到 Worker 报告不能覆盖新 Run 的结果。

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

后续需确认具体的重试次数、失败与超时后的 Task 最终投影、continuation 数据结构和 Session 执行迁移顺序。
