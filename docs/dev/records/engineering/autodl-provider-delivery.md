# AutoDL Provider 交付报告

## 范围与实测时间

- 分支：`feat/autodl-provider`，从 `feat/llm-api-foundation` 创建；未推送、未合并、未修改 remote。
- 探测日期：2026-10-24（Asia/Tokyo）。T0–T7 报告时间以 UTC 记录，对应当地同一天。
- 仅修改 catalog、resolver、registry 的公开投影、测试、示例配置、文档，并新增探测脚本；没有新增依赖、修改 Adapter、业务流程或路由。浏览器验收暴露共享图标缺少未知品牌回退，以及基线 mock 缺 imageId；用户在本次会话中明确授权这两处最小前端修复，另作一笔 fix 提交；随后另行授权为当前共享 Composer 补齐空目录下的按钮与键盘 AI 提交保护及回归测试。
- 原始脱敏 JSON 位于本次本机 `/tmp/autodl_probe.json`；下文保留可审查的结果摘要。报告、日志、提交不包含真实 Key。

## T0：可用模型列表

`GET https://www.autodl.art/api/v1/models` 返回 HTTP 200。确认以下目标 ID：

1. `DeepSeek-V4.1-Flash-1017`：选择明确日期版；同列表还有无日期的 `DeepSeek-V4.1-Flash`，本批不重复注册。
2. `Qwen3.5-397B-A17B`
3. `Kimi-K2.5`

`GLM-5.1` 与 `DeepSeek-V3.2` 均不在 T0，未发起虚构 ID 的探测，也未以其他版本替代。因此第 2 步实际运行三个可确认的目标型号，而非五个。

T0 完整返回 ID（顺序保留；出现不代表纳入本产品）：

```text
DeepSeek-V4.1-Flash-1017
hy4-preview
DeepSeek-V4.1-Flash
gpt-6-astra
GLM-5.3-flash
GLM-5.3
gpt-5.6-luna
gpt-5.6-terra
gpt-5.6-sol
Kimi-K3
hy3
Kimi-K2.7-Code
GLM-5.2
claude-opus-5-5
claude-fable-5
claude-sonnet-5
DeepSeek-V4-Pro
DeepSeek-V4-Flash
gpt-image-2
Kimi-K2.6
claude-opus-4-8
claude-opus-4-8-cc
claude-opus-4-7
claude-opus-4-7-cc
qwen3.7-max
qwen3.6-plus
Kimi-K2.5
MiniMax-M3.1-Flash
MiniMax-M2.7
MiniMax-M2.5
Qwen3.5-397B-A17B
claude-sonnet-4-6-cc
claude-opus-4-6-cc
claude-sonnet-4-6
claude-opus-4-6
gpt-image-2.5-sunburst
gpt-image-2.5-flare
claude-opus-5
Qwen-Image
Z-Image-Turbo
nano-banana-2
qwen3-vl-plus
```

## T1–T7 能力矩阵

| 探测项 | DeepSeek-V4.1-Flash-1017 | Qwen3.5-397B-A17B | Kimi-K2.5 |
| --- | --- | --- | --- |
| T1：HTTP / 正文 / finish_reason | 200 / 非空 / stop | 200 / 非空 / stop | 200 / 非空 / stop |
| T1：reasoning_content / reasoning / 正文 think 标签 | 有 / 无 / 无 | 有 / 无 / 无 | 无 / 无 / 无 |
| T2：include_usage | 200，usage 有 | 200，usage 有 | 200，usage 有 |
| T3：首个接受的输出上限 | 32768，收到首块断开 | 32768，收到首块断开 | 32768，收到首块断开 |
| T4：temperature=0.3 | 200，接受 | 200，接受 | 200，接受 |
| T5：流式工具分片、合法 JSON、无推理字段历史的第二轮 | PASS，2/2；首轮各 10 片 | PASS，2/2；首轮 5、6 片 | PASS，2/2；首轮 8、7 片 |
| T6：enable_thinking=false | PASS，2/2 | PASS，2/2 | 未触发 |
| T6：thinking.type=disabled | PASS，2/2 | PASS，2/2 | 未触发 |
| T7：错误 Key | 服务级一次请求，401 | 共用左侧结果 | 共用左侧结果 |

T5/T6 每次均为两轮请求：声明 echo(text)、tool_choice=auto，拼接 arguments 为合法 JSON；第二轮 assistant 不带 reasoning_content/reasoning，回传 tool 结果后要求 200 且有正文。DeepSeek、Qwen 的基线 T5 已通过，T6 因 T1 出现推理而执行；两种关闭参数也都通过，但无需作为默认 request_params。Kimi 无推理且 T5 已通过，按条件跳过 T6。

T7 状态码 401，脱敏响应体前缀：

```json
{"error":{"message":"Invalid authentication credentials","type":"invalid_request_error"}}
```

已有错误文案覆盖 401。未出现只返回 delta.reasoning 的模型或需要补充的新状态码，因此两个 Adapter 均保持原样。

## 最终声明与默认模型

- 三个模板均声明 `tool_calling=true`、`stream_options=true`、`max_output_tokens=32768`；沿用 `temperature=true`、`chat_max_tokens=4096`、`agent_max_tokens=32768`、`thinking=none`、空 request_params 等默认值。
- DeepSeek 与 Qwen 声明 `reasoning=true`；Kimi 沿用 false。未凭型号名称推断能力。
- Chat 与 Agent 的推荐默认值均为 `autodl/DeepSeek-V4.1-Flash-1017`。仅配置 AutoDL Key 时，两个用途的隐式默认值亦为该项；Qwen、Kimi 均可选作 Agent 备选。
- 旧 Provider Key 同时存在时保留原有默认优先级；显式 `AI_DEFAULT_MODEL` / `AI_AGENT_DEFAULT_MODEL` 优先于文件 defaults 与隐式选择。
- 无 AutoDL Key 不自动注册其模型。清单按原始大小写保存，空项/重复项清理后为空则使用默认清单；无裸名别名。清单外型号保持保守能力，不能直接用于 Agent。
- `AUTODL_BASE_URL` 复用已有 HTTPS 校验，不引入新的连接方式。

## 模型菜单行为变更

公开目录仅返回已配置且启用的 Provider 下的条目。实际共享 Composer 的品牌组件已补充通用 PlatformLogo 及未知品牌回退，Qwen 与 Kimi 均使用通用图标；旧 Chat 目录内的品牌组件原有回退保持原样。已配置 Provider 下显式 disabled 的模型仍有“模型已禁用”提示。`default_model` 必须在本次返回列表中，否则为 null；旧 config 测试中“缺 Key 显示灰色模型”的断言改为“空目录 / null”，并保留已配置未知型号仅 Chat 可见的覆盖。

服务端仍保留旧 Provider 模型及历史 ID 校验，未改变 DashScope、DeepSeek、Zhipu 路由。前端配置失败的占位逻辑保持原样。新增前端测试覆盖成功加载空目录 / null、旧选择不被当作可用模型，并同时覆盖旧 Chat 与当前共享 Composer 的 AI 按钮和键盘提交保护；简单搜索入口不受模型限制。

## 未接入 / 移除项与限制

- `GLM-5.1`、`DeepSeek-V3.2`：T0 不存在。三个实测型号没有 T1 失败或正文 think 标签，不存在按此规则移除的型号。
- gpt、claude、gemini：参数兼容风险；*-cc：Claude Code 专用；*-codex：编码专用；MiniMax：可能混合思考与正文；图像模型：任务范围外。
- 32768 是参数接受探测，不是完整输出长度、质量、价格或上下文长度的保证；T3 首块后立即断开。T5 两次通过是当前账号/日期的证据，不保证上游永久可用。
- 模型目录通过服务端凭据和能力声明过滤，不会每次请求远程探活。账号权限、上游清单和余额变化后需重新执行脚本；手动填入 AUTODL_MODELS 的未知型号需部署者自行验证。
- Chat 追问沿用当前 Chat 默认模型；不会隐式沿用每条消息选择的其他型号。

## 测试结果

| 检查 | 结果 |
| --- | --- |
| Backend：`uv run python -m unittest discover -s tests` | 493 项，466 通过、27 因无 CHAT_DATABASE_URL 跳过，0 失败 |
| Web：`npm run typecheck` | 授权修复 mock 的 imageId 后通过 |
| Web：`npm test` | 402 项全部通过，0 跳过 / 失败 |
| Web：直接对 tsc 产物运行标准脚本的 node --test 文件集 | 402 项全部通过（含新增空目录测试）；不能等同于 npm test 通过 |
| Web：`npm run lint` | 0 错误，2 个既有 warning，与改动前基线一致 |

类型错误已在 `git archive feat/llm-api-foundation apps/web` 的独立副本中通过 `npm test` 复现；初次复现时该文件未修改。用户随后明确授权补 imageId:null，已修复并通过标准检查。两处 lint warning 为 use-chat-session.ts 的 setBusyValue 与 use-popover-placement.ts 的 anchorRef 依赖，未修改相关文件。

## 端到端结果

验收使用隔离 Backend 8001（加载本地 .env 后清空其他 LLM Key、旧白名单、自定义注册文件及数据库连接，仅 AutoDL 模型凭据有效），以及基础分支前端副本 3001（同步用户授权的三处修复），保留用户已运行的 8000/3000 服务。无数据库时会话为进程内存态。临时环境未修改 .env。

| 验证边界 | 实测结果 |
| --- | --- |
| Backend / BFF 两种用途的模型目录 | HTTP 200，只含三个 AutoDL 条目，无灰色旧 Provider；provider_id 和品牌正确 |
| 浏览器首页 / Agent 模型菜单 | 三个条目均可见，名称正常；DeepSeek 为品牌图标，Qwen/Kimi 为通用图标，未知品牌不再崩溃 |
| Chat 真实 API：三个模型 × fast/deep | 6/6 均为 HTTP 200，SSE 正文非空，done.status=done，无错误事件 |
| Chat 推理 | DeepSeek、Qwen 的四次产品响应均有 reasoning；Kimi 两次无 reasoning，与 T1 一致 |
| Chat 追问 | 4/6 返回三个建议；Qwen deep、Kimi deep 两次的 followups.items 为空，见下方限制 |
| Chat 会话读取恢复 | 六个会话重新 GET 后均为 done，正文非空，模型完整 ID 与 mode 保留；未用浏览器验证旧 Chat 页面 |
| Agent 默认 V4.1 | 浏览器发起，实际 paper_search 检索三篇 2026 RAG 论文并根据摘要完成回答，2 轮，7254ms，status=done；推理与工具过程可展开 |
| Agent 停止 | 浏览器点击“停止”，5427ms 结束，status=stopped，页面显示“已手动停止” |
| Agent 继续 | 在同一会话提交“继续刚才被停止的回答，但改为三句话”，4251ms 完成，status=done；使用原工具结果继续对比 |
| Agent 备选 Qwen | 浏览器选择 Qwen，实际 paper_search 检索三篇 2026 大模型智能体论文，2 轮，18539ms，status=done |
| Agent 刷新恢复 | 刷新后四轮历史（含停止轮）恢复，最后选择仍为 Qwen；无数据库时仅承诺当前进程内恢复 |
| 无 Key 的空目录 | 隔离后端清空全部模型 Key，BFF Chat/Agent 均 200、models=[]、default_model=null；页面正常渲染 |
| 空目录提交限制 | 输入非空文本后 AI 发送仍 disabled，回车不创建会话；切到简单搜索后发送可用，并实际进入 /knowledge/search、检索接口 200 |
| 凭据安全 | 用真实 Key 前 8 位扫描本次日志、JSON 报告、分支提交与 diff，匹配均为 0；未输出前缀自身 |

默认 Agent 实测返回 MMRAG-RFT、MASS-RAG、DeepRAG；Qwen 备选返回 Rethinking Scale、DiLLS、VDC-Agent。来源是当前知识库检索结果，模型没有用模拟 echo 替代产品工具。工具返回年份可能指发表年，与 arXiv 编号年份不一致时按来源如实标注。Kimi 的 Agent 能力有 T5 两次工具往返证据，未额外运行浏览器论文任务。

临时前端最初尝试依赖软链接，Turbopack 拒绝跨根目录；webpack 又不能解析现有动态鉴权模块。随后复制现有依赖到隔离副本，恢复 README 的 Turbopack 模式完成上述验收，没有修改包配置或新增依赖。这些临时环境失败不计为产品通过证据。

## 尚未全部达标的项目

1. **旧 Chat 浏览器入口缺失**：基线 /agents/ask 已重定向首页，/agents 使用 ShenzhiAiPage（Agent），旧 ChatPage / AskPage 没有页面入口。因此未声称完成“浏览器 Chat 菜单逐个切换、fast/deep、刷新”的验收；已验证真实 Chat API 链路及当前 Agent UI。恢复入口需要改路由或产品流程，超出任务范围及后续三处最小修复授权，未擅自修改。
2. **追问建议非稳定**：六次真实 Chat 中有两次返回空建议。对应追问请求日志为 HTTP 200，非模型主回答失败；其余四次返回三个建议。现有追问固定 max_tokens=300、解析 JSON 字符串数组，没有暴露原始响应到日志。未据此猜测具体根因，也未通过重跑覆盖失败记录；如需修复需要允许调整现有 Adapter 的追问逻辑 / 预算，超出本任务仅允许错误映射与推理字段兼容的 Adapter 范围。
3. PostgreSQL 未配置，27 项持久化测试跳过；本次浏览器刷新验证不是进程重启后的持久化保证。

## 提交拆分

保留要求的 chore / 两笔 feat / test / docs 五个目的提交；另有用户明确授权的“品牌回退与知识库 mock 类型”修复提交。共享 Composer 空目录保护归入目录行为提交，对应回归归入 test 提交。最终 hash 在完成回复中给出；未推送、未合并、未修改 git remote。
