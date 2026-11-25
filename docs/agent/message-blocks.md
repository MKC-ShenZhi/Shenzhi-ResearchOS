# Agent 结构化消息 V1（第一阶段）

本阶段验证 Agent Service 的消息组织边界，只定义 Message Metadata、MarkdownBlock、Reference，以及六类结构化消息事件。协议版本为 `schema_version=1`，与内部 API 的 v1/v2 版本独立。

## 代码职责

| 位置 | 职责 |
| --- | --- |
| `packages/agent-contracts/src/agent_contracts/messages.py` | 消息及事件数据模型、Block 判别类型、字段与引用关联校验 |
| `apps/agent/src/agent_app/execution/message_stream.py` | 消息生命周期、有序 Markdown 块、增量引用标记校验、最终消息组装 |
| `apps/agent/src/agent_app/execution/references.py` | 程序生成来源 ID，按来源类型及 entity_id、DOI 或 URL 去重和补全 |
| `ToolOutput.references` / `ToolResult.references` | 工具到 Runtime 的来源数据通道；不从模型文本或任意工具文本中猜测来源 |
| Runtime / Worker | 驱动组装、沿用事件序号与持久化链路、在执行报告中保存最终 `message` |

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

本轮未改 Platform Backend 的产品消息投影、Web Client 或 Renderer，因此不代表产品 UI 已完成 Block 渲染和引用展示。报告文件与反问等原有制品继续使用原通道。

## 验证

在 `apps/agent` 执行 `uv run --locked python -m pytest tests -q`；共享契约在 `packages/agent-contracts` 执行 `uv run --group dev python -m pytest tests -q`。

`test_message_blocks.py` 使用脚本化 Provider 验证引用分片、来源去重、连续块、事件重建/去重、终态校准、异常保留、反问、Checkpoint 和 Worker 报告。`test_worker_takeover.py` 经过真实 Agent API、Control SQL 和 Worker，核对事件落库后的最终消息；SQLite 测试不代表生产 PostgreSQL 并发验收。
