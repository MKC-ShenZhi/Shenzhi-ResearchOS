# Agent 结构化消息 V1

本阶段验证 Agent Service 的消息组织边界，只定义 Message Metadata、MarkdownBlock、Reference，以及六类结构化消息事件。协议版本为 `schema_version=1`，与内部 API 的 v1/v2 版本独立。

Backend 已接入消息传输、存储和历史读取；实现与部署迁移见 [会话持久化](session-persistence.md#结构化消息投影)。当前仍未扩展其他 Block 类型。

Web Client、SSE 事件分发及会话状态已接入；Block 组件渲染与引用展示尚未接入。

## 代码职责

| 位置 | 职责 |
| --- | --- |
| `packages/agent-contracts/src/agent_contracts/messages.py` | 消息及事件数据模型、Block 判别类型、字段与引用关联校验 |
| `apps/agent/src/agent_app/execution/message_stream.py` | 消息生命周期、有序 Markdown 块、增量引用标记校验、最终消息组装 |
| `apps/agent/src/agent_app/execution/references.py` | 程序生成来源 ID，按来源类型及 entity_id、DOI 或 URL 去重和补全 |
| `ToolOutput.references` / `ToolResult.references` | 工具到 Runtime 的来源数据通道；不从模型文本或任意工具文本中猜测来源 |
| Runtime / Worker | 驱动组装、沿用事件序号与持久化链路、在执行报告中保存最终 `message` |
| `apps/web/clients/backend/agent-message.ts` | Web 消息类型、Zod 协议校验、六类消息事件解码 |
| `apps/web/features/agent-chat/message-state.ts` | 无 React 依赖的 Block/Reference 组装、事件去重和最终快照校准 |
| `apps/web/features/agent-chat/session-state.ts` | Backend 历史 Turn 到页面会话状态的恢复 |

Provider 的 `AssistantMessage` 是模型上下文与工具往返 transcript；`AIMessage` 是面向展示的完整消息。两者职责不同。系统不要求 LLM 生成 ID、状态、时间戳或 JSON 外壳，LLM 继续流式生成 Markdown，通过 `[[cite:ref_id]]` 使用工具提供的来源。

`AIMessage` 的字段为 `id`、`role=assistant`、`status`、`created_at`（Unix 秒）、`schema_version`、可选 `metadata`、`blocks` 和 `references`。状态复用 Runtime 的 `running`、`done`、`failed`、`stopped`、`timeout`、`awaiting_input`，不使用 Control 的另一套 RunStatus。`metadata` 当前记录模型、耗时；遇到无效引用时另记录诊断 ID。

## 生成与传输

每次 Runtime 执行产生一条展示消息。每次模型调用中有可见正文时创建一个 MarkdownBlock；工具调用后的继续作答创建下一个块，空响应和纯思考不创建空块。

结构化事件沿用 `AgentEvent(seq, turn, name, data)` 和 Worker 的 `PlatformEvent` envelope：

| name | data |
| --- | --- |
| `message_start` | `{message}`，初始化或恢复中的完整消息快照 |
| `block_start` | `{message_id, block}`，Markdown 块初始正文为空 |
| `block_delta` | `{message_id, block_id, delta}`，追加正文 |
| `block_end` | `{message_id, block_id}` |
| `reference_upsert` | `{message_id, reference}`，按来源 ID 新增或补全 |
| `message_end` | `{message}`，含终态的最终完整消息 |

序号由 Runtime 统一递增，Worker 继续叠加领取时的持久事件偏移。稳定去重键仍为 `(run_id, seq)`；消息及块 ID 在同一组事件中不变。断线后重放已持久化事件，不重新生成 ID。Worker 租约接管目前仍从头执行并生成新消息 ID，不表示恢复上一条消息；该限制沿用现有执行架构。

`message_end` 用于替换/校准最终状态，不追加正文。原 `delta`、思考、工具、steer、反问及 `run_end` 事件保留；消费者应选择旧正文事件或 Block 事件中的一套，避免重复显示。

## 来源和异常

当前 `web_search`、`paper_search`、`paper_detail` 从已返回的数据构造 `Reference`，Runtime 注册后把规范来源 ID 注入工具上下文的 `references`。搜索与详情匹配同一 entity_id 时复用 ID，详情补充 DOI、作者、年份等字段；重复引用不新增记录。其他工具尚未声明来源时不会自动生成来源。

来源记录独立于 Markdown 块，允许在生成中 upsert。Pydantic 校验唯一 Block/Reference ID、字段类型、版本、Markdown 引用与来源的关联；共享事件与报告入口也校验新增载荷，未知的旧事件保持原有读取方式。

引用标记跨增量边界时先缓存，完整后再校验。不存在的引用替换为 `[引用不可用]`，中断时未闭合的引用替换为 `[引用不完整]`；其余正文继续保留。结构化流与最终消息使用相同的校验后正文。旧 transcript 与旧文本事件保留原始内容供兼容和诊断使用。

失败、停止、超时均闭合已开始的块，发送完整终态消息。外部任务取消也先发出终态快照，再继续传播 `CancelledError`。反问仍通过既有问题制品通道返回，消息状态为 `awaiting_input`。

## 历史与扩展

执行报告的 `result.message` 保存同一个 `AIMessage`，可作为后续历史展示的数据源；原 `final_text`、`messages`、`output` 等字段保留。旧 transcript 没有 `references` 时仍可解码。新工具 transcript 会保存注册后的来源；Checkpoint 同时保存消息快照与事件序号，直接 Runtime resume 可沿用消息、来源及序号。

新增 Block 时，在共享协议增加具体模型并扩展 `ContentBlock` 的 `type` 判别集合，在消息组装层增加对应写入逻辑与校验，再接入消费者。不要在 Provider、Worker 或 SSE 传输中增加按具体 Block 类型分支的处理。来源适配继续通过 `ToolOutput.references`，不把工具名称或上游返回格式写入消息组装器。

Backend 在最终 SSE `result.message` 和历史详情 `turns[].message` 返回同一份结构化快照，存储于 `agent_turns.message`，不重新组织正文或来源。Web Client 已接入；Renderer 尚未接入，因此不代表产品 UI 已完成 Block 渲染和引用展示。报告文件与反问等原有制品继续使用原通道。

## Web 数据层

Client 复用已有通用 SSE 解析器，将六类消息事件连同原始 SSE `id` 交给可选的 `onMessageEvent`。会话 POST、GET 重放和无状态运行共用这一入口；原正文、思考、工具、反问及其他回调保持原有行为。新增协议使用已有 Zod 依赖校验，仅接受当前 Markdown Block。完整消息同时校验版本、状态、唯一 ID 和引用关联；兼容 API v2 事件外层的 `schema_version`。Client 不生成系统字段、不改写 Markdown 或引用标记。

Feature 在每个助手 Turn 的 `structured` 中保存 `AgentMessageState`，完整消息位于 `structured.message`，不与现有 `content`、`stream`、`report` 或 `sources` 混用。深知 AI 页面与论文问答共用同一个纯组装器；页面只将事件连接到状态，不增加 Block 渲染逻辑。

- `message_start` 初始化或替换快照；`block_start` 按到达顺序追加块，`block_delta` 只追加到当前打开的 Markdown 块，`block_end` 结束该块。
- `reference_upsert` 按来源 ID 原位替换或追加记录，不重新编号或排序；引用标记可跨 delta，来源也可稍后到达。
- Backend 的数值 SSE ID 用于高水位去重，重放已处理事件不会重复追加。新的 Run 清空结构化状态；同一 Run 的重复 `run_start` 保留现有状态。没有 SSE ID 时不根据正文猜测重复。
- `message_end` 和最终 `result.message` 替换完整快照，不追加正文。`message_end` 不代表产品流已完成，仍须等待 `result`；EOF、超时或解析失败保留已组装的有效内容。
- 关联到其他消息的事件被忽略。块的打开/关闭顺序错误保留原内容，并记入 `structured.protocolError`；最终合法快照可以校准状态。字段、版本或完整引用关联无效时，Client 中止该次连接，沿用页面现有重连提示。
- 历史 `message=null` 或缺失时，不合成结构化消息，原正文、过程、报告和来源继续可读。合法快照以独立副本恢复，保留嵌套 metadata、显式 null、可选字段缺失、数组顺序和原始文本。

后续新增 Block 应同步扩展 Client 判别 Schema 和必要的组装规则；Renderer 再读取 `structured.message` 分发组件。通用 SSE 解析与传输无需按具体 Block 类型增加分支。

## 验证

在 `apps/agent` 执行 `uv run --locked python -m pytest tests -q`；共享契约在 `packages/agent-contracts` 执行 `uv run --group dev python -m pytest tests -q`。

`test_message_blocks.py` 使用脚本化 Provider 验证引用分片、来源去重、连续块、事件重建/去重、终态校准、异常保留、反问、Checkpoint 和 Worker 报告。`test_worker_takeover.py` 经过真实 Agent API、Control SQL 和 Worker，核对事件落库后的最终消息；SQLite 测试不代表生产 PostgreSQL 并发验收。

Backend 的 `tests/test_agent_message_blocks.py` 验证 Gateway v1/v2、产品 SSE、断线游标、重试和历史接口的数据一致性；`tests/test_agent_message_postgres.py` 在显式配置 `TEST_AGENT_MESSAGE_DATABASE_URL` 的隔离测试库中验证真实 JSONB 往返、连接重建、旧数据迁移和无效载荷不落库。测试库须先应用 Backend 迁移，禁止将该测试变量指向业务数据库。

Web 在 `apps/web` 执行 `pnpm test`、`pnpm typecheck`，并对改动文件执行 ESLint。`tests/agent/message-blocks.test.ts` 验证纯协议及组装器；`message-stream.test.ts` 使用 mock fetch 和分片 ReadableStream 验证真实 Client/SSE 解析到状态及历史恢复的完整数据链路，不调用真实 Agent 或模型。
