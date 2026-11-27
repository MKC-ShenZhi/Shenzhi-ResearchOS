# Agent 结构化消息 V1

本阶段验证 Agent Service 的消息组织边界，只定义 Message Metadata、MarkdownBlock、Reference，以及六类结构化消息事件。协议版本为 `schema_version=1`，与内部 API 的 v1/v2 版本独立。

Backend 已接入消息传输、存储和历史读取；实现与部署迁移见 [会话持久化](session-persistence.md#结构化消息投影)。当前仍未扩展其他 Block 类型。

Web Client、SSE 事件分发、会话状态及 Markdown Block 和引用渲染已接入，深知 AI 与论文问答共用消息组件。

## 代码职责

| 位置 | 职责 |
| --- | --- |
| `packages/agent-contracts/src/agent_contracts/messages.py` | 消息及事件数据模型、Block 判别类型、字段与引用关联校验 |
| `apps/agent/src/agent_app/execution/model_output.py` | 按约定边界拆分流式 Markdown 与模型提交的来源 JSON，并校验来源字段 |
| `apps/agent/src/agent_app/execution/message_stream.py` | 输出格式 Prompt、消息生命周期、有序 Markdown 块、引用键映射、最终消息组装 |
| `apps/agent/src/agent_app/execution/references.py` | 按来源类型及 entity_id、DOI 或 URL 去重、补全和保留来源 ID |
| `ToolOutput.references` / `ToolResult.references` | 保留旧 transcript 的兼容字段，不自动生成当前消息的参考列表 |
| Runtime / Worker | 驱动组装、沿用事件序号与持久化链路、在执行报告中保存最终 `message` |
| `apps/web/clients/backend/agent-message.ts` | Web 消息类型、Zod 协议校验、六类消息事件解码 |
| `apps/web/features/agent-chat/message-state.ts` | 无 React 依赖的 Block/Reference 组装、事件去重和最终快照校准 |
| `apps/web/features/agent-chat/session-state.ts` | Backend 历史 Turn 到页面会话状态的恢复 |
| `apps/web/features/agent-chat/components/message-renderer.tsx` | 消息组织、创建时间与状态展示 |
| `apps/web/features/agent-chat/components/block-renderer.tsx` | Block 类型分发与未知类型降级 |
| `apps/web/features/agent-chat/components/blocks/markdown-block.tsx` | MarkdownBlock 协议到正文 Renderer 的适配 |
| `apps/web/features/agent-chat/components/streamdown-renderer.tsx` | 流式 Markdown、公式、代码及引用角标渲染 |
| `apps/web/features/agent-chat/components/references-renderer.tsx` | 独立来源列表和来源跳转 |
| `apps/web/features/agent-chat/components/citation-markers.ts` / `message-presentation.ts` | 引用 AST 转换、编号、展示字段与安全链接规则 |

Provider 的 `AssistantMessage` 是模型上下文与工具往返 transcript；`AIMessage` 是面向展示的完整消息。模型输出 Markdown 与独立的 references JSON，使用局部引用键绑定两部分。正式消息/Block/Reference ID、状态、时间戳、版本由程序生成，不要求 LLM 输出整个 AIMessage。

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

工具继续返回真实检索、详情或阅读结果，不自动把检索结果转换成消息来源。模型根据当前工具结果、用户提供的资料及历史上下文明确选择实际采用的来源，并按以下格式输出：

```text
先引用 B [[cite:r2]]，再引用 A [[cite:r1]]，重复 B [[cite:r2]]。
<references_json>
[{"id":"r1","type":"paper","title":"来源 A"},{"id":"r2","type":"webpage","title":"来源 B","url":"https://example.test/b"}]
</references_json>
```

标签必须在代码围栏外顶格开始，JSON 为数组，结束标签之后不再输出正文。无引用时为 `[]`。id 是该次模型回复内的局部关联键；程序将它映射为正式 Reference ID。JSON 只允许 Reference 字段，不接受模型提供系统 metadata 或其他 Block。模型只提交有依据的字段，不编造作者、URL 等信息。此格式是结构约束，不承担论文真实性或论断支持度审查。

解析器跨任意 TextDelta 边界识别标签，正文即时流出，JSON 和标签不进入 block_delta、旧正文 delta 或 result.final_text。代码围栏中的示例标签按普通代码保留。Provider transcript 保留模型原始输出，供下一轮上下文及诊断使用。

来源 JSON 到齐后复用 Pydantic Reference 校验，按正文首次引用顺序注册、去重，只保留实际使用的条目。相同 entity_id、DOI 或 URL 复用来源 ID，跨模型回复也可补全已有来源；未被引用的 JSON 条目不产生 reference_upsert。不会回退为将全部工具结果当作引用。

来源记录独立于 Markdown 块，允许在生成中 upsert。Pydantic 校验唯一 Block/Reference ID、字段类型、版本、Markdown 引用与来源的关联；共享事件与报告入口也校验新增载荷，未知的旧事件保持原有读取方式。

引用标记跨增量边界时先缓存，完整后流出程序生成的引用 ID；来源可晚于正文到达。JSON 缺失、截断、格式错误、重复键冲突或超限时保留有效正文与合法来源，无法解析的引用在最终快照替换为 `[引用不可用]`，未闭合引用替换为 `[引用不完整]`。诊断写入 metadata，原始 JSON 不作为用户错误内容展示。

重复来源的别名合并、无效引用的降级可能需要改正已流出的引用标记；message_end 的完整快照负责最终校准，不能再次追加正文。程序保证最终消息引用可解析，Backend 存储和历史读取该最终快照。

失败、停止、超时均闭合已开始的块，发送完整终态消息。外部任务取消也先发出终态快照，再继续传播 `CancelledError`。反问仍通过既有问题制品通道返回，消息状态为 `awaiting_input`。

## 历史与扩展

执行报告的 `result.message` 保存同一个 `AIMessage`，可作为后续历史展示的数据源；`final_text` 为拆分后的正文，`messages` 保留原 transcript，`output` 沿用原制品通道。旧 transcript 没有 `references` 时仍可解码，模型可以根据其中真实资料在新回复中重新提交来源 JSON，无需迁移历史行。Checkpoint 保存已闭合消息快照与事件序号，直接 Runtime resume 可沿用消息、来源及序号。

新增 Block 时，在共享协议增加具体模型并扩展 `ContentBlock` 的 `type` 判别集合，在消息组装层增加对应写入逻辑与校验，再接入消费者。不要在 Provider、Worker 或 SSE 传输中增加按具体 Block 类型分支的处理。模型输出拆分留在独立解析器，来源去重留在注册器，不把工具名称或上游返回格式写入消息组装器。

Backend 在最终 SSE `result.message` 和历史详情 `turns[].message` 返回同一份结构化快照，存储于 `agent_turns.message`，不重新组织正文或来源。Web 使用同一个 MessageRenderer 展示实时与历史消息。报告文件与反问等原有制品继续使用原通道。

## Web 数据层

Client 复用已有通用 SSE 解析器，将六类消息事件连同原始 SSE `id` 交给可选的 `onMessageEvent`。会话 POST、GET 重放和无状态运行共用这一入口；原正文、思考、工具、反问及其他回调保持原有行为。新增协议使用已有 Zod 依赖校验，严格校验 Markdown Block；未来未知类型只要求合法 id/type，并保留原始字段供安全降级，不定义其他具体 Block 模型。已知 Markdown 类型的无效字段不能绕过校验。完整消息同时校验版本、状态、唯一 ID 和引用关联；兼容 API v2 事件外层的 `schema_version`。Client 不生成系统字段、不改写 Markdown 或引用标记。

Feature 在每个助手 Turn 的 `structured` 中保存 `AgentMessageState`，完整消息位于 `structured.message`，不与现有 `content`、`stream`、`report` 或 `sources` 混用。深知 AI 页面与论文问答共用同一个纯组装器；页面只将事件连接到状态，不增加 Block 渲染逻辑。

- `message_start` 初始化或替换快照；`block_start` 按到达顺序追加块，`block_delta` 只追加到当前打开的 Markdown 块，`block_end` 结束该块。
- `reference_upsert` 按来源 ID 原位替换或追加记录，不重新编号或排序；引用标记可跨 delta，来源也可稍后到达。
- Backend 的数值 SSE ID 用于高水位去重，重放已处理事件不会重复追加。新的 Run 清空结构化状态；同一 Run 的重复 `run_start` 保留现有状态。没有 SSE ID 时不根据正文猜测重复。
- `message_end` 和最终 `result.message` 替换完整快照，不追加正文。`message_end` 不代表产品流已完成，仍须等待 `result`；EOF、超时或解析失败保留已组装的有效内容。
- 关联到其他消息的事件被忽略。块的打开/关闭顺序错误保留原内容，并记入 `structured.protocolError`；最终合法快照可以校准状态。字段、版本或完整引用关联无效时，Client 中止该次连接，沿用页面现有重连提示。
- 历史 `message=null` 或缺失时，不合成结构化消息，原正文、过程、报告和来源继续可读。合法快照以独立副本恢复，保留嵌套 metadata、显式 null、可选字段缺失、数组顺序和原始文本。

后续新增 Block 应同步扩展 Client 判别 Schema、必要的组装规则和 BlockRenderer 分支，并在 `blocks/` 增加对应适配组件。通用 SSE 解析与传输无需按具体 Block 类型增加分支。

## Web 展示层

`MessageRenderer` 直接读取 `structured.message`，按数组顺序展示 Block；只展示元数据中的创建时间和状态。时间以 Unix 秒读取，显示上海时区日期时间。`id`、`entity_id`、`schema_version` 和附加 metadata 不显示。未知 Block 显示简短占位，前后已知内容继续可读，不输出未知载荷。

`MarkdownBlock` 将 content 交给局部 `StreamdownRenderer`；当前打开的块随 SSE 增量以 streaming 模式渲染，已闭合块和历史使用 static。原有 HTML 清理、KaTeX 安全配置、数学定界符转换和代码样式继续复用。思考和工具过程保留；有结构化快照时不重复展示旧正文和旧 sources，没有快照的历史仍走原展示路径。

MessageRenderer 跨全部 Markdown Block 收集首次引用顺序，角标和来源列表共用编号；忽略来源数组的到达顺序，未引用条目不显示，同一来源重复引用使用同一编号。引用通过 remark AST 插件转换为角标，代码、公式及已有链接中的文本不参与转换。来源 JSON 尚未到达时显示不可跳转的待补全数字角标，不显示原始 ID；记录到达后启用跳转。流式未闭合标记暂不显示，最终快照校准后无效引用显示“引用不可用”。

`ReferencesRenderer` 展示 title、中文 type、已有作者、年份、venue、DOI 与来源链接。超过两位作者显示第一作者加 et al.，悬停可查看完整列表；缺少作者时可显示来源域名，不补造作者。可选字段缺失时省略对应元素。

来源标题和主跳转入口按以下优先级选择：`type=paper` 且有知识库 `entity_id` 时，复用 `paperHref(entity_id)` 进入站内论文详情页；否则使用无凭证的 HTTP(S) 来源 URL，再退回 doi.org 链接；均不可用时仅显示文字。站内使用 Next Link 在当前页导航并关闭预取，外部链接在新标签打开，使用 noopener/noreferrer；DOI 字段仍保留独立的原始来源入口。正文角标继续定位到本消息的来源条目。

Prompt 要求模型将知识库工具返回的真实 paper_id 原样保留到 entity_id；外部来源没有知识库 ID 时省略该字段，不根据标题或 arXiv 编号猜测。站内链接由 Web 构造，不改写协议中的原始 url，不新增检索、外部抓取或工具调用，不改变 Agent loop 的执行策略。

## 验证

在 `apps/agent` 执行 `uv run --locked python -m pytest tests -q`；共享契约在 `packages/agent-contracts` 执行 `uv run --group dev python -m pytest tests -q`。

`test_model_output.py` 验证逐字符边界、围栏示例、JSON 截断/错误/超限、无效字段、首次引用顺序、未引用来源过滤及跨回复去重。`test_message_blocks.py` 使用脚本化 Provider 验证模型 JSON 生成来源、工具不自动选来源、历史资料复用、正文 delta/最终文本不泄漏 JSON、事件重建/去重、异常保留、反问、Checkpoint 和 Worker 报告。`test_worker_takeover.py` 经过真实 Agent API、Control SQL 和 Worker，核对事件落库后的最终消息；SQLite 测试不代表生产 PostgreSQL 并发验收。

Backend 的 `tests/test_agent_message_blocks.py` 验证 Gateway v1/v2、产品 SSE、断线游标、重试和历史接口的数据一致性；`tests/test_agent_message_postgres.py` 在显式配置 `TEST_AGENT_MESSAGE_DATABASE_URL` 的隔离测试库中验证真实 JSONB 往返、连接重建、旧数据迁移和无效载荷不落库。测试库须先应用 Backend 迁移，禁止将该测试变量指向业务数据库。

Web 在 `apps/web` 执行 `pnpm test`、`pnpm typecheck`，并对改动文件执行 ESLint。`tests/agent/message-blocks.test.ts` 验证纯协议及组装器；`message-stream.test.ts` 使用 mock fetch 和分片 ReadableStream 验证真实 Client/SSE 解析到状态及历史恢复的完整数据链路，不调用真实 Agent 或模型。

`tests/agent/message-rendering.test.ts` 验证引用转换、展示字段及链接规则。浏览器联调脚本位于仓库根目录 `tests/visual/agent-message-blocks.mjs`，使用独立 Next 开发服务和 mock Backend 的真实 HTTP/SSE，验证 Client → 状态 → React DOM、流式内容、来源跳转、刷新恢复、手机布局与兼容降级。先在 `apps/web` 启动 `pnpm exec next dev --hostname 127.0.0.1 --port 3311`，再从仓库根运行 `node tests/visual/agent-message-blocks.mjs --next http://127.0.0.1:3311 --out <artifact-directory>`。脚本使用本机 Edge，可用 `EDGE_PATH` 指定路径，保留截图和隔离浏览器目录，不清理现有文件。此联调不调用真实模型，也不代表生产环境验收。

## V2 集成与故障降级

产品接口仅使用 `/api/v2/agent/*`，Agent 通信仅使用 `/internal/v2/*`；
`submission_gateway()` 选择唯一的 `agent_gateway/gateway.py`。消息 `schema_version=1`
独立于执行 API 版本。Gateway 校验消息并记录无效载荷诊断，保持原始数据和事件顺序；
MessageCapture 负责拒绝无效或不一致的快照，不阻塞明确执行终态落库。

最终报告与事件快照一致时保存原快照；报告未带消息时仅使用状态匹配的完整 message_end。
报告与事件不一致、状态不匹配、结构无效或缺少完整快照时，记录诊断、返回 message=null，
保留普通文本、Timeline、transcript 和 Usage。失败报告无需完整消息即可关闭 Turn。
Web 最终 result 的显式 null 清除流式结构化状态，历史缺失字段和传输中断保留原有兼容行为。

论文助手将上轮全部 Markdown Blocks 和实际 References 编码为原有 assistant transcript 的文本，
保留 DOI、URL、实体 ID 及来源信息，不将 AIMessage 作为 Provider 消息。
重试继续使用冻结的 operation.request 与原 idempotencyKey。

会话导出通过 Feature 的 sessionExportMessages 投影。JSONL 保留完整 message（含 metadata、
Blocks 和 References），HTML 按顺序输出全部 Markdown Blocks 并展示参考来源；
所有正文、标题和来源均经 HTML 转义，URL 以文本呈现。旧格式仍读取原 content。
HTML 沿用既有超大会话导出预算和截断提示。
