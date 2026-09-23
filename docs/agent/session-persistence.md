# Agent 会话持久化

## 产品边界

Agent 正式会话以 FastAPI 中的 Agent Session Repository 为 source of truth。Web 不再向正式运行接口传入完整历史，也不再从 `shenzhi-agent-sessions` 读取 Sidebar 历史。旧 `/api/v1/agent/run` 仍保留给 Paper Agent 等兼容调用；首页和 `/agents` 使用持久化 Session API。

没有 `CHAT_DATABASE_URL` 时使用进程内 Memory Repository，API 会在列表响应中标记 `ephemeral: true`。该模式只用于开发和测试，不提供跨重启持久化；PostgreSQL 是生产数据源。

## 数据模型

Migration `007_agent_sessions` 创建两张表。

### `agent_sessions`

- `id`：`ses_` 前缀的不可猜 UUID。
- `owner`：复用 `request_owner`，值为 `user:<id>` 或 `anon:<uuid>`。
- `title`：创建时由后端取首条 prompt 的前 50 个字符，后续可重命名。
- `settings` JSONB：最近一轮的 `model` / `mode` / `attachments` / `skills` / `workspace_id`。
- `branched_from`：为后续分叉保留的逻辑关联，本次不自动复制会话。
- `import_key`：旧 localStorage 迁移的幂等键，在同一 owner 内唯一。
- `created_at` / `updated_at`。

`(owner, updated_at DESC, id DESC)` 索引服务于 Sidebar 的 keyset pagination。

### `agent_turns`

一条 Turn 对应一次“用户输入 → Agent 运行结果”，不存每个 SSE token。字段包括：

- `user_content`、`assistant_content`、`reasoning`。
- `settings` JSONB：该轮的模型、模式、附件、Skill 和 workspace。
- `process` JSONB：按到达顺序保存 reasoning / text / tool timeline，工具条目含参数、完成状态、耗时、摘要与错误状态。
- `steers`、`report`、`sources`、`question`、`warnings`。
- `error`、`stopped`、`stop_reason`、`status`、`usage`。
- `transcript` JSONB：经 Agent Runtime 编码的完整、闭合历史，下一轮由后端从最新 Turn 恢复。
- `created_at` / `completed_at`。

Session 删除时 Turn 通过外键 `ON DELETE CASCADE` 删除。`status = 'running'` 的部分唯一索引保证同一 Session 最多一个 active run，竞争请求返回 409。

## 生命周期

1. 首页智能搜索先 `POST /api/v1/agent/sessions`，即使后续运行失败，Session 也已存在。
2. Web 将第一轮完整 `AgentRunInput` 写入 `sessionStorage` 的一次性 launch 记录，URL 只携带 `session` 和不透明 `launch` id。
3. `/agents?session=<id>&launch=<id>` 先向后端恢复 Session，然后消费一次 launch，调用 `POST /api/v1/agent/sessions/{id}/run`。首轮的 model / mode / attachments / skills 以显式入参传入，不依赖 React state flush。
4. Backend 校验 owner，从已存最新 transcript 恢复 runtime history，预留 running Turn，再开始 SSE。
5. 运行期间 SSE 实时传输 delta / tool / steer / report 等事件。正常结束、`ask_user`、失败、超时和手动停止都在终态时一次性写入 Turn。
6. SSE 连接在 RunResult 产生前断开时，桥接层会把已可见的正文和 timeline 作为 `connection_closed` 停止轮次保存。后端重启时，遗留的 running Turn 标记为 `failed` / `backend_restart`。

## API

- `GET /api/v1/agent/config`：模型、真实 Skills 和附件限制。
- `POST /api/v1/agent/sessions`：创建 Session，后端生成 id 和初始标题。
- `GET /api/v1/agent/sessions?limit=10&cursor=...`：按当前 owner 分页。
- `GET /api/v1/agent/sessions/{id}`：返回 Session 和全部 Turns。
- `PATCH /api/v1/agent/sessions/{id}`：重命名。
- `DELETE /api/v1/agent/sessions/{id}`：删除 DB Session 及其 Turns。
- `POST /api/v1/agent/sessions/{id}/run`：基于后端历史启动一轮 SSE Run。
- `POST /api/v1/agent/run/{run_id}/steer`：向当前 owner 的 active run 插话。
- `POST /api/v1/agent/run/{run_id}/stop`：请求当前 owner 的 active run 正常停止。
- `POST /api/v1/agent/sessions/import`：按 `(owner, import_key)` 幂等导入旧本地会话。
- `POST /api/v1/agent/run`：旧无状态兼容接口，不是首页和正式 Agent 页的产品路径。

除 config/export 等明确的 BFF 端点外，Session 端点均使用 `request_owner`。查询条件同时带 `id` 和 `owner`；他人会话与不存在会话统一返回 404，不泄露存在性。

## URL 和页面流

- `/`：唯一新任务入口。简单搜索只跳转 `/knowledge/search?q=...`；智能搜索创建 Backend Session 后跳转 Agent 对话。
- `/agents?session=<id>`：具体持久化会话。刷新和浏览器 back/forward 都按 URL 重新向后端加载。
- `/agents`：没有 session 时返回发现页。
- `/agents/ask`：旧 Chat 路由保留为安全 redirect，正式路径不再调用旧 Chat message API。

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
- Repository 已预留匿名 owner 转移能力，但正式 Agent UI 本次未接入“登录后认领”确认流程。匿名会话已按浏览器 UUID 严格隔离；认领 UI/API 应后续复用现有 Chat 的双身份授权模式，不能由客户端任意指定 source owner。
- Agent 匿名会话目前没有接入旧 Chat 的 TTL 清理任务；上线前应为 `agent_sessions` 增加同等的保留期策略，避免匿名数据无限增长。
- PostgreSQL 会在后端启动时恢复遗留 running Turn；Memory fallback 不存在跨重启恢复。
