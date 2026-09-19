# Agent 基座（第二阶段迁移）

本目录描述 `integration/20260919` 当前已接入的 Backend Agent 基础设施。代码来自 `feat/SZDR` 的选择性迁移；本阶段没有接入 Deep Research Skill、Agent 产品前端或 legacy retrieval。

## 结构与调用边界

`apps/backend/app/services/agent/` 保留现有 Runtime 实现：`runtime.py` 执行模型与工具循环，`types.py` 定义消息、事件和运行结果，`provider.py` 提供 OpenAI 兼容流式模型调用，`tools.py` 负责注册、参数校验和执行。`context.py`、`compaction.py`、`memory.py` 管理上下文和 checkpoint；`skills.py` 管理 Skill 发现、读取和工具加载；`prompt_templates.py` 提供独立的模板加载和参数展开机制。`workspace.py`、`ask_user.py`、`netguard.py`、`json_repair.py`、`export.py` 是配套能力。

`service.py` 是应用组合根，按请求组装 Runtime，并通过适配工具复用现有 `KnowledgeService`、`web_search`、`document_parser` 和 Chat 附件仓库。论文检索工具调用路径为 Agent Tool → `KnowledgeService` → `integrations/knowledge`；没有旧 `/search/explore` 或 `services/retrieval.py` 链路。`read_paper` 与 `fetch_url` 随 Runtime 注册，图表和图片工具在有工作区时注册；外部搜索未配置时由工具返回明确错误。没有业务 Skill、工作区或可选搜索服务时，Runtime 仍可初始化。

## HTTP 接入

`app/main.py` 注册 `app/api/agent.py` 的 `/api/v1/agent` router。当前接口包括运行 SSE（`POST /run`）、运行中插话、配置查询、工作区创建与文件上传、会话文件及图片读取、会话导出。运行接口接收 prompt、history、可选模型、Skill、附件和工作区参数；不会自动创建产品会话或持久化聊天记录。身份及 BFF 访问规则沿用 `app.core.identity`。

Skill 默认从 `apps/backend/skills/` 发现第一方 Skill，并可从 `skills_vendor/` 发现外部 Skill；这两个目录可以不存在或为空。`SKILLS_VENDOR` 为空时启用全部 vendor Skill，设为 `none` 时禁用，逗号列表用于白名单。显式指定不存在的 Skill 会返回参数错误。当前仓库不带业务 Skill，`/config` 的 skills 列表默认为空。

## 配置与依赖

模型使用现有 DashScope / DeepSeek 配置和 `AI_TIMEOUT_SEC`。新增的可选环境变量见 `apps/backend/.env.example`：`SKILLS_VENDOR`、`AGENT_DISABLE_THINKING`、`EXA_API_KEY`。`pyproject.toml` 只增加基座实际使用的 PyYAML、lxml、matplotlib 和 CLI 使用的 python-dotenv；Pillow 由 matplotlib 的锁定依赖提供。工作区默认位于 `apps/backend/workspace/`，作为运行时数据被 Git 忽略。

## 当前边界

- `apps/backend/skills/deep-research/`、业务 prompt 和 Web Agent 产品代码尚未迁入。模板加载机制已迁入，但当前没有预置业务模板。
- 工作区文件使用本地文件系统；在无共享持久存储的多实例或 Serverless 环境中，跨实例读取和长期保留没有保证。运行中插话通道也只在当前进程有效。
- Agent Runtime 的单次运行不自动写入 Chat 会话数据库；调用方负责保存 history 和处理 SSE 结果。
- 不调用真实付费模型的验证可用 `uv run python -m unittest -q tests.test_agent tests.test_agent_api tests.test_agent_memory tests.test_agent_workspace tests.test_edit_fuzzy tests.test_agent_skills`。
