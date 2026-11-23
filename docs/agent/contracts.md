# Agent Platform 共享契约

本页描述 `packages/agent-contracts/src/agent_contracts/` 中 Backend 与 Agent Platform 共用的数据和接口约定。包以 dataclass 表达领域记录，以 Pydantic Wire Model 校验 HTTP 请求与响应；Runtime 类型只存在于 Agent Worker 内部，由 Worker adapter 在进程边界转换。Backend Gateway 已接入产品 Agent API、Session 投影和 Knowledge 内部适配器；本文记录静态代码状态，不替代独立进程或可靠性验收。

## 身份与关联

```text
User → Session → Turn → Task → Run 1 / Run 2 / ...
```

- 一次用户提交创建一个 Task；一个 Task 可有多个执行尝试，每次尝试有新的 `run_id`，`RunRecord.attempt` 从 1 递增。旧 Run、报告和事件按各自 `run_id` 保留，`TaskRecord.current_run_id` 只指向当前尝试。
- Session 包含多个 Turn。会话任务一对一关联一个 Turn，`TaskSubmission.session_id` 与 `turn_id` 必须同时存在；`RunRequest` 复制同一对关联 ID。两字段也可同时为 `None`，表示非会话任务。仅提供其中一个会在构造契约对象时抛出 `ValueError`。
- `TaskRecord.session_id`、`turn_id` 从其 `submission` 读取；`RunRecord.task_id` 从其 `request` 读取。`RunRequest.task_id` 必填；Control 创建 Run 时负责核对 Task 归属、唯一 `run_id` 和递增 attempt。单个 dataclass 无法替代跨记录唯一性约束。
- `owner_id` 由可信 Backend 根据用户身份生成，沿用 `user:<id>` / `anon:<id>`。Agent 内部 API 校验服务 Bearer 凭据，并按 owner 限制任务和运行的读取与操作。配额和跨 Worker 的用户并发控制尚未接入。

`TaskSubmission` 保留 `prompt`、`input_ref`、`idempotency_key`；`TaskRecord` 保留 `status`、`created_at`、`cancel_requested` 和 `current_run_id`。`RunRequest` 保留模式、模型、Workspace、Skills、预算和输入引用；`RunRecord` 保存请求快照、attempt、状态、创建/完成时间及错误字段。Session/Turn 的对话内容和 Transcript 仍由既有 `agent_sessions` Repository 保存，不复制为另一套会话记录。

## 执行结果与用量

`WorkerExecutor.execute(RunRequest)` 产生一个 `ExecutionReport`：`task_id`、`run_id`、最终 `RunStatus`、JSON 兼容的结果字典或 `None`、`UsageReport`、`error_code` 与 `error_message`。共享协议不嵌入 Runtime Python 对象。报告不接受 `PENDING` 或 `RUNNING`；`AWAITING_INPUT` 表示本次 Runtime 尝试已停止并交出问题，不表示 Task 已完成。

Agent Worker 的报告适配器负责把 Runtime `RunResult` 转换为 JSON 兼容报告字典，并映射错误和测得用量。Agent Runtime 的消息、最终文本和产物以字典字段表达。Control 在单一数据库事务内写报告、更新 Run/Task 状态并决定重试；失败或超时最多执行 3 次，使用新 `run_id` 和指数退避。用量结算尚未接入 Backend 配额服务。

`BudgetLimits` 包含时长、工具次数和模型 Token 限制。Worker 按模式设置默认时长与工具次数，并可执行更严格的显式上限。`UsageReport` 用 `None` 表示未知；模型 Token 上限当前无法可靠预先强制，带该限制的 Run 会失败并返回明确执行错误。

## 事件

Runtime `AgentEvent(seq, turn, name, data)` 是事件来源。Worker 边界将字段复制为 `PlatformEvent(task_id, run_id, seq, turn, name, data, occurred_at)`，交给 Control 的 `EventSink.publish`；共享协议不携带 Runtime 类实例。这里 `turn` 是 Runtime 内部轮序号，不是产品 `turn_id`。

`seq` 在单个 Run 内排序；`PlatformEvent.sequence` 与 `seq` 相同。事件标识为 `PlatformEvent.event_key == (run_id, seq)`，数据库对 `(run_id, seq)` 建唯一约束；相同事件重放幂等，冲突事件拒绝。`PlatformEventWire` 与 `EventIngestWire` 是共享 HTTP envelope，`GET /internal/v1/runs/{run_id}/events?owner_id=...&after_seq=...` 提供持久事件读取。Backend Gateway 校验提交、Task、Run 与事件响应，再将持久事件投影到产品 SSE。

产品 SSE 的 `after` 是从 0 开始的下一条事件偏移，与内部 API 的 `after_seq` 含义不同。若客户端最后完整收到的 SSE `id` 为 3，同一流续接时传 `after=4`。

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

表中 Protocol 描述职责，实际支持的操作以 HTTP 路由为准。会话任务已通过 `session_id`、`turn_id` 和 Backend 提供的 `history` 执行。模型 Token 显式限制仍在执行前拒绝，时长与工具次数可执行。

## V1 Agent API 与 Worker 现状

任务提交会在同一事务创建 Task、首个 pending Run 和调度 Outbox 记录；Worker 通过内部 API 领取，Agent 使用 PostgreSQL `FOR UPDATE SKIP LOCKED` 分配执行权。领取响应返回递增的 fencing token，Worker 随心跳、事件和报告提交该 token。Runtime 事件先写入 Agent Event Store，写入失败时 Worker 不会提交成功报告。Backend `AgentGateway` 使用共享 Wire Model 校验产品边界的数据。

Worker 心跳使用 `POST /internal/v1/runs/{run_id}/heartbeat`。请求是 JSON 对象 `{"worker_id":"worker-1","lease_token":1}`，由共享 `WorkerHeartbeatRequestWire` 校验，token 必须是正整数。响应由 `WorkerHeartbeatResponseWire` 定义：

| 响应 | 含义与 Worker 行为 |
| --- | --- |
| `{"active":true,"cancel_requested":false}` | 租约已续期，继续执行。 |
| `{"active":true,"cancel_requested":true}` | 租约已续期，Worker 通知 Runtime 停止，最终状态由执行报告确定。 |
| `{"active":false,"cancel_requested":false}` | 当前 Worker 无有效执行权，停止本地执行。 |

无效请求返回 `422`。Worker 默认每 12 秒发一次心跳，Agent 续租到 45 秒后。查询参数不属于该接口契约。

相同报告重试幂等成功，冲突报告拒绝；Task、Run、报告、重试 Run 与 Outbox 更新由数据库事务协调。运行中 steer 经持久 Control 记录传给 Worker；Backend Knowledge Adapter 已调用 Backend 内部 API。暂停和产品配额结算尚未实现。

Worker 通过独立进程入口运行；`AGENT_DATABASE_URL` 与 `AGENT_SERVICE_TOKEN` 均归 Agent 运行环境。Backend 上传附件会先做 owner 校验与解析，再把受限文本上下文随 Task 提交；`input_ref` 尚未启用，Agent 收到非空引用会明确失败。Agent API 与 Worker 需挂载同一个 `AGENT_WORKSPACE_ROOT` 持久共享目录，Workspace 文件通过 owner 与工作区 ID 重新定位。

## 目标契约与当前差距

用户级调度、并发准入和 Worker 交接的目标见 [用户级调度契约](scheduling.md)。

| 目标 | 当前兼容行为 |
| --- | --- |
| Agent 持有 Conversation / Message；Backend 保存展示投影和外部引用 | Backend 仍提交会话历史，Agent 保存执行请求与结果快照。 |
| Interaction 回答形成新产品 Turn，原 Task / Run 创建新 Attempt 继续执行 | 当前后续回答仍是一次新 Task；内部 API 没有 Interaction 回答接口。 |
| 基础设施重试在同一个 Run 下建立独立 Attempt，从安全 Checkpoint 恢复 | 失败或超时会新建 Run，过期租约可复领旧 Run。尚未接入独立 Attempt、Checkpoint 和工具执行日志；同一 Run 从头执行时可能与已有事件序号冲突。 |
| Task 级事件游标与事务通知 Outbox | 当前游标为单 Run 的 `after_seq`；调度 Outbox 与事件存储职责不同。 |
| Backend 可靠提交、签发 BudgetGrant，并按用量报告幂等结算 | 当前由 Backend 同步提交并提供稳定幂等键，尚无提交 Outbox、额度预留、Grant 和结算。 |

后续契约演进需保持以下语义：

- **标识与恢复**：`task_id` 标识用户任务，`run_id` 标识逻辑执行版本，`attempt_id` 标识一次物理执行。基础设施重试沿用原 Task / Run，分配新 Attempt 和更大的 fencing token；用户主动重跑产生新的逻辑执行版本。恢复只使用兼容的 Checkpoint，未知副作用交给工具恢复策略。
- **回答追问**：Backend 的新 Turn 携带 `interaction_id` 和稳定幂等键。Agent 校验归属和等待状态，同一 Interaction 只接受一次有效回答，持久化消息后重新调度原 Run。
- **事件和游标**：目标事件由 Agent 分配 Task 内单调递增的 `sequence`，并包含 `event_id`、版本及关联的 Run / Attempt。Backend 按 Task 持久化已处理游标。现有 `after_seq` 仍只解释为 Run 内序号，不能直接作为 Task 游标使用。
- **提交和额度**：Backend 保存可重试的提交与额度预留。同一次提交在响应丢失后沿用原幂等键；Agent 校验绑定预留、主体、期限和限额的 Grant，Backend 用稳定的用量报告 ID 结算。

这些变更需要配套的数据迁移和版本化接口。在新读写路径接入前，现有历史记录和调用方仍按当前契约工作。
