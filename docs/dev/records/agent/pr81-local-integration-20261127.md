# PR #81 本地集成验收（2026-11-27）

## 范围与提交

- 仓库：D:/Projects/Shenzhi-ResearchOS-agent-message-integration
- 分支：integration/agent-message-blocks-v2
- Fetch 后目标：dabca7405d729ced37e963cb849a212108ee422c
- Fetch 后源：5c4e232ce638d1f4f4441ea6d3af837a179adbd0
- Merge Base：f04e01ac11f95e75f5c29bdfa0e6d4025c94dbc3
- 分叉目标/源独有提交数：14 / 6。从源创建 Worktree 后 merge 目标，未 rebase、未 cherry-pick。
- 最终 merge commit 及完整 diff stat 由交付时 git rev-parse HEAD、git diff --stat origin/feat/agent-platform...HEAD 输出，避免文档自引用 SHA。

## Git 冲突

1. apps/backend/app/api/agent.py：保留 submission_gateway() 并加入 MessageCapture。
2. apps/web/clients/backend/agent.ts：保留 agentApiJson、V2 请求路径，融合历史消息解析。
3. apps/web/features/papers/[id]/use-paper-agent.ts：保留 operation.request 与重试幂等键，并增加事件回调。
4. docs/agent/contracts.md：保留 V1 退役说明，更新消息契约及 schema_version 区别。

## P0 / P1 修复与关键验收

| 场景 | 实现与证据 |
|---|---|
| 正常事件与报告一致 | 原始全载荷保存，message-blocks 与 PostgreSQL 测试 |
| 报告缺 message、完整 message_end | 同 Run 且终态匹配时使用事件快照 |
| Worker 在 message_start 后交付失败 | 真实 Worker 回归封存 failed 报告；Backend 回归保存 failed，不停留 running |
| message_end done、最终 failed | 不改消息状态，丢弃快照，Turn 以 failed 结束 |
| 消息状态与报告不符 | 诊断并丢弃，原文、Timeline、transcript、Usage 继续保存 |
| 结构化消息缺失 | 普通文本及旧 Timeline 可恢复；Web 最终 null 清除不可信部分状态 |
| 失败 Run 后重试 | run_start 清空消息捕获，最后成功 Run 独占最终快照 |
| Backend 重启 | 隔离 PostgreSQL 丢弃进程状态与连接后，历史和 SSE 仍一致 |
| SSE 重复重放 | 数值 event ID 高水位去重，快照替换，不重复追加 Block |
| 同键请求/计量 | 原目标提交指纹、恢复与 Usage 保留；Session 幂等及 A-line 回归 |
| 论文助手后续对话 | 全部 Block 正文和真实 DOI、URL、entity_id 作为原 assistant transcript 文本传递 |
| 导出 | Feature 实际投影测试、Backend JSONL 全载荷和 HTML 全 Block/来源转义测试 |

Gateway 对展示载荷校验失败时记录诊断，保留原始载荷，交给 MessageCapture 丢弃；不会因为展示协议拒绝读取已封存 ExecutionReport。没有执行报告时仍不得虚构终态。失败 Run 顺序、投影租约、usage settlement、原始 transcript 和 V2 通信边界保持目标实现。

## 最终测试命令与结果

命令 cwd 已注明。测试未使用原工作区 .env，也未配置任何真实上游。

| cwd | 命令 | 结果 |
|---|---|---|
| apps/agent | uv run python -m pytest ../../packages/agent-contracts/tests/test_messages.py -q | 17 passed |
| apps/agent | uv run python -m pytest tests/unit -q | 256 passed，124 subtests passed；包含 Worker 接管和两个交付故障场景 |
| apps/agent | uv run python -m pytest tests/test_a_line_persistence.py tests/test_formal_plans.py -q | 48 passed，9 subtests passed；39 个既有 SQLite datetime adapter deprecation warning |
| apps/backend | uv run python -m unittest discover -s tests -q | 558 tests，OK，83 个既有外部/数据库可选测试未配置环境而跳过；未添加 skip |
| apps/backend | uv run alembic heads | 唯一头 029_agent_message |
| apps/backend | uv run alembic upgrade head | 新建隔离测试库从空库完整升级至 029，028 衔接正确 |
| apps/backend | uv run python -m unittest tests.test_agent_persistence tests.test_agent_message_postgres tests.test_agent_uploads -q | 显式配置隔离测试库后 20 tests 全部通过，0 skip |
| apps/web | pnpm install --frozen-lockfile | 按现有锁文件成功，未新增依赖 |
| apps/web | pnpm test | 476 tests 全部通过，0 skip |
| apps/web | pnpm typecheck | 退出码 0 |
| apps/web | pnpm build | 退出码 0；以本机测试 BETTER_AUTH_URL/SECRET 构建，无真实 DB |
| apps/web | pnpm exec eslint features/agent-chat/components features/agent-chat/message-state.ts features/agent-chat/session-export.ts features/agent-chat/shenzhi-ai-page.tsx features/papers/[id]/paper-agent.ts features/papers/[id]/use-paper-agent.ts features/papers/[id]/components/paper-assistant-panel.tsx clients/backend/agent.ts clients/backend/agent-message.ts | 退出码 0，无警告 |
| 仓库根 | uv run --project apps/backend python -m compileall -q apps/backend/app | 退出码 0 |
| 仓库根 | node tests/visual/agent-message-blocks.mjs --next http://127.0.0.1:3311 --out .tmp-agent-message-browser | 六组检查通过，postCount=1，browserErrors=[]，桌面/手机截图保留并检查 |
| 仓库根 | git diff --check --cached | 退出码 0，无冲突标记 |

PostgreSQL 使用新建 postgres:16-alpine 测试容器 shenzhi-message-integration-test，仅绑定本机 127.0.0.1:55489，无业务卷。测试变量 CHAT_DATABASE_URL 与 TEST_AGENT_MESSAGE_DATABASE_URL 仅指向该库。已验证 JSONB、旧行 NULL、完整消息与重启恢复；没有连接/迁移正式数据库。验收后测试容器已停止，开发服务已关闭。

### 调试期间失败及处理

- 初始 Fetch 被只读 Git 元数据沙箱拒绝；提升本地 Git 元数据权限后 Fetch 成功，无远程配置变更。
- 初次 Backend 使用 pytest 命令缺少 app 搜索路径而收集失败；改用仓库 README 的 uv run python -m unittest 后完整通过。
- 初次尝试 npm ci 因项目使用 pnpm 锁文件而失败；使用 pnpm install --frozen-lockfile 后完成，没有生成 npm 锁文件或变更依赖。
- 首轮有报告事件故障使旧“无报告”fixture 暴露与业务假设不符；将该 fixture 明确设置为无报告，保留全部原断言；新增独立有报告终态故障回归。
- 通用消息校准原测试要求 null 保留部分状态；保留原断言和默认行为，只在终态 result 显式启用清理，新增回归覆盖。
- 导出抽离后 ESLint 两个无用类型警告已移除。
- 首轮构建退出码 0 但有默认认证配置警告；最后构建显式使用本机测试配置后无此警告。

## 未解决的边界与风险

- 未调用真实 LLM、搜索或科研服务；浏览器使用 V2 Mock，不能据此声称生产联调完成。
- 全量 Backend 原有外部依赖可选测试仍按原条件跳过；所需消息/Session/附件 PostgreSQL 持久化另行在隔离库全部执行。
- 沿用现有 HTML 大会话导出字符预算与截断提示；JSONL 保存完整消息，HTML 非 Markdown 富格式转换，正文与来源均安全转义。
- Gateway 记录无效展示载荷诊断，但保持原始数据；实时 Web 若遇无效协议仍使用原有连接错误/恢复流程，最终历史以 Backend 已保存的降级结果为准。
- 只保证已得到明确 ExecutionReport 的消息异常不阻塞终态；未取得报告的断连/不确定提交继续 running 以便原机制安全恢复。
- 保留原 Runtime Checkpoint presentation/event_seq 恢复能力；未新增 Worker Runtime 或跨进程会话体系。

## 逐文件修改原因（相对目标分支）

| 文件 | 原因 |
|---|---|
| `apps/agent/src/agent_app/application/composition.py` | 融合 Message Blocks 至目标 Agent Platform 现有边界，不新增并行执行架构。 |
| `apps/agent/src/agent_app/execution/memory.py` | 沿用原 Runtime/Provider/工具边界，加入正文/来源流式拆分、块组装、引用去重及 Checkpoint 恢复。 |
| `apps/agent/src/agent_app/execution/message_stream.py` | 沿用原 Runtime/Provider/工具边界，加入正文/来源流式拆分、块组装、引用去重及 Checkpoint 恢复。 |
| `apps/agent/src/agent_app/execution/model_output.py` | 沿用原 Runtime/Provider/工具边界，加入正文/来源流式拆分、块组装、引用去重及 Checkpoint 恢复。 |
| `apps/agent/src/agent_app/execution/references.py` | 沿用原 Runtime/Provider/工具边界，加入正文/来源流式拆分、块组装、引用去重及 Checkpoint 恢复。 |
| `apps/agent/src/agent_app/execution/runtime.py` | 沿用原 Runtime/Provider/工具边界，加入正文/来源流式拆分、块组装、引用去重及 Checkpoint 恢复。 |
| `apps/agent/src/agent_app/execution/tools.py` | 沿用原 Runtime/Provider/工具边界，加入正文/来源流式拆分、块组装、引用去重及 Checkpoint 恢复。 |
| `apps/agent/src/agent_app/execution/types.py` | 沿用原 Runtime/Provider/工具边界，加入正文/来源流式拆分、块组装、引用去重及 Checkpoint 恢复。 |
| `apps/agent/src/agent_app/worker/host.py` | 融合 Message Blocks 至目标 Agent Platform 现有边界，不新增并行执行架构。 |
| `apps/agent/tests/unit/test_agent.py` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `apps/agent/tests/unit/test_agent_knowledge_tools.py` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `apps/agent/tests/unit/test_message_blocks.py` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `apps/agent/tests/unit/test_model_output.py` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `apps/agent/tests/unit/test_worker_takeover.py` | 保留 V2 execution_id/lease/fencing，新增 message_start/message_end 后事件交付失败并封存 failed 报告的测试。 |
| `apps/backend/app/api/agent.py` | 保留统一 V2 产品提交/幂等恢复，SSE 增加 MessageCapture 与终态快照。 |
| `apps/backend/app/models/agent_session.py` | 在现有 Backend Session/Turn 所有权和持久化体系内保存完整消息，保留 transcript、投影租约和旧历史。 |
| `apps/backend/app/services/agent_gateway/client.py` | 已读取封存报告时，事件读取故障不阻塞终态投影；无报告仍保持恢复语义。 |
| `apps/backend/app/services/agent_gateway/gateway.py` | 唯一 V2 Gateway 增加 AIMessage 与六类事件校验；诊断无效载荷，保留原始数据及顺序。 |
| `apps/backend/app/services/agent_sessions/entities.py` | 在现有 Backend Session/Turn 所有权和持久化体系内保存完整消息，保留 transcript、投影租约和旧历史。 |
| `apps/backend/app/services/agent_sessions/export.py` | HTML 顺序输出全部 Markdown Blocks 和来源，所有模型字段转义；JSONL 保留原始完整载荷。 |
| `apps/backend/app/services/agent_sessions/live.py` | 在现有 Backend Session/Turn 所有权和持久化体系内保存完整消息，保留 transcript、投影租约和旧历史。 |
| `apps/backend/app/services/agent_sessions/messages.py` | 最终快照对比、状态校验、事件快照回退；异常丢弃结构化消息并记录诊断，不阻塞 Turn 终态。 |
| `apps/backend/app/services/agent_sessions/postgres_repository.py` | 在现有 Backend Session/Turn 所有权和持久化体系内保存完整消息，保留 transcript、投影租约和旧历史。 |
| `apps/backend/app/services/agent_sessions/repository.py` | 在现有 Backend Session/Turn 所有权和持久化体系内保存完整消息，保留 transcript、投影租约和旧历史。 |
| `apps/backend/app/services/agent_sessions/service.py` | 在现有 Backend Session/Turn 所有权和持久化体系内保存完整消息，保留 transcript、投影租约和旧历史。 |
| `apps/backend/app/services/agent_sessions/timeline.py` | 在现有 Backend Session/Turn 所有权和持久化体系内保存完整消息，保留 transcript、投影租约和旧历史。 |
| `apps/backend/migrations/versions/029_agent_message.py` | 029_agent_message 衔接 028_formal_plans，增加可空 JSONB，旧记录不回填。 |
| `apps/backend/tests/test_agent_message_blocks.py` | V2 全载荷一致性、快照异常终态、失败重试、恢复、HTML/JSONL 安全导出。 |
| `apps/backend/tests/test_agent_message_postgres.py` | 隔离 PostgreSQL JSONB 往返、Backend 重启恢复、迁移旧行 NULL 及非法消息不落库。 |
| `apps/backend/tests/test_agent_sessions.py` | 无报告断连场景显式隐藏报告，继续验证不得虚构终态；与新有报告故障场景区分。 |
| `apps/web/clients/backend/agent-message.ts` | 融合 Message Blocks 至目标 Agent Platform 现有边界，不新增并行执行架构。 |
| `apps/web/clients/backend/agent.ts` | 保留 agentApiJson/agentApiPath、V2 与错误处理；增加事件、结果及历史消息解析。 |
| `apps/web/components/renderers/markdown-elements.tsx` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/components/renderers/streamdown-renderer.tsx` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/features/agent-chat/components/block-renderer.tsx` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/features/agent-chat/components/blocks/markdown-block.tsx` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/features/agent-chat/components/citation-markers.ts` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/features/agent-chat/components/message-presentation.ts` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/features/agent-chat/components/message-renderer.tsx` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/features/agent-chat/components/references-renderer.tsx` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/features/agent-chat/components/streamdown-renderer.tsx` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/features/agent-chat/message-state.ts` | Run 隔离、SSE ID 去重、快照校准；终态显式 null 清除被拒绝的结构化展示。 |
| `apps/web/features/agent-chat/session-export.ts` | Feature 内统一导出投影，保留结构化独有的 Turn、全部 Blocks/References 和旧格式。 |
| `apps/web/features/agent-chat/session-state.ts` | 融合 Message Blocks 至目标 Agent Platform 现有边界，不新增并行执行架构。 |
| `apps/web/features/agent-chat/shenzhi-ai-page.tsx` | 主 Agent 页面接入共享消息状态与渲染、终态校准及完整导出，避免正文重复。 |
| `apps/web/features/agent-chat/timeline-view.tsx` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/features/papers/[id]/components/paper-assistant-panel.tsx` | 统一 Block/Reference 展示、引用跳转和安全 Markdown；保留思考及工具过程。 |
| `apps/web/features/papers/[id]/paper-agent.ts` | 共用消息状态；后续 transcript 携带全部正文及实际来源信息，不把 AIMessage 作为 Provider transcript。 |
| `apps/web/features/papers/[id]/use-paper-agent.ts` | 保留 pendingPaperAgentRetry、冻结 operation.request 与原始幂等键，在此基础上添加消息回调。 |
| `apps/web/tests/agent/markdown-math.test.ts` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `apps/web/tests/agent/message-blocks.test.ts` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `apps/web/tests/agent/message-fixtures.ts` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `apps/web/tests/agent/message-rendering.test.ts` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `apps/web/tests/agent/message-stream.test.ts` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `apps/web/tests/agent/paper-assistant.test.ts` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `docs/agent/contracts.md` | 同步消息契约、当前实现、架构边界或保留源分支开发记录。 |
| `docs/agent/message-blocks.md` | 同步消息契约、当前实现、架构边界或保留源分支开发记录。 |
| `docs/agent/session-persistence.md` | 同步消息契约、当前实现、架构边界或保留源分支开发记录。 |
| `docs/dev/records/agent/message-blocks-backend-20261126.md` | 同步消息契约、当前实现、架构边界或保留源分支开发记录。 |
| `docs/dev/records/agent/message-blocks-phase1-20261125.md` | 同步消息契约、当前实现、架构边界或保留源分支开发记录。 |
| `docs/dev/records/agent/message-blocks-rendering-20261126.md` | 同步消息契约、当前实现、架构边界或保留源分支开发记录。 |
| `docs/dev/records/agent/message-blocks-web-20261126.md` | 同步消息契约、当前实现、架构边界或保留源分支开发记录。 |
| `docs/dev/records/agent/model-selected-references-20261126.md` | 同步消息契约、当前实现、架构边界或保留源分支开发记录。 |
| `docs/engineering/architecture-confirmation.md` | 同步消息契约、当前实现、架构边界或保留源分支开发记录。 |
| `packages/agent-contracts/src/agent_contracts/__init__.py` | 共享结构化消息与事件契约；消息 schema_version=1 独立于执行 API V2。 |
| `packages/agent-contracts/src/agent_contracts/messages.py` | 共享结构化消息与事件契约；消息 schema_version=1 独立于执行 API V2。 |
| `packages/agent-contracts/src/agent_contracts/wire.py` | 共享结构化消息与事件契约；消息 schema_version=1 独立于执行 API V2。 |
| `packages/agent-contracts/tests/test_messages.py` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |
| `tests/visual/agent-message-blocks.mjs` | 保留原业务语义，验证消息协议、引用、流式状态、展示或浏览器 V2 Mock 链路。 |

## 保护检查

原工作区仍为 feat/billing-subscription，git status --short 为空；所有代码写入指定独立 Worktree。
目标提交将是最终 merge commit 的祖先。仅本地 commit，没有 Push、没有合并 GitHub PR、没有操作真实数据库。
完整测试输出与浏览器截图留在独立工作区 .tmp-agent-message-browser 中，不进入仓库提交。
