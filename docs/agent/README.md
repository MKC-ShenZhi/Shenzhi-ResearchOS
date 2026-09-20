# Agent Framework 与产品接入

**Agent Framework migration completed.** `integration/20260919` 已完成从 `feat/SZDR` 到 ShenZhi 主工程的 Agent Runtime、消息与事件类型、Provider、Tool、Context / Compaction、Memory / Checkpoint、Skill framework、Workspace、基础 policy、prompt/template infrastructure、export、安全与网络辅助模块迁移，并接入 FastAPI Agent API 和 Web `/agents` 产品入口。这些能力现为 ShenZhi 可继续开发的正式基座。

**Deep Research Skill Migration = DONE。** 第一方 `deep-research` 位于 `apps/backend/skills/deep-research/`，可在 `/agents` 选择，也可用 `/research <主题>` 触发。Agent 使用既有 Tool → `KnowledgeService` → `integrations/knowledge` 检索论文；legacy retrieval 未迁入。2026-09-20 的真实 Backend + Web 验收记录见 [verification-2026-09-20.md](verification-2026-09-20.md)。

## 结构与调用边界

`apps/backend/app/services/agent/` 保留现有 Runtime 实现：`runtime.py` 执行模型与工具循环，`types.py` 定义消息、事件和运行结果，`provider.py` 提供 OpenAI 兼容流式模型调用，`tools.py` 负责注册、参数校验和执行。`context.py`、`compaction.py`、`memory.py` 管理上下文和 checkpoint；`skills.py` 管理 Skill 发现、读取和工具加载；`prompt_templates.py` 提供独立的模板加载和参数展开机制。`workspace.py`、`ask_user.py`、`netguard.py`、`json_repair.py`、`export.py` 是配套能力。

`service.py` 是应用组合根，按请求组装 Runtime，并通过适配工具复用现有 `KnowledgeService`、`integrations/web_search/provider.py`、`services/chat/attachments.py` 和 Chat 附件仓库。论文检索工具调用路径为 Agent Tool → `KnowledgeService` → `integrations/knowledge`；没有旧 `/search/explore` 或 `services/retrieval.py` 链路。`read_paper` 与 `fetch_url` 随 Runtime 注册，图表和图片工具在有工作区时注册；外部搜索未配置时由工具返回明确错误。没有业务 Skill、工作区或可选搜索服务时，Runtime 仍可初始化。

## HTTP 接入

`app/main.py` 注册 `app/api/agent.py` 的 `/api/v1/agent` router。当前接口包括运行 SSE（`POST /run`）、运行中插话、配置查询、工作区创建与文件上传、会话文件及图片读取、会话导出。运行接口接收 prompt、history、可选模型、Skill、附件和工作区参数；不会自动创建产品会话或持久化聊天记录。身份及 BFF 访问规则沿用 `app.core.identity`。

Skill 默认从 `apps/backend/skills/` 发现第一方 Skill，并可从 `skills_vendor/` 发现外部 Skill；目录可以不存在或为空。`SKILLS_VENDOR` 为空时启用全部 vendor Skill，设为 `none` 时禁用，逗号列表用于白名单。显式指定不存在的 Skill 会返回参数错误。当前 `/config` 的 skills 列表包含 `deep-research`。

## 配置与依赖

模型使用现有 DashScope / DeepSeek 配置和 `AI_TIMEOUT_SEC`。新增的可选环境变量见 `apps/backend/.env.example`：`SKILLS_VENDOR`、`AGENT_DISABLE_THINKING`、`EXA_API_KEY`。`pyproject.toml` 只增加基座实际使用的 PyYAML、lxml、matplotlib 和 CLI 使用的 python-dotenv；Pillow 由 matplotlib 的锁定依赖提供。工作区默认位于 `apps/backend/workspace/`，作为运行时数据被 Git 忽略。

## 已完成的产品接入与后续边界

- `/agents` 是 Agent 主入口：`ShenzhiAiPage` 经 `clients/backend/agent.ts` 向 `/api/v1/agent/run` 发起 POST SSE，由 `AgentRuntime` 完成模型与工具循环。页面处理增量正文与 reasoning、工具调用和结果、插话、反问、压缩、警告及终态，并提供工作区上传、报告展示和导出。
- Agent 会话阶段性保存在浏览器 `localStorage`（`shenzhi-agent-sessions`），包含轮次、过程、工具、插话、报告、来源、反问、用量和分叉信息。旧 Chat 仍使用 Backend/PostgreSQL 会话，但已退出 `/agents` 主入口；Agent durable Backend session 留待后续实现。
- `apps/backend/skills/deep-research/` 已接入；在 `/agents` 选择 Skill 或输入 `/research <主题>` 会强制加载其指引并挂载会话工作区。报告写入 `report.md` 后，由 Backend 读回到运行结果的 `output.report`，页面可打开报告。普通 Agent 请求仍可使用基础工具；模板加载机制已迁入，但当前没有预置业务模板。
- legacy retrieval 未迁入；论文工具仍通过 `KnowledgeService → integrations/knowledge`。
- 工作区文件使用本地文件系统；在无共享持久存储的多实例或 Serverless 环境中，跨实例读取和长期保留没有保证。运行中插话通道也只在当前进程有效。
- 当前 Stop 使用浏览器流连接取消；Backend 尚无独立的 server-side cancel API。
- **P0 before public production:** `run_command` 需要宿主机 shell / env sandbox 与隔离。本阶段保留现有 netguard、路径禁闭及命令检查，不放宽安全边界。
- 不调用真实付费模型的验证可用 `uv run python -m unittest -q tests.test_agent tests.test_agent_api tests.test_agent_memory tests.test_agent_workspace tests.test_edit_fuzzy tests.test_agent_skills tests.test_deep_research_skill`。
