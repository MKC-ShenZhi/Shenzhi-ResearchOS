# LLM API Foundation：多 Provider 模型注册与 AutoDL 接入

## 调用与文件职责

```text
Agent / Future AI Features
    → load_registry() / ModelRegistry
    → resolve_model(id, purpose) → ResolvedModel
    → ProviderConfig（HTTPS Base URL、服务端凭据、启用状态）
    → Agent OpenAICompatProvider
    → /chat/completions
```

- `apps/agent/src/agent_app/integrations/llm/catalog.json`：内置 Provider、实际开放白名单、禁用历史模板及固定 aliases。它是模型注册的主要来源；enabled 决定开放状态。
- `registry.py`：类型、校验、模型查询、默认模型、兼容别名、用途校验及公开目录投影。用途（`Purpose`）有 `chat` 与 `agent` 两种：`chat` 是基础用途与共享默认（要求流式对话能力，对应 `AI_DEFAULT_MODEL`），`agent` 在此之上要求 Tool Calling；它们是 Registry 内的能力 / 默认划分，不对应独立产品。`ResolvedModel` 包含 `spec`、`provider`、`upstream_model`、`base_url`、`key`；它是服务端对象，禁止直接序列化为 API 响应。
- `resolver.py`：服务端配置加载器。组合内置声明、自定义 JSON 与通用地址/默认覆盖，生成单一 Registry。现阶段按配置请求 / Provider / Runtime 构造加载，不引入数据库、远程管理或缓存失效机制。
- `agent_app.integrations.llm.config`：保留 `ModelConfig` 显式离线注入结构；`OpenAICompatProvider(config)` 经 `resolver.registry_from_config()` 注入测试 / MockTransport，不读取旧型号环境变量。业务路由使用统一 Catalog Registry。
- `integrations/llm/agent_stream.py`、`agent_app/execution/provider.py`、`agent_app/execution/runtime.py`：唯一的模型调用 Adapter。负责 Tool Calling、JSON 修复、超时（`AI_TIMEOUT_SEC`）、零增量重试、历史恢复与预算，模型解析及请求参数构造统一走 Registry。上下文摘要仍通过相同 Agent Provider 与模型。
- `api/agent.py` 的 `GET /agent/config`：Registry 中 `agent` 用途的公开目录与默认模型；保留 JSON 外层及 `value/label/provider/enabled` 字段。`provider` 表示展示品牌，另有 `provider_id/brand/capabilities/aliases`。
- Web 的 `clients/backend/model-types.ts` 为公开模型契约，`types/ai-search.ts` 定义 Composer 使用的 `ComposerConfig` / `ModelId` 等类型；配置加载失败时的禁用占位目录在 `components/common/composer/config.ts`。模型选择器不维护可用性白名单，只展示 `/agent/config` 的能力过滤结果。

Provider 与品牌分别建模。例如 `dashscope/deepseek-v3` 的品牌为 `deepseek`，其地址和 Key 属于 `dashscope`。

## 普通开发配置与内置白名单

只在 `apps/agent/.env` 填写需要的 Key（Docker 填 `infra/docker/env/agent.env`）：

```ini
DASHSCOPE_API_KEY=
DEEPSEEK_API_KEY=
ZHIPU_API_KEY=
AUTODL_API_KEY=
OPENLUX_API_KEY=
```

地址、协议、Key 环境变量名、型号及能力由扁平 `catalog.json` 统一维护。Key 不进入 Catalog。
以下为内置 enabled=true 的型号；缺 Key 时仍在内部 Registry，但不进入公开目录，真实调用返回 20004/503。

| Provider | 开放的精确上游 ID（完整 Model ID 加上 `provider/` 前缀） | Agent |
| --- | --- | --- |
| dashscope | `qwen-plus` | 是 |
| deepseek | `deepseek-chat` | 是 |
| zhipu | `glm-4-plus` | 声明支持；既有离线验证，真实联调待完成 |
| autodl | `DeepSeek-V4.1-Flash-1017`、`Qwen3.5-397B-A17B`、`Kimi-K2.5` | 是，沿用既有 T0–T7 实测记录 |
| openlux | `deepseek-v4.1-flash`、`qwen3.8-flash`、`glm-5.3-flash`、`kimi-k2.6`、`gemini-3.8-flash` | 前四款开放 Agent；Gemini 因输出上限异常暂不开放 Agent |

`qwen-max`、`qwen-turbo`、DashScope `deepseek-v3`/`deepseek-r1`、DeepSeek `deepseek-reasoner` 保留为禁用模板，不因存在 Key 自动开放。公开契约仍保留禁用提示；禁用模型不导出为授权能力。其他历史部署中的型号须通过受信任文件迁移，不根据名称猜能力。

## 注册流程、默认选择与覆盖

`load_registry()` 读取 Catalog → 合并 `AI_MODEL_REGISTRY_FILE` → 通用地址覆盖 → 显式默认覆盖 → `ModelRegistry`。没有 Provider 专用注册分支，新增兼容协议的 Provider 不需要修改 Resolver。

- 文件按 ID 完整替换 Provider/Model，保留既有位置；新条目追加。aliases/defaults 按键覆盖。文件内重复 ID、未知字段、非法地址/参数、冲突 Alias 与无效默认均拒绝，不回显输入。
- `AI_DEFAULT_MODEL`、`AI_AGENT_DEFAULT_MODEL` 高于文件/Catalog defaults。内置 Catalog 不固定 defaults，使 Key-only 配置可自动选择。
- 自动默认按 Catalog 模型顺序选首个已配置、启用且支持用途的模型：DashScope → DeepSeek → 智谱 → AutoDL → OpenLux；各渠道内部顺序见表。OpenLux 首选 `openlux/deepseek-v4.1-flash`，不改变其他 Provider 顺序。新增 Provider/Model 的位置就是默认优先级，应审查变更。Agent 额外要求 Tool Calling；可复用满足要求的显式 Chat 默认。
- 显式默认未知/禁用/用途不匹配时报错；显式默认缺凭据不切换供应商，公开默认为 null，真实调用拒绝。没有可用模型时公开列表为空、默认 null；内部保留历史解析定义不表示可调用。
- 同名上游是独立实例。裸名称通过 Catalog 的固定 aliases 兼容，绝不随 Key 变化重绑；`deepseek-chat` 固定为 `deepseek/deepseek-chat`。历史上绑定到 DashScope 的同名裸名称，必须在部署文件显式覆盖 Alias 后才能升级。AutoDL/OpenLux 不生成裸名 Alias。
- `AI_TIMEOUT_SEC` 沿用现有 Adapter。`<PROVIDER_ID大写>_BASE_URL` 可选覆盖内置和文件 Provider 的地址；禁止 URL 凭据、query、fragment、非 HTTPS。只使用受审查的部署地址；API 客户端不能覆盖配置。

## 一次性配置整理

型号只从 Catalog 和受信任的 `AI_MODEL_REGISTRY_FILE` 注册。旧型号环境变量、过渡选择器和废弃告警已删除，不再保留第二套注册机制；部署者一次性清理旧项即可。需要继续使用的非内置型号，先作为完整 Model 条目加入受信任 JSON 并验证能力。

历史完整 Model ID 及 Catalog 固定 Alias 保持稳定。历史同名裸名称若指向其他渠道，在部署 JSON 显式维护 Alias；不能随 Key 变化重绑。配置整理不自动替换会话/任务/Policy 的 ID，不发布 Policy 或调整用户权益。

原生 API、执行 Worker、Usage Worker 使用同一配置；Docker 填 `infra/docker/env/agent.env`，JSON 挂载到相同容器可读路径。修改 env 后重新创建三个容器，不能只 restart。

## OpenLux 验证入口

[官方价格目录](https://www.openlux.ai/pricing) 与真实 `GET /models` 均确认下列五个精确 ID；不动态同步或开放其他型号。Provider 使用 [官方文档](https://doc.openlux.ai/) 的默认端点与 Bearer Key，继续走同一 OpenAI Compatible Adapter。

| 上游 ID | Label | Brand | Agent | reasoning 字段实测 |
| --- | --- | --- | --- | --- |
| `deepseek-v4.1-flash` | DeepSeek V4.1 Flash | deepseek | 是，OpenLux 首选 | reasoning_content |
| `qwen3.8-flash` | Qwen3.8 Flash | platform | 是 | reasoning_content |
| `glm-5.3-flash` | GLM-5.3 Flash | zhipu | 是 | reasoning_content / reasoning |
| `kimi-k2.6` | Kimi K2.6 | moonshot | 是 | 本次未出现正文推理字段 |
| `gemini-3.8-flash` | Gemini 3.8 Flash | google | 暂否 | 本次未出现正文推理字段 |

五者于2026-11-24通过流式正文、`stream_options.include_usage`、temperature=0.3 参数接受，以及两次两轮工具调用（回传工具结果，不回传 reasoning）的真实探测。基线均通过，故不设置额外 thinking 参数；不根据其他平台的同系列名称外推能力。推理字段声明不保证每次出现。

型号均保守声明输出硬上限4096、chat/agent预算4096，不编造上下文窗口。32768仅验证首块接受，未证明完整长输出。补充非流式截断探测：前四者请求64 completion tokens均在64结束，DeepSeek/Qwen/GLM的usage显示思考包含在completion中；Kimi也报告少量reasoning tokens。该结果只是本次渠道/分组的小样本，不构成全局上界或生产风险审批。

**Gemini 请求 `max_tokens=64` 却报告4160 completion tokens**。虽然工具探测通过，当前仍保守设 `tool_calling=false`，使其退出 Agent 目录、能力导出和正式预算接入；保留 Chat 声明供后续核验。其64上限异常须先确认 OpenLux 参数映射与流式同等语义，不允许通过抬高预算掩盖。其他渠道的Gemini/同名模型不能据此推断。

完整仓库原生环境从 `apps/agent` 使用 opt-in 探测入口（复用的 Backend 运维脚本未打包进 Agent 生产镜像）：

```powershell
uv run --env-file .env python scripts/openlux_probe.py --list-only
uv run --env-file .env python scripts/openlux_probe.py deepseek-v4.1-flash qwen3.8-flash glm-5.3-flash kimi-k2.6 gemini-3.8-flash
```

脚本复用既有 T0–T7 Probe，只探测目录中精确匹配的显式候选，不自动注册/授权。首次只运行 list-only；型号探测会产生少量费用。输出经过脱敏且不包含模型正文或思考文本；不得将真实 Key 写进命令、日志、文档或客户端。详细实测及本地 Docker 验收见 [交付记录](../dev/records/engineering/model-provider-unification-delivery.md)。

普通组员只填 `OPENLUX_API_KEY`；原生运行需显式加载 `.env`，Docker 用 `prepare-env.py --from-local` 导入并重建三个Agent容器。已有非空Docker Key优先保留，轮换时须自行同步本地Docker env。若已有显式默认，仍优先使用该配置；只配置OpenLux Key、默认留空时自动选DeepSeek。

## 权益与计量

注册、已配置、支持 Agent、正式 Policy 已授权是不同状态。Web/Admin/`export_capabilities.py` 继续使用同一服务端 Registry，未改 API 契约或前端名单。

Model Identity 仍绑定 provider_id、registry_model_id、upstream_model、能力、request_params、route revision 和 Adapter 契约；密钥不进入 digest。仅将现有相同能力迁到 Catalog 不改变该模型身份。修改路由需管理员更新 `AGENT_MODEL_ROUTE_REVISION`；修改能力、参数、用途开放集合需用最终 Worker 配置重新导出并审核。

正式环境按 [权益部署步骤](../agent/entitlements.md#部署时的能力同步与资源默认值) 排空历史 Grant、导出能力、准备逐模型预算/risk profile，再经既有 Admin 预览发布及分配。OpenLux 新 ID 必须有独立预算审批；max_tokens 覆盖 completion（含 reasoning）的语义未知或异常时不得批准。BudgetGrant、CallPermit、唯一发送权、动态 Token 上限及用量账本保持原实现，不发布生产 Policy、不修改用户权益。开发环境也须按现有显式 test_only Policy 流程，不能把 Key-only 误解为免授权。

## 新增兼容 Provider 或 Model

无需修改 Agent、API 路由或前端业务代码。创建服务端 JSON，例如 `llm-registry.json`：

```json
{
  "providers": [
    {
      "id": "fourth",
      "protocol": "openai_chat_completions",
      "base_url": "https://llm.example.com/v1",
      "api_key_env": "FOURTH_API_KEY",
      "enabled": true
    }
  ],
  "models": [
    {
      "id": "fourth/upstream-chat-v1",
      "provider_id": "fourth",
      "upstream_model": "upstream-chat-v1",
      "label": "Research Chat",
      "brand": "platform",
      "enabled": true,
      "capabilities": {
        "chat": true,
        "streaming": true,
        "tool_calling": true,
        "reasoning": false,
        "temperature": true,
        "thinking": "none",
        "stream_options": false,
        "chat_max_tokens": 4096,
        "agent_max_tokens": 32768,
        "max_output_tokens": 8192
      },
      "request_params": {}
    }
  ],
  "aliases": {"historical-custom-model": "fourth/upstream-chat-v1"},
  "defaults": {"chat": "fourth/upstream-chat-v1", "agent": "fourth/upstream-chat-v1"}
}
```

内置接入时将相同扁平条目加入 Catalog，并在两个 `.env.example` 添加 Key 项，完成真实能力验证后再启用；无需新增 Python 分支。部署私有条目则设置 `FOURTH_API_KEY` 与 `AI_MODEL_REGISTRY_FILE` 并重启。目录文件不保存 Key；只引用环境变量名。修改文件为该 JSON 与 Agent 环境配置；可选增加品牌 Logo。未知品牌使用通用图标，不会造成组件异常。增加新协议才需要新增 Adapter；当前拒绝未支持的协议字符串。

给新 GLM 型号声明能力时，也可只提供 `models`（引用已有 `zhipu`），例如 ID `zhipu/my-glm`、`upstream_model` 为实际型号，明确设置该版本支持的能力。不得凭型号名称推测。

能力默认值为流式对话（`chat=true`）、temperature=true、Tool Calling=false、reasoning=false、thinking=none、stream_options=false、`chat_max_tokens` 4096 / `agent_max_tokens` 32768 / 模型硬上限 4096（当前只有 Agent Adapter 使用 `agent_max_tokens`）。实际发送的上限取业务预算与模型硬上限的最小值，Agent 的显式压缩预算也受尊重。升级模型上限需有供应商文档 / 联调依据。

`thinking` 策略可为 `none`、`enable_thinking` 或 `thinking`。`request_params` 仅接受与策略一致的 `enable_thinking: boolean` 或 `thinking: {"type":"enabled|disabled"}`，禁止覆盖 model、messages、tools、stream、地址或凭据。Chat 仅发送显式 request_params；Agent 可按已声明策略开启思考，`AGENT_DISABLE_THINKING=true` 可关闭扩展。只有响应明确指出相关可选参数不支持时才摘掉该参数重试；任意 400 不降级 / 重试。原始错误体只作内部分类，不进入日志或公开异常。

DeepSeek 官方 Provider 推理型号的 Agent Tool Calling 暂时保守禁用：官方当前协议要求工具轮次回传完整 reasoning_content，而现有 Agent 历史契约没有保留该字段。当前不为此修改历史协议；该历史模板默认禁用；经验证的受信任声明可单独开放 Chat。AutoDL 是独立渠道，V4.1 日期版仅因其 T5 实测通过而声明工具能力，不据此外推官方型号。参考 [DeepSeek thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/)。GLM 入口参考 [智谱 OpenAI 兼容说明](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)；真实型号权限与能力以部署平台联调为准。

## 验证与真实 API 边界

在 `apps/agent`：

```bash
uv run --no-sync python -m pytest tests -q
uv run --no-sync python -m pytest tests/unit/test_llm_registry.py tests/unit/test_llm_config_api.py tests/unit/test_llm_routing.py tests/unit/test_openlux.py tests/unit/test_export_capabilities.py tests/unit/test_metering_boundaries.py -q
```

`--no-sync` 使用已有 uv 环境；首次开发按仓库方式先 `uv sync`。在 `apps/web`：

```bash
pnpm test
pnpm typecheck
pnpm lint
```

专项覆盖：稳定默认优先级、三家实际请求 Host/Bearer/upstream、GLM 产品 SSE / 推理片段 / 工具参数分片、同名上游、多家同时可用、别名、禁用/缺凭据/未知/能力不足、两份 config 同源且兼容旧字段、公开 Schema / 日志无 Key，以及只新增 JSON 声明即可路由第四家。原有停止、恢复、上下文、工具修复和重试测试继续保留；明确更新了旧任意 400 降级与原始错误体外泄的断言。

阶段一的本地验收记录见 [交付记录](../dev/records/engineering/llm-api-foundation-delivery.md)。智谱 GLM 尚未对真实供应商接口联调：其 SSE、推理字段容错、Tool Calling、凭据隔离与参数策略均为 Mock 验证；实际模型权限、输出上限、地区兼容性、延迟与工具成功率待有凭据后联调。模拟流中的 reasoning_content 验证的是 Adapter 解析，不能证明 `glm-4-plus` 实际输出思考内容。
