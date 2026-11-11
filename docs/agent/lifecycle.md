# Agent Platform 生命周期与状态

Task/Run 是 Agent 执行生命周期的权威来源；Session/Turn 只保存产品对话、Transcript、展示事件及必要状态投影。Agent PostgreSQL 持久化 Task/Run/事件/Outbox 与 Worker Lease。Backend Gateway 已把 Agent Task/Run/持久事件投影到产品 Session/Turn；本页记录静态代码边界，不表示独立进程恢复和重连已经验收。

## 状态推进

| 阶段 | Task | 当前 Run | 约定 |
| --- | --- | --- | --- |
| 用户提交、排队 | `QUEUED` | 尚无 Run 或 `PENDING` | 每次提交一个 Task；Control 授权预算并创建首个 Run。 |
| Worker 领取并开始执行 | `RUNNING` | `RUNNING` | Worker 以 `FOR UPDATE SKIP LOCKED` 领取，租约续期并递增 fencing token。 |
| 运行成功 | `COMPLETED` | `COMPLETED` | Runtime 结果归档后，Task 可结束。 |
| 本次运行失败 | `QUEUED`（attempt < 3）或 `FAILED` | `FAILED` | 保留旧 Run/报告；重试新建 Run 并指数退避。 |
| 本次运行超时 | `QUEUED`（attempt < 3）或 `FAILED` | `TIMED_OUT` | Task 没有单独超时状态；最多 3 次后投影为 FAILED。 |
| 请求取消 | `CANCELLING` | 仍是当前状态 | `TaskManager.request_cancel` 记录意图，`Dispatcher.request_cancel(task_id, run_id)` 通知当前 Run。 |
| Runtime 确认取消 | `CANCELLED`（若 Task 结束） | `CANCELLED` | `WorkerExecutor.request_cancel` 只发停止信号；最终以执行报告为准。 |
| 重试 | 按 Control 策略重新排队 | 新 Run 为 `PENDING` | 同一 Task 创建新 `run_id`，attempt 递增；旧 Run 的结果和事件不变。 |
| 等待用户输入 | `AWAITING_INPUT` | `AWAITING_INPUT` | 本次 Runtime 尝试已交出问题；续接方式待定。 |

`TaskRecord.current_run_id` 只指向当前尝试；每次重试分配新的 `run_id` 和从 1 递增的 `attempt`，历史 Run、事件、报告不可覆盖。

## V1 状态转换约束

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

Task/Run 报告更新、`current_run_id` 校验和新 Run/Outbox 创建在一个事务内执行。当前数据库以唯一约束确保 `(task_id, attempt)`、`(run_id, seq)` 唯一；报告采用同 Run 的幂等相等比较，冲突报告被拒绝。并发行为仍需后续专门可靠性验证。

## 等待输入与会话关联决策

现有 `AgentTurnRow` 属于一个 Session，包含一次用户内容、执行状态、问题和 Transcript；它没有跨多个用户 Turn 的 Task 关联。按本阶段冻结规则，每次用户提交创建一个 Task；用户在 `awaiting_input` 后回答时，创建新 Turn 和新 Task。一个 Task 只关联一个 Turn，不实现一个 Task 跨多个 Turn 的续接模型。

Backend Session 投影仍使用 `agent_turns.worker_id/lease_expires_at` 协调哪个 Backend 实例负责把 Agent 持久状态写回产品 Turn；Agent Worker 使用独立 Run Lease 与 fencing token。该 Turn Lease 是产品投影租约，不是 Agent 执行租约。只有确认投影恢复不再依赖后，才可通过新的 Backend 数据库迁移移除其字段；历史迁移保持不变。

## Runtime 终止原因到 Run 状态

Agent Worker 将 `RunResult.status` 映射为共享 `ExecutionReport`，再由 Agent Control 原子更新 Run 与 Task；Runtime 原始对象不越过服务边界。

| `StopReason` | `RunStatus` |
| --- | --- |
| `STOP`、`LENGTH` | `COMPLETED` |
| `ERROR`、`MAX_TURNS`、`TOOL_CALLS` | `FAILED` |
| `TIMEOUT` | `TIMED_OUT` |
| `CANCELLED` | `CANCELLED` |
| `AWAITING_INPUT` | `AWAITING_INPUT` |

`TOOL_CALLS` 在 Runtime 注释中不是预期终态；若 Runtime 仍以此结束，现有 `RunResult.status` 将其归为失败。Task 的失败、超时和取消投影应在 Control 结束或重试决策后写入，不能把一次 Run 失败自动当成整个 Task 失败。

## 现有 Session/Turn 与待确认事项

`agent_sessions` Repository 仍负责 Backend Session/Turn；Agent Task 记录 `session_id`、`turn_id` 作为关联键，不访问 Backend 数据库。Agent Task/Run/Event/Outbox 表与 Run Lease 已有独立迁移。现有 Session API 的运行状态不能被误写成新平台已接管。

V1 的失败与超时最多尝试 3 次，重试创建新的 Run 并按指数退避；`awaiting_input` 后由 Backend 创建新的 Turn 与 Task。代码路径已按上述规则实现，真实数据库竞争、Worker 重启和多实例故障场景尚未在本次迁移中执行验收。
