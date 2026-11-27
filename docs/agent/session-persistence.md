# Agent 会话持久化

## 产品边界

Agent 正式会话以 FastAPI 中的 Agent Session Repository 为 source of truth。Web 不再向正式运行接口传入完整历史，也不再从 `shenzhi-agent-sessions` 读取 Sidebar 历史。Backend 产品路径为 `/api/v2/agent/*`；`/run` 为 Paper Agent 等无状态调用提供 SSE，独立 Task JSON 提交使用 `/submissions`；首页和 `/agents` 使用持久化 Session API。

Agent 执行库另存 Task、Run、事件和控制记录。Backend 在 Turn 的 `settings` 中记录 `agent_task_id` 和 `agent_run_id`，用于轮询和恢复。
V2 任务运行列表响应通过共享 `TaskRunsResponseWire` 校验，接受 `schema_version: 1`，保留完整且有序的 `run_ids`；其他版本仍拒绝。

没有 `CHAT_DATABASE_URL` 时使用进程内 Memory Repository，API 会在列表响应中标记 `ephemeral: true`。该模式只用于开发和测试，不提供跨重启持久化；PostgreSQL 是生产数据源。

## 数据模型

Migration `007_agent_sessions` 创建两张表；`agent_turns` 的幂等键、Worker ID 与租约字段由 `016_request_idempotency` 增加。Agent 附件解析文本另存于 `011_agent_uploads` 创建的表，见下文 API。

Migration `029_agent_message` 为 `agent_turns` 增加可空 `message` JSONB 列，保存 Agent 结构化消息快照。部署新 Backend 前先执行迁移；既有记录保持 SQL NULL，不重写旧正文或推造引用。

`030_merge_billing_message` 合并 `029_agent_message` 与订阅分支的 `029_billing`，不执行额外 DDL。从任一分支升级到 `head` 都会补齐另一分支的迁移。

### `agent_sessions`

- `id`：`ses_` 前缀的不可猜 UUID。
- `owner`：复用 `request_owner`，值为 `user:<id>` 或 `anon:<uuid>`。
- `title`：创建时由后端取首条 prompt 的前 50 个字符，后续可重命名。
- `settings` JSONB：最近一轮的 `model` / `mode` / `attachments` / `skills` / `workspace_id`。
- `branched_from`：为后续分叉保留的逻辑关联，不会自动复制会话。
- `import_key`：旧 localStorage 迁移的幂等键，在同一 owner 内唯一。
- `created_at` / `updated_at`。

`(owner, updated_at DESC, id DESC)` 索引服务于 Sidebar 的 keyset pagination。

### `agent_turns`

一条 Turn 对应一次“用户输入 → Agent 运行结果”，不存每个 SSE token。字段包括：

- `user_content`、`assistant_content`、`reasoning`。
- `message` JSONB：完整 AIMessage（Metadata、当前支持的 Markdown Blocks 和 References）；旧记录为 `null`。
- `settings` JSONB：该轮的模型、模式、附件、Skill 和 workspace。
- `process` JSONB：按到达顺序保存 reasoning / text / tool timeline，工具条目含参数、完成状态、耗时、摘要与错误状态。
- `steers`、`report`、`sources`、`question`、`warnings`。
- `error`、`stopped`、`stop_reason`、`status`、`usage`。
- `transcript` JSONB：经 Agent Runtime 编码的完整、闭合历史，下一轮由后端从最新 Turn 恢复。
- `idempotency_key` 与 `idempotency_fingerprint`：同一 Session 内识别一次运行操作并检查请求内容；文件上传 ID 不写入 Turn。
- `created_at` / `completed_at`。

Session 删除时 Turn 通过外键 `ON DELETE CASCADE` 删除。`status = 'running'` 的部分唯一索引保证同一 Session 最多一个 active run，其他操作竞争时返回 409。`POST /sessions/{id}/run` 使用 `Idempotency-Key` 请求头；相同 owner、Session、键和请求复用原 Turn，不重复执行模型或工具。同键请求内容不同返回 409。新一轮任务必须使用新键。键和指纹随 Turn 在一条数据库事务中建立，因此事务失败不会留下脱离业务资源的键记录。

### 结构化消息投影

Backend 通过共享 `agent_contracts.messages` 校验六类消息事件和完整消息。唯一 V2 Gateway、首次运行、恢复运行及兼容的无状态运行均保留消息载荷。Backend 不拼接/重写 Block，不重新编号引用，也不把 `references` 混入旧 `output.sources`。

最终 SSE `result.message` 与历史接口 `turns[].message` 使用同一结构。优先保存报告的 `result.message`；报告缺少该字段时使用同一执行尝试的 `message_end.message`。两者同时存在但不一致、消息状态与运行终态不符、消息结构无效，或已收到结构化事件却没有最终快照时，记录诊断并丢弃结构化快照，不修改消息自身状态。已有明确 ExecutionReport 终态时仍保存 Turn 终态、普通文本、Timeline、原始 transcript 和 Usage，不因展示快照异常停留在 running。若事件读取失败但本次已读取封存报告，使用报告继续投影；没有报告的读取失败仍保留 running 并释放投影租约以供恢复。

校验后保存原始 JSON：保留 Markdown 空格/换行、数组顺序、系统字段、嵌套 metadata，以及显式 `null` 与省略字段的区别。JSONB 对象键顺序不属于协议语义。内存存储、公开消息和 SSE 缓冲使用独立消息副本，避免后续对象修改污染已保存或可重放的数据。

每次重试的 `run_start` 清空当前消息快照，只把最后一次尝试的消息保存到 Turn；此前尝试的原始消息事件继续在 SSE 中按原顺序回放。恢复仍使用现有 SSE 游标，不额外插入消息事件。旧记录及旧 localStorage 导入没有结构化快照时，`message=null`，原 `assistant_content`、报告、来源、过程和 transcript 保持可读；不会在读取时回填或改写数据库。

## 生命周期

1. 首页智能搜索先 `POST /api/v2/agent/sessions`，即使后续运行失败，Session 也已存在。
2. Web 将第一轮完整 `AgentRunInput` 写入 `sessionStorage` 的一次性 launch 记录，URL 只携带 `session` 和不透明 `launch` id。
3. `/agents?session=<id>&launch=<id>` 先向后端恢复 Session，然后消费一次 launch，调用 `POST /api/v2/agent/sessions/{id}/run`。首轮的 model / mode / attachments / skills 以显式入参传入，不依赖 React state flush。
4. Backend 校验 owner，从最新 transcript 恢复历史，预留 running Turn，向 Agent API 提交 Task 并记录 Task / Run ID。
5. Worker 经 Agent API 领取和执行 Run。Backend 轮询持久事件，经 SSE 发送 delta、tool、steer 等内容，并将终态投影到 Turn。Agent Control 为可重试失败创建新 Run；Backend 经只读 Task Run 列表按 attempt 顺序投影全部 Run，排空旧 Run 尾部后再进入直接后继，只在最后一个 Run 结束时生成 result。
6. 产品 SSE 订阅与执行解耦。断开订阅后运行可继续。Backend 通过五分钟 Turn 投影租约和三十秒续租协调投影写入，Agent Worker 使用独立的 Run 租约。失去投影租约的 Backend 无法覆盖后续投影终态。
7. `LiveRun` 与 SSE 缓冲仍在 Backend 进程内。缺少本地缓冲时，Backend 可依据 Task / Run ID 通过 Agent 持久事件恢复；活跃投影被另一 Backend 持有时返回 409。未关联 Agent Task 的运行无法从 Agent 回放。投影恢复和跨进程游标连续性仍需联调。

投影读取失败不再将 Turn 标记为执行失败：流以无 result 的 EOF 结束，清除不完整缓存，按 worker_id 释放投影租约；数据库不可用时仍等待原租约到期。客户端重连后从持久事件恢复，执行终态只来自 Agent 报告。缓存订阅每次重新校验当前 Session owner 和最新 Turn；旧幂等键只回放它关联的 Turn，不替换最新订阅。

Turn 内部 settings 的 `_agent_owner_id` 保存原 Agent 执行身份，不返回 Web。匿名认领在同一 Backend 事务中为旧关联 Turn 补齐该字段，产品归属检查仍使用当前 owner，再用原执行身份读取 Agent 历史。已在旧版本完成认领且没有此字段的记录不能自动推断原身份，需单独核对后修复。


## API

- `GET /api/v2/agent/config`：模型、真实 Skills 和附件限制。
- `POST /api/v2/agent/sessions`：创建 Session，后端生成 id 和初始标题。
- `GET /api/v2/agent/sessions?limit=10&cursor=...`：按当前 owner 分页。
- `GET /api/v2/agent/sessions/{id}`：返回 Session 和全部 Turns。
- `PATCH /api/v2/agent/sessions/{id}`：重命名。
- `DELETE /api/v2/agent/sessions/{id}`：删除 DB Session 及其 Turns。
- `POST /api/v2/agent/sessions/{id}/run`：基于后端历史启动一轮 SSE Run；前端必须为一次用户提交生成并在该操作重试时复用 `Idempotency-Key`。
- `GET /api/v2/agent/sessions/{id}/run/stream?after=<n>`：从事件索引 `after`（默认 0）起重放；Backend 会优先使用本地 `LiveRun`，缺少时尝试恢复已关联的 Agent Run。页面刷新后若最新 Turn 仍为 `running`，`ShenzhiAiPage` 用它重新订阅。
- 同一 Task 的首次流和无缓存恢复均从最早 Run 枚举全部历史，SSE ID 保持零基事件偏移。`after` 是下一条待收事件的 ID：result ID 为 6 时，未收到传 6，已完整收到传 7。编号依据见 [共享契约](contracts.md#事件)。
- `POST /api/v2/agent/run/{run_id}/steer`：向当前 owner 的 active run 插话。
- `POST /api/v2/agent/run/{run_id}/stop`：请求当前 owner 的 active run 正常停止。
- `POST /api/v2/agent/sessions/import`：按 `(owner, import_key)` 幂等导入旧本地会话。
- `POST /api/v2/agent/uploads` / `GET /api/v2/agent/uploads/{file_id}`：解析并暂存 owner 隔离的附件文本 / 查询状态（不返回正文）。配置 `CHAT_DATABASE_URL` 时存 PostgreSQL，否则存进程内存；24 小时过期，运行消费后删除。附件 ID 只在运行入参中引用，不写入 Turn。
- `POST /api/v2/agent/run`：无状态运行接口，不是首页和正式 Agent 页的产品路径；论文详情页 Agent（`use-paper-agent.ts`）仍使用它。
- 历史消息中的同源 `GET /api/v1/agent/assets/{session_id}/{path}` 和 `GET /api/v1/agent/session/{session_id}/file` 由 BFF 转发到对应 V2 读取接口，继续沿用 Backend 的归属与路径校验。新产物使用 V2 URL。

除 config/export 等明确的 BFF 端点外，Session 端点均使用 `request_owner`。查询条件同时带 `id` 和 `owner`；他人会话与不存在会话统一返回 404，不泄露存在性。

## URL 和页面流

- `/`：发现页。简单搜索只跳转 `/knowledge/search?q=...`；智能搜索创建 Backend Session 后跳转 Agent 对话。
- `/agents`：深知 AI 新对话页（侧边栏「深知 AI」入口）。与发现页智能搜索共用 `features/agent-chat/use-agent-launcher.ts`，同样创建 Backend Session 后跳转 Agent 对话。
- `/agents?session=<id>`：具体持久化会话。刷新和浏览器 back/forward 都按 URL 重新向后端加载。

页面显示每轮的执行中、完成、失败、超时、停止或等待回答状态。SSE 未收到 result 就结束，或 45 秒没有收到任何数据（含心跳），视为连接问题；不推断任务已失败。用户可点击“重新连接 / 刷新结果”重新 GET Session，并在最后一轮仍为 running 时从 `after=0` 重建当前轮的增量显示。执行状态未确认时禁止新提交；结果正文使用服务端最终 `final_text`，与历史记录保持一致。产品闭环的隔离 Mock 演示见 [本地演示](local-demo.md)。

## Sidebar 分页

AppSidebar 的主 `nav` 是唯一纵向滚动容器。“聊天”列表首次请求 10 条，底部 sentinel 以该 `nav` 为 `IntersectionObserver.root`；接近底部时使用 `next_cursor` 加载下 10 条，`has_more=false` 后停止。

cursor 是 base64url 编码的 `[updated_at, id]`。查询使用 `(updated_at, id) < cursor` 和降序索引，不会先返回全量再在前端切片。新建、重命名、删除或运行完成会触发列表刷新。

## localStorage 迁移

Sidebar 首次连接到 durable Repository 时检查 `shenzhi-agent-sessions`：

1. 每个本地 Session 以 `local-v1:<old_session_id>` 作为 `import_key` 逐条导入。
2. 重试不会重复创建；后端唯一索引也处理并发导入。
3. 只有全部导入成功后才写入 migration flag 并删除旧 key。任意失败都保留全部本地源数据。
4. Memory / dev fallback 不执行迁移，避免把持久数据搬进不持久进程后删除。

## 删除与后续项

- 当前删除只删除 Session / Turn 数据库行。不会根据模型或请求提供的路径递归删除 workspace；需要后续增加以 owner + session id 为边界的产物保留/清理任务。
- 匿名会话按浏览器 UUID 严格隔离。登录后的认领已接入：全局 `AppShell` 中的 `AnonymousClaimCoordinator` 经同源 `/api/identity/anonymous-claim` 预览并在用户确认后认领，FastAPI `POST /api/v1/identity/anonymous-claim` 调用 `services/identity/anonymous_claim.py`，迁移 Agent Session（含工作区复制）及 Agent 附件；有 `running` Turn 的 Session 暂不迁移并计入 `skipped_streaming_count`。source owner 只来自 BFF 注入的双身份请求头，客户端不能指定，细节见 [认证架构](../auth/ARCHITECTURE.md#anonymous-identity-and-claim)。
- Agent 匿名会话目前没有接入 TTL 清理：维护命令 `uv run --locked python -m app.services.agent_uploads` 只删除过期的 Agent 附件暂存文本（输出 `expired_agent_uploads`），不处理 `agent_sessions`；上线前应增加保留期策略，避免匿名数据无限增长。
- PostgreSQL 会按产品投影租约处理过期的 running Turn，已关联的 Agent Run 可走事件重放路径；Memory fallback 不存在跨进程租约或重启恢复。
