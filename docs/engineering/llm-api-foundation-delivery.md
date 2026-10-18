# LLM API Foundation 第一阶段交付报告

## 分支与基线

- 基线：执行 `git fetch origin` 后的 `origin/dev`，commit `9b114b34cf536b558efeeb542a7449baabc36728`。
- 功能分支：`feat/llm-api-foundation`。创建前工作区干净，无同名分支冲突。
- 仅在该功能分支修改并提交；没有修改 remote，没有合并或改动本地 `dev` / `main`，没有推送。

## 交付架构

Chat / Agent 通过 `load_registry()` 获得类型化 ModelRegistry，使用 `resolve_model(model_id, purpose)` 得到 ModelSpec 与 ProviderConfig 组成的 ResolvedModel。Registry 提供 `list_models`、`default_model`、`public_models` 与兼容别名，是唯一模型信息来源。

Provider ID、协议、HTTPS 地址、环境凭据与启用状态独立于模型品牌。ModelSpec 绑定稳定 ID、Provider ID、上游型号、品牌、显示名称、用途能力、参数策略与输出限制。新会话持久化 `provider/model` ID；裸历史名称通过 Registry aliases 解析。两个原有 Provider 各自保留流处理实现，不增加网关、数据库或新的依赖。

Chat 的追问调用明确使用 Chat 默认模型；Agent 主调用与压缩摘要都经过同一 Agent Provider 和模型解析。模型解析不再依据全局 DashScope Key 选择所有请求的地址，也不通过型号正则判断推理能力。Chat、Agent 的输出预算分别保留，最终应用模型硬上限。

## 文件清单与职责

以下路径相对仓库根目录；共 32 个新增或修改文件。

| 文件 | 主要职责 |
| --- | --- |
| `apps/backend/app/integrations/llm/registry.py`（新增） | 类型、能力、配置校验、Resolver、默认模型、别名、公开目录 |
| `apps/backend/app/integrations/llm/resolver.py`（新增） | 声明加载、旧变量兼容、配置优先级、测试注入适配 |
| `apps/backend/app/integrations/llm/catalog.json`（新增） | 三家 Provider 与精确型号能力模板 |
| `apps/backend/app/core/config.py` | 保留旧 ModelConfig 入口，Key 不进入 repr |
| `apps/backend/app/integrations/llm/provider.py` | Chat 按解析结果注入连接信息和参数，追问独立解析 |
| `apps/backend/app/services/agent/provider.py` | Agent 路由、能力校验、Token 上限、精确参数降级和错误体保护 |
| `apps/backend/app/services/agent/runtime.py` | 共用模型解析，保留现有运行循环与测试注入 |
| `apps/backend/app/main.py` | 启动时校验 Registry 配置 |
| `apps/backend/app/api/chat.py`、`apps/backend/app/api/agent.py` | 两个 config API 同源、按用途过滤、兼容旧字段 |
| `apps/backend/tests/test_llm_registry.py`（新增） | 旧默认、冲突、别名、配置错误与稳定路由 |
| `apps/backend/tests/test_llm_routing.py`（新增） | 三家与第四家实际 Mock 请求、GLM 工具解析、版本声明及参数策略 |
| `apps/backend/tests/test_llm_config_api.py`（新增） | config 一致性、安全投影、GLM 产品 SSE、客户端不能覆盖凭据 |
| `apps/backend/tests/test_agent.py` | 更新任意 400 重试、原始错误外泄及规范化 ID 的断言 |
| `apps/web/clients/backend/model-types.ts`（新增） | Chat / Agent 共用公开模型契约 |
| `apps/web/clients/backend/chat/types.ts`、`apps/web/clients/backend/agent.ts` | 保留旧类型出口，扩展能力、Provider 与别名元数据 |
| `apps/web/features/chat/services/model-catalog.ts` | 禁用回退展示、后端别名选择、不可用原因 |
| `apps/web/features/chat/services/chat-config.ts` | 后端目录权威适配，取消静态可用性合并 |
| `apps/web/features/chat/components/composer.tsx` | 兼容历史选择；无可用模型时禁用 AI 发送，简单搜索继续可用 |
| `apps/web/features/chat/components/composer-control-picker.tsx` | 显示真实不可用原因，移除虚构订阅提示 |
| `apps/web/features/chat/components/model-provider-logo.tsx`、`model-provider-badge.tsx` | 智谱品牌保留，未知品牌通用回退、通义通用标识 |
| `apps/web/features/chat/components/agent-chat.tsx` | 初始历史模型通过后端别名选择 |
| `apps/web/features/agent-chat/shenzhi-ai-page.tsx` | Agent config 直接符合公共模型类型，移除强制类型转换 |
| `apps/web/tests/chat/model-config.test.ts`（新增） | 后端可用性权威、GLM 品牌、失败禁用、历史别名 |
| `.env.example`、`apps/backend/.env.example` | 配置入口、智谱变量、新默认模型与声明文件变量 |
| `docs/chat/README.md`、`docs/engineering/architecture-confirmation.md` | 同步运行规则与架构说明 |
| `docs/engineering/llm-api-foundation.md`（新增） | 完整配置、优先级、兼容、能力与扩展指南 |
| `docs/engineering/llm-api-foundation-delivery.md`（新增） | 本交付报告 |

## 三家 Provider 配置

在 Backend `.env` 中分别设置 Key，示例不包含真实凭据：

```ini
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-plus
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
ZHIPU_API_KEY=
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_MODEL=glm-4-plus
AI_DEFAULT_MODEL=dashscope/qwen-plus
AI_AGENT_DEFAULT_MODEL=deepseek/deepseek-chat
AI_ALLOWED_MODELS=
AI_TIMEOUT_SEC=90
AI_MODEL_REGISTRY_FILE=
```

Key 与具体型号均有效配置后才显示可用。智谱默认地址仅表示国内开放平台，其他地区 / 平台必须使用独立且配套的 Provider 声明。GLM 不限于该示例版本；未知版本可用于保守 Chat，Agent 所需能力需显式声明。

完整优先级：显式默认环境变量 > 文件 defaults > 旧 Provider 默认顺序。自定义声明按 ID 完整替换自动条目，文件内重复 ID、未知 Provider、非法默认与不受支持的参数 / 协议明确报错。各自 URL 环境变量只影响对应内置 Provider；Key 始终从相应环境变量加载。

## 第四家 Provider 的实际接入流程

1. 新建或修改 `AI_MODEL_REGISTRY_FILE` 指向的 JSON：增加 Provider ID、OpenAI Chat Completions 协议、HTTPS 地址与 `api_key_env` 名称。
2. 增加模型的稳定 ID、Provider ID、upstream_model、显示信息和明确能力；必要时配置别名与默认模型。
3. 在 Backend 环境配置对应 Key，重启并执行 Mock / 真实联调。
4. 可选新增品牌 Logo。现有未知品牌通用图标已能安全显示。

只需要修改部署声明 JSON / 环境配置；无需改 Chat、Agent、Runtime、两个 config API 或前端选择业务。`test_fourth_provider_and_duplicate_upstream_without_business_changes` 已用新声明验证两个 Adapter 的 Host、Bearer 和相同 upstream_model 路由隔离；仅第四家有 Key 时，也验证了无需旧 Key 即可成为默认模型。完整可复制 JSON 见 [接入指南](llm-api-foundation.md#声明第四家-openai-兼容-provider)。新协议才需要新 Adapter。

## 向后兼容与行为边界

- 原有 Chat / Agent 请求字段、SSE 事件、业务错误码、request_id、会话恢复及配置 JSON 外层保持兼容，不修改数据库 Schema。
- 仅旧变量时，DashScope 有 Key 则优先，否则 DeepSeek。`AI_ALLOWED_MODELS` 仍绑定该旧优先供应商。
- `default`、原裸型号和文件 aliases 均可解析。新生成完整 ID 固定 Provider；同名上游不会冲突。前端按后端 aliases 匹配历史选择。
- 旧裸名称没有历史 Provider 信息。迁移旧白名单、切换旧 Key 优先关系前，应通过文件 aliases 固定需要保留的历史路由；不再注册的完整 ID 会明确报错。
- 未知型号不猜 Tool Calling、推理或供应商专有参数；旧自定义型号若要用于 Agent，需要补能力声明。
- DeepSeek 推理型号暂不开放 Agent：当前工具协议需要回传 reasoning_content，现有历史契约没有保留。普通 Chat 保留，避免本期扩大历史协议修改。
- 只有上游明确拒绝某个可选参数时才降级；任意 400 不重试。原始供应商错误体不进入公开异常或日志。未配置凭据在真实 Adapter 请求前失败，离线 FakeProvider 构造仍可用。
- 配置加载失败时前端保留禁用展示，不宣称可用。模型不可用不会统一显示为“需要订阅”。

## 自动化验收结果

执行日期：2026-10-18。

| 目录 / 命令 | 实际结果 |
| --- | --- |
| Backend：`UV_CACHE_DIR=/tmp/shenzhi-uv-cache uv run --no-sync python -m unittest discover -s tests` | 470 项；443 通过，27 跳过，0 失败；23.198 秒 |
| Backend 专项：`UV_CACHE_DIR=/tmp/shenzhi-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_llm*.py'` | 22 项全部通过，0 失败；0.435 秒，亦包含于全量回归 |
| Web：`npm run typecheck` | 通过 |
| Web：`npm test` | 327 项全部通过，0 跳过 / 失败；9.403 秒 |
| Web：`npm run lint` | 0 错误，2 处既有 warning |
| 仓库：`git diff --check` | 通过 |

27 项跳过依赖 `CHAT_DATABASE_URL`，本地未配置 PostgreSQL。相关已有持久化测试未被删改，真实数据库历史恢复尚未在本次环境运行。其他原有 SSE、思考内容、工具调用、停止、继续生成、重试、上下文压缩、历史解码与会话测试通过。

两处既有 lint warning：`features/chat/hooks/use-chat-session.ts:472` 的 `setBusyValue` 依赖，以及 `lib/use-popover-placement.ts:37` 的 `anchorRef` 依赖。两文件均未修改。

## GLM 验证事实

| 能力 | Mock 验证 | 真实 API 验证 |
| --- | --- | --- |
| 国内地址 / Key / 型号独立绑定 | 通过 | 未执行 |
| 普通流式 Chat、产品会话 SSE、正常完成 | 通过 | 未执行 |
| reasoning_content 字段解析容错 | 通过；不代表具体型号实际输出推理 | 未执行 |
| 已声明工具能力的函数调用分片、参数归并 | 通过 | 未执行 |
| 未声明 Tool Calling 的版本拒绝 Agent | 通过 | 未执行 |
| 新 GLM 版本通过 JSON 指定能力、thinking、temperature 和 Token 上限 | 通过 | 未执行 |
| 实际型号权限、地区平台兼容、限额、延迟及工具成功率 | 无法由 Mock 证明 | 待凭据联调 |

当前执行进程的 `DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`、`ZHIPU_API_KEY` 均未设置，仅检查是否存在，未读取或输出任何真实 Key。本次没有真实供应商 API 请求，没有伪造联调通过结果。

## 已知风险与后续建议

- 内置型号能力是保守声明，供应商别名 / 型号 / 账号权限会演进。上线前为实际使用的具体型号完成真实 Chat 与 Tool Calling 联调，再按证据更新声明。
- 旧自定义型号不再依赖名称正则推测能力，可能需要补充声明；迁移时应核对历史裸模型名与 aliases。
- DeepSeek 思考工具轮次回传应作为后续明确的小任务，补齐历史协议和回归测试后再开放对应 Agent 能力。
- 在配置数据库的测试环境补跑 27 项持久化验收；本期无 Schema 变化。
- 当前 JSON 为进程服务端配置，不是管理平台；部署者负责审查自定义 HTTPS 端点信任关系。没有自动故障切换、负载均衡、订阅、计费或配额功能。

## 提交与状态

| 阶段 | Commit | 说明 |
| --- | --- | --- |
| A | `a62c48d` | feat: 建立统一模型注册表与独立供应商配置 |
| B | `9bf5ec9` | refactor: Chat 与 Agent 统一解析模型并隔离供应商路由 |
| C | `fd8519e` | feat: 统一 Chat 与 Agent 模型目录及智谱前端展示 |
| D | 本报告所在提交 | test: 完善模型配置边界验收与接入文档 |

最终 Commit hash 与 clean 状态在交付答复中给出。保持本地功能分支，无推送、无合并到 dev / main。
