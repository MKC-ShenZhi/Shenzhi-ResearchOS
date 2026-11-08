# Agent Framework 与产品接入

Agent Runtime、消息与事件类型、Provider、Tool、Context / Compaction、Memory / Checkpoint、Skill framework、Workspace、基础 policy、prompt/template infrastructure、export、安全与网络辅助模块已从 `feat/SZDR` 迁入 ShenZhi 主工程，并接入 FastAPI Agent API 和 Web `/agents` 产品入口，是 ShenZhi 继续开发的正式基座，也是唯一的对话链路；匿名身份引导与登录后认领见 [认证架构](../auth/ARCHITECTURE.md#anonymous-identity-and-claim)。

第一方 `deep-research` Skill 位于 `apps/backend/skills/deep-research/`，可在 `/agents` 选择，也可用 `/research <主题>` 触发。Agent 使用既有 Tool → `KnowledgeService` → `integrations/knowledge` 检索论文；legacy retrieval 未迁入。它与前端原型页 `/agents/deep-research`（见 [Deep Research 页面说明](../deep-research/README.md)）无关。历史验收记录见 [verification-2026-09-20.md](../dev/records/agent/verification-2026-09-20.md)。

## 结构与调用边界

`apps/backend/app/services/agent/execution/` 包含 `runtime.py`（模型与工具循环）、`provider.py`（模型请求/事件协议）、`types.py`（消息、事件和结果）、`tools.py`（工具注册与执行）、`context.py`、`compaction.py`、`memory.py`（Checkpoint 协议与内存实现）和 `json_repair.py`。`capabilities/` 包含知识、论文、网页搜索/抓取、HTML 正文解析、图表和用户提问等 Agent Tool 包装。`extensions/` 包含 Skills、Workspace、附件、导出和模板。`app/` 放运行装配、事件桥接和产品策略。根目录原模块路径保留兼容别名。OpenAI 兼容流式传输位于 `integrations/llm/agent_stream.py`；公共网页抓取和安全校验位于 `integrations/public_web/`，Exa 图片搜索位于 `integrations/web_search/exa_images.py`，论文来源候选解析位于 `integrations/paper_resource/agent_sources.py`。能力层负责 PDF/HTML 解析、Agent 输出格式与 Workspace 文件写入；Integration 负责上游协议、凭证与有界网络访问。

`service.py` 是保留给 API、会话服务与 CLI 的稳定入口；实际装配位于 `app/composition.py`，事件桥接与运行中插话/停止通道位于 `app/events.py`。装配通过适配工具复用现有 `KnowledgeService` 与 `integrations/web_search/provider.py`；附件上下文由 `extensions/attachments.py` 基于 `agent_uploads` 暂存文本组装，按模式的采样温度、时间与工具预算在 `app/policies.py`。论文检索工具调用路径为 Agent Tool → `KnowledgeService` → `integrations/knowledge`。`read_paper` 与 `fetch_url` 随 Runtime 注册，图表和图片工具在有工作区时注册；外部搜索未配置时由工具返回明确错误。

## HTTP 接入

`app/main.py` 注册 `app/api/agent.py` 的 `/api/v1/agent` router。接口分两类：

- 持久化会话：`/sessions*` 创建、分页、详情、重命名、删除、旧本地会话导入，`POST /sessions/{id}/run` 基于后端历史启动一轮 SSE，`GET /sessions/{id}/run/stream` 续接运行中的事件流。Session 与 Turn 存于 PostgreSQL（Migration `007_agent_sessions`），Backend 是 source of truth，详见 [Agent 会话持久化](session-persistence.md)。
- 通用能力：无状态运行 SSE（`POST /run`，接收 prompt、history、可选模型、Skill、附件和工作区参数，不创建或持久化会话）、运行中插话（`POST /run/{run_id}/steer`）、停止（`POST /run/{run_id}/stop`）、配置查询、附件上传（`/uploads`）、工作区创建与文件上传、会话文件及图片读取、会话导出。

身份及 BFF 访问规则沿用 `app.core.identity`。

Skill 默认从 `apps/backend/skills/` 发现第一方 Skill，并可从 `skills_vendor/` 发现外部 Skill；目录可以不存在或为空。`SKILLS_VENDOR` 为空时启用全部 vendor Skill，设为 `none` 时禁用，逗号列表用于白名单。显式指定不存在的 Skill 会返回参数错误。当前 `/config` 的 skills 列表包含 `deep-research`。

## 配置与依赖

模型使用共享的 [LLM Registry](../engineering/llm-api-foundation.md)，Provider 包括 DashScope、DeepSeek、智谱（`ZHIPU_*`）和 AutoDL（`AUTODL_*`），默认模型可用 `AI_AGENT_DEFAULT_MODEL` 指定，超时沿用 `AI_TIMEOUT_SEC`。Agent 相关的可选环境变量见 `apps/backend/.env.example`：`SKILLS_VENDOR`、`AGENT_DISABLE_THINKING`、`EXA_API_KEY`（图片搜索，未配置时该工具不可用）。`pyproject.toml` 只增加基座实际使用的 PyYAML、lxml、matplotlib 和 CLI 使用的 python-dotenv；Pillow 由 matplotlib 的锁定依赖提供。工作区默认位于 `apps/backend/workspace/`，作为运行时数据被 Git 忽略。

## 产品接入与后续边界

- `/agents` 是 Agent 主入口：无 `?session` 时渲染 `AgentHomePage`（新对话），带 `?session=<id>` 时渲染 `ShenzhiAiPage`。`ShenzhiAiPage` 经 `clients/backend/agent.ts` 的 `streamAgentSessionRun` 向 `/api/v1/agent/sessions/{id}/run` 发起 POST SSE，刷新后用 `attachAgentSessionRun` 续接运行中的流，由 `AgentRuntime` 完成模型与工具循环。页面处理增量正文与 reasoning、工具调用和结果、插话、反问、压缩、警告及终态，并提供工作区上传、报告展示和导出。
- 会话历史以 Backend Agent Session 为准，侧栏 `sidebar-chat-history.tsx` 通过 `/agent/sessions` 分页读取。旧浏览器 `localStorage`（`shenzhi-agent-sessions`）只在首次连接持久化仓库时一次性导入，不再作为数据源。
- 论文详情页问答：`features/papers/[id]/use-paper-agent.ts` 调用 `streamAgentRun`（`POST /api/v1/agent/run`），prompt 携带当前论文的 `paper_id` 与标题并要求模型调用 `read_paper`（`services/agent/capabilities/read_paper.py`）按 `paper_id` 经知识库详情取 PDF 全文；轮次只保存在页面状态中，不创建 Agent Session。
- `apps/backend/skills/deep-research/` 已接入；在 `/agents` 选择 Skill 或输入 `/research <主题>` 会强制加载其指引并挂载会话工作区。报告写入 `report.md` 后，由 Backend 读回到运行结果的 `output.report`，页面可打开报告。普通 Agent 请求仍可使用基础工具；模板加载机制已迁入，但当前没有预置业务模板。
- legacy retrieval 未迁入；论文工具仍通过 `KnowledgeService → integrations/knowledge`。
- 工作区文件使用本地文件系统；在无共享持久存储的多实例或 Serverless 环境中，跨实例读取和长期保留没有保证。
- Stop 调用 `POST /run/{run_id}/stop` 请求 Runtime 正常收尾并保存已有结果；插话与停止通道只在当前进程有效。
- **已知约束**：运行归属与事件缓冲是单进程内存状态（`services/agent_sessions/live.py`），续接、steer、stop 落到其他实例时无法命中；`deep` / `idea` / `doubt` 模式运行时限为 900 秒（`services/agent/application/policies.py`），超过 Vercel 函数 300 秒的执行上限。部署影响见 [deployment.md](../engineering/deployment.md)。
- **P0 before public production:** `run_command` 需要宿主机 shell / env sandbox 与隔离。本阶段保留现有 netguard、路径禁闭及命令检查，不放宽安全边界。
- 不调用真实付费模型的验证可用 `uv run python -m unittest -q tests.test_agent tests.test_agent_api tests.test_agent_memory tests.test_agent_workspace tests.test_edit_fuzzy tests.test_agent_skills tests.test_deep_research_skill`；会话、附件、`read_paper` 和匿名认领另见 `tests.test_agent_sessions`、`tests.test_agent_uploads`、`tests.test_agent_read_paper`、`tests.test_anonymous_claim`。
