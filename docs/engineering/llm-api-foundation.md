# LLM API Foundation（第一阶段）

## 调用与文件职责

```text
Chat / Agent / Future AI Features
    → load_registry() / ModelRegistry
    → resolve_model(id, purpose) → ResolvedModel
    → ProviderConfig（HTTPS Base URL、服务端凭据、启用状态）
    → 现有 Chat ModelProvider / Agent OpenAICompatProvider
    → /chat/completions
```

- `apps/backend/app/integrations/llm/catalog.json`：内置 Provider 定义与精确型号能力模板。模板本身不表示该型号已开放；环境默认型号、旧白名单或自定义文件决定实际注册的模型。
- `registry.py`：类型、校验、模型查询、默认模型、兼容别名、用途校验及公开目录投影。`ResolvedModel` 包含 `spec`、`provider`、`upstream_model`、`base_url`、`key`；它是服务端对象，禁止直接序列化为 API 响应。
- `resolver.py`：服务端配置加载器。组合内置声明、旧变量、自定义 JSON，生成单一 Registry。现阶段按配置请求 / Provider / Runtime 构造加载，不引入数据库、远程管理或缓存失效机制。进程启动也校验配置。
- `core/config.py`：保留 `ModelConfig` 与 `model_config()` 兼容入口，用于已有服务端调用 / 测试注入；业务路由已改用 Registry。
- `integrations/llm/provider.py`：保留普通 Chat 的 SSE、推理片段与追问处理。追问明确解析 Chat 默认模型，不隐式沿用任意全局供应商。
- `services/agent/provider.py`、`runtime.py`：保留 Tool Calling、JSON 修复、超时、零增量重试、历史恢复与预算，只迁移模型解析及请求参数构造。上下文摘要仍通过相同 Agent Provider 与模型。
- `api/chat.py`、`api/agent.py`：同一 Registry 的公开目录与默认模型；保留 JSON 外层及 `value/label/provider/enabled` 字段。`provider` 继续表示展示品牌，新增 `provider_id/brand/capabilities/aliases`。
- Web 的 `clients/backend/model-types.ts` 为共用公开模型契约，Chat 类型路径继续转出旧名称。`features/chat/services` 只适配后端目录、兼容别名及失败展示；模型选择器不维护可用性白名单。Agent 使用自身 config 的能力过滤结果和同一公共选择组件。

Provider 与品牌分别建模。例如 `dashscope/deepseek-v3` 的品牌为 `deepseek`，其地址和 Key 属于 `dashscope`。

## 三家供应商配置

仅在 Backend 环境设置，禁止放入 Web / `NEXT_PUBLIC_*`。以下省略真实 Key：

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
# 可选；不设置时优先共用具备 Agent 能力的 Chat 默认模型。
AI_AGENT_DEFAULT_MODEL=deepseek/deepseek-chat
AI_ALLOWED_MODELS=
AI_TIMEOUT_SEC=90
AI_MODEL_REGISTRY_FILE=
```

三套 Provider 可同时启用。智谱的默认地址是**国内开放平台**，没有默认型号；仅有 Key 不产生 GLM 模型。国内、国际及其他平台的凭据不得交叉使用；其他区域应声明独立 Provider ID 与完整配套地址 / 凭据。本文不承诺不同平台支持相同型号与参数。

`ZHIPU_MODEL` 接受任意非空具体型号。内置 `glm-4-plus` 能力声明支持普通 Chat、流式、Tool Calling 和 temperature，输出上限保守设为 4096，不发送 `enable_thinking` / `stream_options`。其他未声明型号默认仅启用保守的流式 Chat，Tool Calling 为 false，需要在自定义文件中显式声明后才能用于 Agent。

## 优先级、冲突和旧配置

1. 内置 Provider 默认地址可被各自 `*_BASE_URL` 覆盖；Key 总是取各自环境变量。
2. 注册每家 `*_MODEL`。DashScope 默认 `qwen-plus`，DeepSeek 默认 `deepseek-chat`，智谱无默认型号。没有 Key 的条目在 config 中禁用。
3. `AI_ALLOWED_MODELS` 保持旧语义：作为额外型号，绑定有 Key 的 DashScope，否则绑定 DeepSeek。它不是多 Provider 全局白名单；新增多供应商型号优先使用 JSON 声明。
4. `AI_MODEL_REGISTRY_FILE` 指向服务端 JSON 文件，相对路径以 Backend 工作目录为基准。自定义条目按 ID 覆盖自动生成条目（完整替换，不做字段合并）。文件内重复 Model / Provider ID、未知 Provider、冲突别名、未知字段、不支持协议、非法参数、非 HTTPS 地址均明确报配置错误。
5. 默认模型优先级为 `AI_DEFAULT_MODEL` / `AI_AGENT_DEFAULT_MODEL` > 文件 `defaults` > 旧规则。有旧 Key 时，Chat 默认有 Key 的 DashScope，否则 DeepSeek；仅智谱配置有效时可默认选择智谱。无有效 Key 时保持旧默认候选的禁用展示。
6. Agent 未单独指定默认时，共用具备 Tool Calling 的 Chat 默认；否则优先选择已配置、启用且具备 Agent 能力的条目。没有合适候选时明确不可用，不放行不支持的模型。显式默认模型不存在、禁用或不支持其用途会报配置错误；缺失凭据不会切到别家。

环境覆盖与文件覆盖均是服务端部署配置；客户端不能提交地址、Key 或请求能力配置。所有端点必须为 HTTPS，禁止 URL 中的用户名、密码、查询参数及 fragment。自定义端点由部署者审查信任关系；本地 MockTransport 使用 HTTPS 虚拟域名，无外网依赖。

新注册的自动 Model ID 为 `{provider_id}/{upstream_model}`，不会因为同名型号或另一家 Key 的存在而改变 Provider。旧裸名称通过显式生成的 aliases 兼容；发生同名时，旧优先供应商拥有裸名称别名，另一家用完整 ID。迁移历史白名单或修改旧 Key 优先关系前，应将历史裸名称固定为文件 aliases。已保存的完整 ID 始终指向明确供应商；如果该条目不再注册，则报错，不切换供应商。文件可给任意历史自定义 ID 建立一层别名，禁止链式 / 循环别名。`default` 是解析当前用途默认模型的保留值。

Chat 创建与 Agent Runtime 构造保留离线测试注入体验，先验证型号及用途；真实 Adapter 发起请求前校验凭据。未知 / 禁用 / 不支持用途使用现有 `20001`，供应商未配置使用 `20004 / 503`。SSE 已开始后不自动切换模型，request_id 和业务错误协议不变。

## 声明第四家 OpenAI 兼容 Provider

无需修改 Chat、Agent、API 路由或前端业务代码。创建服务端 JSON，例如 `llm-registry.json`：

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
      "id": "fourth/research-chat",
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
  "aliases": {"historical-custom-model": "fourth/research-chat"},
  "defaults": {"chat": "fourth/research-chat", "agent": "fourth/research-chat"}
}
```

然后设置 `FOURTH_API_KEY` 与 `AI_MODEL_REGISTRY_FILE` 并重启。目录文件不保存 Key；只引用环境变量名。修改文件为该 JSON 与 Backend 环境配置；可选增加品牌 Logo。未知品牌使用通用图标，不会造成组件异常。增加新协议才需要新增 Adapter；当前拒绝未支持的协议字符串。

给新 GLM 型号声明能力时，也可只提供 `models`（引用已有 `zhipu`），例如 ID `zhipu/my-glm`、`upstream_model` 为实际型号，明确设置该版本支持的能力。不得凭型号名称推测。

能力默认值为流式 Chat、temperature=true、Tool Calling=false、reasoning=false、thinking=none、stream_options=false、Chat 4096 / Agent 32768 / 模型硬上限 4096。实际发送的上限取业务预算与模型硬上限的最小值，Agent 的显式压缩预算也受尊重。升级模型上限需有供应商文档 / 联调依据。

`thinking` 策略可为 `none`、`enable_thinking` 或 `thinking`。`request_params` 仅接受与策略一致的 `enable_thinking: boolean` 或 `thinking: {"type":"enabled|disabled"}`，禁止覆盖 model、messages、tools、stream、地址或凭据。Chat 仅发送显式 request_params；Agent 可按已声明策略开启思考，`AGENT_DISABLE_THINKING=true` 可关闭扩展。只有响应明确指出相关可选参数不支持时才摘掉该参数重试；任意 400 不降级 / 重试。原始错误体只作内部分类，不进入日志或公开异常。

DeepSeek 推理型号的 Agent Tool Calling 暂时保守禁用：官方当前协议要求工具轮次回传完整 reasoning_content，而现有 Agent 历史契约没有保留该字段。本阶段不扩大历史协议修改；普通 Chat 可用。参考 [DeepSeek thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/)。GLM 入口参考 [智谱 OpenAI 兼容说明](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)；真实型号权限与能力以部署平台联调为准。

## 验证与真实 API 边界

在 `apps/backend`：

```bash
UV_CACHE_DIR=/tmp/shenzhi-uv-cache uv run --no-sync python -m unittest discover -s tests
UV_CACHE_DIR=/tmp/shenzhi-uv-cache uv run --no-sync python -m unittest discover -s tests -p 'test_llm*.py'
```

`--no-sync` 使用已有 uv 环境；首次开发按仓库方式先 `uv sync`。在 `apps/web`：

```bash
npm test
npm run typecheck
npm run lint
```

新增专项覆盖 A–K：旧默认优先级、三家实际请求 Host/Bearer/upstream、GLM 产品 SSE / 推理片段 / 工具参数分片、同名上游、多家同时可用、别名、禁用/缺凭据/未知/能力不足、两份 config 同源且兼容旧字段、公开 Schema / 日志无 Key，以及只新增 JSON 声明即可路由第四家。原有停止、恢复、上下文、工具修复和重试测试继续保留；明确更新了旧任意 400 降级与原始错误体外泄的断言。

本地验收结果记录在 [阶段一交付报告](llm-api-foundation-delivery.md)。本次没有调用真实供应商接口：GLM 的 SSE、推理字段容错、Tool Calling、凭据隔离与参数策略均为 Mock 验证；实际模型权限、输出上限、地区兼容性、延迟与工具成功率待有凭据后联调。模拟流中的 reasoning_content 验证的是 Adapter 解析，不能证明 `glm-4-plus` 实际输出思考内容。
