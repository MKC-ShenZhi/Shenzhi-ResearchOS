# ShenZhi Agent 基座设计（v3.16 · pi harness 源码核对版）

> 位置：`apps/backend/app/services/agent/`。参照物：
> ① [earendil-works/pi](https://github.com/earendil-works/pi) 的 `packages/agent`（pi-agent-core）——**主基准**，
>    本仓库 `pi/` 目录内有浅克隆，本文所有"pi 源码"引用均指该目录实际文件；
> ② [anthropics/skills](https://github.com/anthropics/skills) 官方技能规范——本仓库 `anthropic-skills-ref/` 内有克隆，
>    技能资产与 SKILL.md 格式按它对齐（渐进披露三级、frontmatter 校验、disable-model-invocation）；
> ③ Claude Code / Codex 无源码在库，仅按**公开文档描述的机制**在以下点做了机制级对齐（非源码逐一核对，引用时已注明）：
>    AGENTS.md/CLAUDE.md 项目上下文加载（`load_project_context`）、精确文本替换编辑（edit_file）、
>    命令审批/沙箱思路（deny list + timeout 封顶）、上下文压缩（compaction）、技能/记忆外置的渐进披露。
> 修订记录：v3.1 = 三路独立审查（Claude Code deepseek-v4-flash / 内部子智能体 / Codex gpt-5.6-sol）裁决合并；
> v3.2 = 对照 pi 源码（`agent.ts`、`agent-loop.ts`、`types.ts`、`harness/skills.ts`、`harness/system-prompt.ts`、`ai/types.ts`）逐项核对修正；
> v3.3 = 质量审查修复批：pinned 豁免覆盖轮组截断与 floor 去重（context）、forced_skills/工作区组合的 system 追加式装配（service）、
> 工具清单按 registry 动态生成（pi visibleTools 机制）、provider 零增量重试补"剩余 deadline > 2s"条件（ModelRequest.deadline_at）、
> turn_start/compaction 事件、resume 恢复全部 run 级状态（Checkpoint 扩展）、compaction 完整移植 pi 语义（§8.0）。
> v3.4 = 通用 work prompt：AGENT_SYSTEM 拆为 IDENTITY / BASE_GUIDELINES / SKILL_DOC_POINTER（基座通用）+ 业务准则注入
> （service.RESEARCH_GUIDELINES）；ToolSpec 增加 snippet / prompt_guidelines（pi promptSnippet / promptGuidelines 机制），
> 工具专属准则随挂载注入系统提示（workspace 四工具已补，edit/write 准则逐条移植 pi）。
> v3.5 = 剩余 pi 机制全量移植（用户拍板"全部借鉴"）：steer/follow_up 队列（RunChannel，§8.6）、parallel 工具执行
> （tool_execution 配置 + per-tool execution_mode 覆盖，§6）、should_stop_after_turn / prepare_next_turn 钩子（§8.7）、
> addedToolNames（latent 工具由结果启用，§6）、ToolSpec.replay 恢复策略标记、prompt-templates（prompts/ 目录 + $1/$@/ARGUMENTS，
> §10a）、AGENTS.md → project_context 注入（§6a）、provider 重试退避（max_retries/max_retry_delay）与
> onPayload/onResponse 观测钩子、message 事件。默认值保持既有行为（sequential、无钩子、无 latent）。
> v3.6 = 精简重构（以 pi 分层为基准）：循环执行路径零 skills 引用（34→0，read_skill 语义移入 skills.SkillPolicy，
> 经 tool_policy 扩展点接入——pi"一切工具差异走钩子"同构）；pinned 升级为 ToolResult 通用字段；运行控制契约
> （RunChannel/StopContext/NextTurn）归位 types.py，__init__ 全量再导出；工作区目录注册归位 workspace.py
> （service 回归纯组合根）；RunResult 删 metrics dict 双表示改类型化字段；context 单一 groups；workspace.read
> 截断分支合并；default_store 键控缓存（消除每请求磁盘扫描与 tools.py 重复 exec）；compaction 收敛为
> plan_compaction + summarize 两步（删 Compactor/run_compaction/CompactionResult/is_summary_message）。
> v3.7 = 差距修复批（提示词/安全边界/skills，loop 区核对后与 pi 等价）：run_command 超时封顶 300s（pi MAX_TIMEOUT_SECONDS）
> + 极端破坏性命令 deny list（rm -rf /、mkfs、dd 直写磁盘、fork bomb、关机、注册表/格式化——服务器场景必需，pi 本地靠人工确认）；
> edit_file 补 per-path lock（pi file-mutation-queue 覆盖全部文件变更）；read_file/run_command 补工具优先准则
> （pi "Use read instead of cat or sed"：查看文件用 read_file 而非 cat/type/sed，文件操作优先专用工具）；
> 技能目录递归发现（pi 递归语义，排除隐藏/node_modules/__pycache__/venv；vendor 白名单仍精确点名顶层）。
> v3.8 = 功能移植批（pi session-export/print-mode/argument-hint）+ 引用回复：会话导出 HTML 报告/JSONL
> （export.py + POST /session/export，前端导出按钮）；CLI print 模式（`python -m app.services.agent "问题"` 一次性输出，
> 工具进度走 stderr、退出码契约 0/1/130）；模板 argument-hint 全管道（frontmatter → config → 前端模板卡/CLI /tpl）；
> 引用回复（前端选中回答文本 → 引文锚点前缀发送，ChatGPT reply-to-message 同类，非 pi 机制——产品层交互）。
> Skill 资产：补 6 个技能运行依赖（python-docx/openpyxl/python-pptx/pdfplumber/defusedxml/pillow——修复已启用
> docx/xlsx 脚本不可用）；vendor 白名单扩至 9（+systematic-review-checklist、pptx、skill-creator，后者正文按
> 渐进披露裁剪 <20k + references/improving-skills.md）；共 17 技能。
> v3.9 = 深度研究可用性修复批（产品验证驱动）：thinking 接入（provider 传 DashScope enable_thinking，
> 输出 reasoning_content；部分模型快照不支持 enable_thinking+tools 组合时自动降级重试一次，增强不绑架主流程；
> AGENT_DISABLE_THINKING=true 可关）；环境行注入当前日期（compose_agent_system——模型无时钟必须由 harness 提供）；
> 技能名误调引导（SkillPolicy.intercept 第二类：模型把技能名当工具直调时回喂"用 read_skill 装载"而非裸 not found）；
> 长文分段写入纪律（scholar Phase 7：`<!-- CONTINUE -->` 锚点 + edit_file 续写——单次输出上限为平台硬限，
> 长制品靠分段而非缩短）；预算估算对齐 wire（reasoning 不发回模型故不计入预算——thinking 开启后修复假性 context_overflow）；
> report-writing/scholar/kb-retrieval 篇幅与引用纪律补齐（正文 6000-10000 字；authors 缺失写"（作者未收录）"
> 不得用 paper_id 顶替）；CLI 预算对齐产品配置（120k/120 轮/900s）；scholar 技能正文工具名修正
> （tavily_search→scholar_web_search）；技能 scripts 同步抽出 sync_skill_scripts（service/CLI 共用）。
> v3.10 = 交付契约批（通用机制，产品验证驱动）：**get_follow_up_messages 钩子**（pi getFollowUpMessages 位点：
> agent 本要自然停止时由策略层决定是否续跑；FollowUpContext 只含 run 事实——消息、终稿、工具计数、可用工具、
> 已装载技能、读/写文件、注入次数、剩余秒数，循环零业务知识）；**技能交付契约**（SKILL.md frontmatter
> `completion:` 声明阶段产物：工具最低调用次数 + 交付物后缀与最低字数；声明了契约的技能自动获得交付前闸门，
> 缺项即注入续跑指令；`SkillCompletionPolicy` 最多 3 次、剩余 <180s 不再打回——一次补跑实测 2-3 分钟，
> 打回只会撞 deadline 把「已完成」变成「超时」）；工作区根唯一化（会话 + 上传从"各挂一套同名工具、ToolRegistry
> 直接构造失败"改为内容同步进会话工作台，`mount_workspace_into`）。
> 驱动证据：同一 prompt 修复前 13 轮 / 1 次检索 / 3338 字收工；闸门上线后 39 轮 / 6 检索 + 12 精读 + 3 引文追溯 /
> 9586 字，闸门恰好触发一次（模型自行补齐 Phase 4 与篇幅）。配套：scholar 声明 completion 契约，并要求补写后
> 核对实际字数（实测模型补写后仍沿用旧数字，自评附录与交付不一致）。
> v3.11 = 精简与通用性批（"随时可装载一切技能"）：**技能装载分信任级**——第一方根严格
> （校验错误=装载失败）、外部根隔离（单个坏技能跳过并告警，不拖垮整座技能库，`SkillRoot.strict`）；
> **缓存按内容签名失效**（新增/改/删技能目录下一次取用即生效，不再需要重启进程或手工失效，
> 删除已成死代码的 `invalidate_store_cache`）；**SKILLS_VENDOR 语义重定义**（空=全部启用、
> `none`=关闭、列表=仅启用列出的）；**pinned 预算与上下文同源**（`max_context_chars × 0.6`，
> 删掉写死的 40k——技能正文总量已 91k，装载第三个技能就被拒）；**技能脚本懒同步**（`after_tool_call`
> 钩子：装载某技能后才把它的 scripts/ 同步进工作区；此前每个请求把整个技能库 1.6MB 搬进每个会话
> 工作区，且把 docx/pptx/xlsx 的 XSD 模式树倒在无关任务的工作区里）；**重复实现归一**——
> char 计数（`context.message_chars` 单一实现，compaction 复用）、模板目录与缓存（`prompt_templates.py`
> 持有 `PROMPTS_DIR` + `prompt_templates()`，service/CLI 共用，消掉三处 `parents[3]/'prompts'`）、
> workspace 符号的 `noqa` 伪注释改为显式 `__all__` 契约；**通用 work prompt 去业务泄漏**（工作区
> 段不再点名 research_state.json，研究状态文件名归技能正文）；**提示词冲突修复**：`SKILL_DOC_POINTER`
> 原写"仅当用户问到技能本身时才读 references/"，与技能正文"详细方法论按需装载"直接冲突（等于关掉 L3），
> 改为只描述机制；**技能悬空引用修复**（scholar 正文的 `references/source_selection.md` 不存在、
> 脚本路径多写了 `skills/` 前缀导致模型跑不到状态脚本、只好手写另一套 JSON）——新增引用完整性检查。
> deep 模式 run 预算 15→30 分钟（实测全长请跑已超 11 分钟），预算表 `RUN_DEADLINE_S[mode]` 与
> `TEMPERATURE[mode]` 同为按模式的业务策略，service/CLI 共用。
> v3.12 = 上游 400 可诊断性 + 闸门覆盖强制技能：**上游响应体必须读出来**（此前 400 只映射成一句
> "模型不支持当前请求参数"，真正原因——参数不支持/输入超限/消息序列非法——被丢弃，等于断掉唯一的
> 证据链；现在 `_status_error` 带上游原文摘要、`app.agent` 记 WARNING）；**400 纳入重试**（实测同一
> payload——9 工具 + enable_thinking + 12 万字符中文上下文——可反复成功，长度/参数/消息序列逐一排除，
> 线上偶发 400 压倒性是上游瞬时状态；`max_retries` 1→2，退避 0.5s/1s，代价恒定）；**闸门覆盖 forced 技能**
> （用户显式选择技能时正文直接进系统提示、不经 read_skill，`loaded_skills` 为空 → 交付契约在最该生效的
> 路径上完全不触发，实测强制技能跑完 11 轮只有 4 次检索/1 次引文追溯/6578 字节报告却静默通过；
> `SkillCompletionPolicy(forced=…)` 与装载集合并判定）。
> v3.13 = 工具参数 JSON 与 pi 对齐（`json_repair.py`，移植 pi `packages/ai/src/utils/json-parse.ts`）：
> 线上实测 400 原文为 `The "function.arguments" parameter of the code model must be in JSON format`——
> 模型写大文件时参数被输出上限截断，我们**把残缺 JSON 原样回传**，上游拒收整轮请求且重试无用
> （只要那条消息还在上下文里就必然复现）。pi 的做法是参数在 AI 层就解析成对象、wire 上
> `JSON.stringify` 回传，因此合法性是结构性成立的；其解析走 `repair → partial → partial(repair) → {}`
> 阶梯（`parseStreamingJson`，在 `toolcall_end` 定稿）。本仓库按同一阶梯对齐：新增 `json_repair.py`
> 承载 `repair_json`/`parse_json_with_repair`（逐行移植）与 `parse_partial_json`（pi 依赖 npm
> `partial-json` 包，此处本地实现同一思路，不引第三方依赖），provider 在构造 `ToolCall` 时规范化参数
> （**截断参数保留已写完的字段**，不再整份丢成 `{}`），`context.wire_arguments` 作为装配请求的兜底。
> 截断调用的回喂文案补上正确恢复方式（分段写入）。
> v3.15 = 文件工具与 pi edit-diff.ts 全面对齐：**edit_file 升级为 pi 的模糊匹配语义**
> （精确优先 → 归一空间匹配：每行尾随空白、智能引号→ASCII、Unicode 破折号→连字符、特殊空格→普通空格；
> 行级改动叠加回原文、未改动行保留原字节；空 old_text / 区间重叠 / 无实际变更 全部拒绝；BOM 与 CRLF 行尾保留）；
> 这是 pi 工具集里我们最后一个明显简化项——之前只是"唯一精确匹配"，模型复制的 old_text 带一个
> 智能引号或尾随空格就整条失败，而 pi 在归一空间里找。回归测试单列 test_edit_fuzzy.py（4 项）。
> v3.14 = 全面对齐 pi 内核（"别再让我遇到这样了"）：**ToolCall.arguments 改为解析后的对象**
> （`dict`，pi `Record<string, any>` 同型）——解析在 AI 层完成（json_repair 阶梯，绝不抛错），
> 于是"回传上游的 function.arguments 恒为合法 JSON"从兜底变成结构性事实；事件/持久化/前端契约保持
> `arguments: string` 文本（runtime 事件序列化、message_to_dict 写对象、message_from_dict 容错解码
> 旧文本）；所有消费点移除 JSON.parse（registry 校验对象、compaction/skills 直接用 dict）；**工具执行
> 默认 parallel**（pi types.ts:267）；**技能校验失败=告警跳过**（pi harness/skills.ts diagnostics 口径，
> 坏技能只影响它自己，删除 SkillRoot.strict 两级配置）；修复 parallel 预检元组位次 bug（ToolResult
> 被误当成待执行项送进并发执行）。
> v3.16 = 报告图片产物直出：新增 `GET /assets/{session_id}/{path:path}`——会话工作区图片产物的
> 稳定 URL（报告 markdown 按 `/api/v1/agent/assets/<session_id>/<相对路径>` 内嵌 `<img>`），
> 路径进 path 段而非 query，同一张图恒定一个 URL、可按 URL 命中缓存；owner 隔离与路径禁闭
> 不在此重做，仍由 `read_session_file` 收口，本层只定响应头（`private, max-age=300` + `inline`
> + `nosniff`）。`workspace._TEXT_MEDIA_TYPES`（名字沿用，已含图片后缀）扩 png/jpg/jpeg/webp/gif/svg；
> inline SVG 按活动内容处理：字节来自模型/被上传文档左右的工作区，而浏览器只打同源 `/api/v1`
> （Next 微后端转发），直接打开该 URL 即同源存储型 XSS 面——保留 inline（attachment 会让报告缩略图
> 失效）但附 `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'` 关掉脚本与外链。
> 遗留（未改，待产品决策）：`text/html` 产物在两个端点仍以 inline 直出，同类风险未加 CSP。

## 1. 定位与分层

```
平台业务层（Chat / 智能搜索 / Deep Research：会话、SSE、引用校验、产品文案）
        ↓ 唯一依赖入口：from app.services.agent import ...
AgentRuntime（turn 循环 · 事件 · 预算 · 取消）+ SkillStore（Agent Skills 装载）
        ↓
Tool 实现（基座 Tool 协议）→ ModelProvider（OpenAI 兼容流式）→ 外部服务
```

基座不 import 任何现有 service（chat/knowledge 等），可脱离前端用 pytest 独立验证。
业务层持有的状态（会话、消息持久化）通过 `history` 参数传入，runtime 每次 run 无状态。

## 2. pi → ShenZhi 映射总表（拿来主义清单）

### 2.1 照搬语义

| pi 的机制（源码位置） | 我们的对应 |
| --- | --- |
| turn 循环：prompt → 流式 assistant → toolCalls → toolResults → 重复（`agent-loop.ts` runLoop） | runtime 主循环同构 |
| 顺序工具执行（pi 默认 parallel，`agent-loop.ts:420` 分支；SZDR 显式选 sequential） | 只做 sequential（确定性/引用顺序/transcript 可恢复） |
| 事件是纯观察流（`agent.subscribe`） | `on_event` 同步回调，绝不阻塞循环 |
| 工具错误契约：throw → is_error 回喂；未知工具/参数校验失败 → is_error（`agent-loop.ts` prepareToolCall） | ToolRegistry 同款 |
| beforeToolCall/afterToolCall 钩子，执行顺序 = **validate → before → execute → after**；钩子自身异常 → is_error 结果，不炸 run（`agent-loop.ts:607-765`） | `before_tool_call` / `after_tool_call`（签名见 §6） |
| **`stopReason == "length"` 时该消息全部工具调用判失败**（参数可能被静默截断，不能执行；`agent-loop.ts:379-404`） | 采纳（原文见测试矩阵 #16） |
| 失败也保证终态事件（pi 合成 stopReason=error/aborted 的 assistant 消息走完整事件序列；`agent.ts:511-527`） | `run_end{status: failed/stopped}` 必达（取消路径除外，见 §9） |
| Usage 挂最终消息并累计（`ai/types.ts:383`） | Finish 带 Usage，RunResult 累计，AssistantMessage.usage_tokens 挂消息（compaction 真实用量估算用） |
| skills 清单/装载格式函数（`harness/system-prompt.ts` 全文 34 行） | **逐字移植 Python**（§10.2） |
| **系统提示骨架：身份 → 动态工具清单（visibleTools，`coding-agent/system-prompt.ts`）→ 准则 → 技能指针** | `compose_agent_system`（§6a）：基座 prompt 通用，工具/业务准则注入 |
| **每工具 promptSnippet（清单单行说明）+ promptGuidelines（工具专属准则，随挂载注入 Guidelines；各工具 `coding-agent/src/core/tools/*.ts`）** | `ToolSpec.snippet` / `ToolSpec.prompt_guidelines`（§6）；workspace 四工具已补，edit/write 准则逐条移植 |
| name/description 校验规则（`harness/skills.ts:310-330`） | 同规则集（严格度分歧见 §15） |
| frontmatter 解析：CRLF 归一（`harness/skills.ts:336`）；BOM 剥离是 SZDR 补的 | 两者都做 |
| messages 可序列化、可作恢复输入（`initialState.messages` / resumeMessages） | `history` 参数 + message 编解码函数（§4） |
| compaction 摘要消息前缀 `COMPACTION_SUMMARY_PREFIX`（`harness/messages.ts`） | `<context_summary>` 包裹（§8.0；前缀句式是我们的中文化对应） |

### 2.2 改造（拿思想、按本项目约束改实现）

| pi 的机制 | 我们的改造 | 理由 |
| --- | --- | --- |
| Agent 有状态，多 prompt() 共享 transcript | AgentRuntime **run-scoped**，history 参数传入 | 会话归业务层（chat sessions 先例）；SZDR 也是每 run 新建 Agent |
| AbortController/AbortSignal | **stop 事件**（业务停止→优雅返回 stopped）+ 外部 CancelledError 清理终态后**重抛** | Python 结构化并发语义；业务停止与进程关闭分流 |
| transformContext + convertToLlm 两个钩子 | `context.assemble` 一个确定性函数（预算内建） | 仓库两次选择确定性字符预算（48k/60k 先例），不做 LLM compaction |
| shouldStopAfterTurn 钩子（提前优雅停） | max_turns / max_tool_calls / deadline 内建配置；预算超限 → is_error 回喂让模型自然收尾 | 配置参数比钩子简单；回喂比硬停温和（SZDR 的 BUDGET_MESSAGE 同思想） |
| streamFn "绝不抛异常，失败编码进流"（`types.ts:23-27`） | provider 抛 BusinessError，runtime 统一捕获 | Python 惯用法；终态保证等价 |
| 工具 execute(id, params, signal, onUpdate) | execute(call, args)；取消靠 CancelledError 穿透 + 每工具 asyncio.timeout | 无 signal 惯例；progress（onUpdate）推迟 |
| pi 的 ToolResultMessage 带 details（结构化给 UI） | `ToolResult.terminal`（结构化直出给 RunResult.output） | 服务端"最终制品直出"通道（引用零失真的关键，v3.1 #1） |

### 2.3 不拿（记录 + 将来加法路径）

| pi 机制 | 不拿理由 | 加法路径 |
| --- | --- | --- |
| replay 恢复策略（`types.ts:403`，断点重放执行副作用工具） | resume 从 turn 边界继续，本身不重放；v3.5 已把 replay 字段移植为元数据标记 | Checkpoint 重放引擎出现时按 spec.replay 过滤 |
| thinkingLevel / sessionId 缓存透传 / getApiKey / ThinkingBudgets | 模型配置静态（env）；DeepSeek 缓存自动 | provider 参数化时加 |
| CustomAgentMessages 声明合并扩展 | Python 无此机制；封闭 union 够用 | union 加成员 |
| SessionManager / 会话树 / ModelRuntime / TUI | coding-agent 产品层 | 业务层自行决定 |

**v3.5 起从"不拿"移出**（用户拍板全部借鉴，均带默认关闭/等价默认值）：steer/followUp 队列（RunChannel，§8.6）、
parallel 工具执行（§6，默认仍 sequential）、prepareNextTurn/shouldStopAfterTurn 钩子（§8.7）、
addedToolNames（latent 工具，§6）、compaction（v3.3 已移出，§8.0）。

## 3. 模块结构

```
apps/backend/app/services/agent/
├── __init__.py     # 唯一公共出口（全量再导出，= pi index.ts）
├── types.py        # 消息/ToolCall/ToolResult/事件/RunResult + 运行控制契约（RunChannel/StopContext/NextTurn）
├── provider.py     # OpenAI 兼容流式 + tool_calls 归并 + 重试退避 + onPayload/onResponse 观测
├── tools.py        # ToolSpec/Tool/@tool/ToolRegistry（prepare→execute_prepared 拆分，校验→钩子→执行）
├── context.py      # wire 装配 + 轮组预算截断 + pinned 豁免（含轮组级）+ context_overflow
├── compaction.py   # LLM 压缩：plan_compaction + summarize 两步（pi 形状），runtime 编排（§8.0）
├── runtime.py      # AgentRuntime：turn 循环（对 skills 零引用，业务差异走 tool_policy）
├── memory.py       # Checkpoint（含 compaction 摘要与 run 级状态）+ 可插拔存储
├── skills.py       # SkillStore + read_skill + SkillPolicy（技能运行时语义 = 钩子实现）
├── prompt_templates.py  # 提示词模板：prompts/*.md + $1/$@/ARGUMENTS 替换 + argument-hint（v3.5，§10a）
├── export.py        # 会话导出：messages → HTML 报告 / JSONL（v3.8，pi session-export 移植）
├── workspace.py    # chroot Workspace + 平台目录注册（会话/上传工作区、产物文件访问）
├── service.py      # 组合根：动态 system 装配 + 事件桥接（工作区能力 re-export 自 workspace）
└── cli.py          # 终端会话（/tpl 模板命令、! 插话、薄 CLI）

依赖方向（单向，= pi 的 ai→agent→harness→coding-agent）：
types ← tools ← provider ← runtime ← service/cli；skills/compaction/prompt_templates/memory
只被 runtime 装配与 service 使用，**runtime 的循环执行路径不 import skills**。

apps/backend/prompts/         # 提示词模板目录（.md 即模板）
apps/backend/skills/          # 第一方 skill（SKILL.md + references/ + tools.py 可执行）
apps/backend/skills_vendor/   # 外部 skill（仅 .md 被读取，.py 物理上永不 import）
```

## 4. 核心类型（types.py）

```python
class StopReason(str, Enum):
    STOP='stop'; LENGTH='length'; TOOL_CALLS='tool_calls'
    MAX_TURNS='max_turns'; ERROR='error'; CANCELLED='cancelled'; TIMEOUT='timeout'
    # pi 另有 pending/deferred，无对应场景不设

@dataclass(frozen=True)
class ToolCall:
    call_id: str; name: str; arguments: str      # 原始 JSON 文本，执行前才校验

@dataclass(frozen=True)
class ToolResult:
    call_id: str; name: str; content: str        # content=喂模型的文本
    is_error: bool = False
    terminal: Any = None                         # 非 None：最终制品直出（§8.4）

@dataclass
class UserMessage: text: str
@dataclass
class AssistantMessage:
    content: str = ''; reasoning: str = ''
    tool_calls: tuple[ToolCall, ...] = ()
    stop_reason: StopReason = StopReason.STOP
@dataclass
class ToolResultMessage:
    call_id: str; name: str; content: str
    is_error: bool = False; pinned: bool = False  # pinned=read_skill 等指令性内容，截断豁免

AgentMessage = UserMessage | AssistantMessage | ToolResultMessage

@dataclass(frozen=True)
class AgentEvent:
    seq: int; turn: int; name: str; data: dict    # seq=run 内排序号（非重放游标，重放归业务层事件日志）

@dataclass
class RunResult:
    stop_reason: StopReason
    status: str            # done | stopped | failed | timeout（属性推导）
    messages: list[AgentMessage]   # 永远是合法可续输 transcript（批次闭合保证，§8.5）
    final_text: str; final_reasoning: str
    output: Any = None     # terminal 工具直出的结构化制品（不经模型转述）
    turns: int; duration_ms: int; error: BusinessError | None
    truncated: bool; prompt_tokens: int; completion_tokens: int

def message_to_dict(m: AgentMessage) -> dict: ...
def message_from_dict(d: dict) -> AgentMessage: ...   # 持久化/恢复编解码（round-trip 测试）
```

## 5. Provider（provider.py）

- `ModelRequest{model, messages(wire), tools, temperature?, max_tokens}`；`OpenAICompatProvider` 是唯一内置实现（DashScope/DeepSeek/任意 OpenAI 兼容端点）。
- 流式事件：`TextDelta / ReasoningDelta / ToolCallEvent(完整归并后) / Finish(stop_reason, Usage|None)`。
- **tool_calls 归并**：`delta.tool_calls` 按 `index` 累积；首帧带 id/name，后续帧仅 arguments 片段（供应商重复发 id/name 也容错——赋值覆盖）；流结束按 index 排序一次性产出。归并完再发 Finish。
- **重试**（零增量原则）：仅当未收到任何语义帧（text/reasoning/tool_call）且异常 ∈ {连接错误, 408, 429, 5xx} 且剩余 deadline > 2s → 退避 0.5s 重试一次。已有产出后断流 → "模型连接中断，可以继续生成"。400/401/403 立即失败。
- reasoning 模型（reasoner/r1/qwen3 正则）：max_tokens=8192、不传 temperature；`reasoning_content` 译为 ReasoningDelta。
- 与既有 `services/model_provider.py` 的关系：自含实现（必须解析 tool_calls）；chat 迁移基座的同一变更内删除旧文件，平行期有明确终点。

## 6. 工具层（tools.py）

```python
class Tool(Protocol):
    spec: ToolSpec    # name(^[a-z][a-z0-9_]{1,63}$)/description/parameters(JSON Schema)/timeout_s/params_model
                      # + snippet（系统提示工具清单单行说明）/ prompt_guidelines（工具专属准则，随挂载注入）
    async def execute(self, call: ToolCall, args: Any) -> str | ToolOutput: ...

BeforeToolCall = Callable[[ToolCall, Any], Awaitable[ToolResult | None]]   # None=放行；返回结果=阻断
AfterToolCall  = Callable[[ToolCall, Any, ToolResult], Awaitable[ToolResult | None]]  # None=保留原结果
```

**执行顺序（pi 源码核对版）**：参数校验（pydantic）→ `before_tool_call`（返回结果=阻断，is_error 带原因）→ 执行（`asyncio.timeout(spec.timeout_s)` 包裹）→ `after_tool_call`（可替换结果）。**任何一步失败（含钩子自身异常）→ is_error ToolResult 回喂模型**；唯一例外 CancelledError 穿透。

- `@tool(name=..., params=PydanticModel, timeout_s=..., snippet=..., prompt_guidelines=(...))` 装饰器；返回 str 或 `ToolOutput(content=..., terminal=...)`。
- `ToolRegistry.dispatch(call, before=None, after=None) -> ToolResult`；`wire()` 产出 OpenAI tools 参数；重名/非法名启动即 ValueError。

### 6a. 通用 work prompt（service.compose_agent_system，v3.4 起）

对齐 pi `coding-agent buildSystemPrompt` 的骨架与分层——**基座 prompt 通用，具体内容全部注入**：

```
IDENTITY（harness 身份，一句话，不绑定工具/业务）
可用工具：- {name}: {spec.snippet 或 description 首句}   ← 按最终注册表生成（pi visibleTools）
准则：
  BASE_GUIDELINES（通用工作准则：直接执行/模糊声明解读/正文只答案/简洁/路径清晰）
  {各挂载工具的 spec.prompt_guidelines}                  ← pi promptGuidelines：只随挂载出现
  {业务注入 guidelines}                                   ← build_run_runtime 传 RESEARCH_GUIDELINES
技能参考文档指针（read_skill file 用法，"仅当用户问到时才读"）
{extra_sections：工作区提示/强制技能/挂载说明，追加式}
```

向后兼容：`AGENT_SYSTEM` 保留为 `compose_agent_system(())` 基线；cli.py 注入 RESEARCH_GUIDELINES 保持科研终端语义。

## 7. 上下文装配（context.py）

- 轮组 = UserMessage 起组到下一 UserMessage 前；截断以组为原子单位、从最旧整组丢弃（tool 消息永不离开其 assistant(tool_calls) 父）。
- 预算闭合：`system + pinned 总量 + 工具 schema + 当前输入 + 输出预留 + 历史 ≤ max_context_chars`；
  - run 级 pinned 总量上限（默认 40k，随 Phase 2 read_skill 交付——Phase 1 无代码能置 pinned，不提前实现）：read_skill 装载越界 → is_error；
  - 不可截断部分自身超限 → 调 provider 前抛 `context_overflow`（failed，错误带各分项占用）。
- 普通工具结果单项 > 8k 截断加 `…[工具结果已截断]` 标记。
- `to_wire(system, messages) -> list[dict]`（user/assistant/tool 三角色，assistant 带 tool_calls 数组，tool 带 tool_call_id）。

## 8. 运行时语义（runtime.py）

### 8.0 compaction（compaction.py，v3.3 起）

pi `harness/compaction` 的语义移植，与 §7 的确定性截断并存（压缩失败/历史太短 → 回退 assemble 截断，run 绝不因压缩失败而失败）：

- **触发**（turn 首prepareNextTurn 位点）：占用估算 ≥ `compaction_at × max_context_chars` 时压缩。估算优先最近 assistant 消息的真实用量（`usage_tokens`，pi 把 usage 挂最终消息），其后消息按字符启发式；无用量回退全量字符估算。
- **保留近期**：按 `compaction_keep_chars`（默认 80k 字符 ≈ pi keepRecentTokens=20000）从最新往回保留完整轮组原文；更旧的轮组折叠。
- **结构化摘要**：Goal / Constraints & Preferences / Progress / Key Decisions / Next Steps / Critical Context 固定模板（pi SUMMARIZATION_PROMPT 移植），对话以 `[User]/[Assistant]/[Assistant tool calls]/[Tool result]` 序列化（工具结果单条截 2k）。
- **迭代摘要**：已有摘要走 UPDATE 路径（previousSummary + `<previous-summary>` 注入），保留旧信息只增不丢；跨 run 从 history 首条 `<context_summary>` 消息恢复。
- **文件清单**：read_file/write_file/edit_file 聚合为 `<read-files>`/`<modified-files>` 追加到摘要尾部，跨 compaction 累积，随 Checkpoint 持久化。
- **本基座扩展**：pinned 轮组（read_skill 指令）整组永不折叠、也不进摘要序列化。

### 8.1 唯一执行原语

```python
async def run(self, prompt, *, history=(), on_event=None,
              stop: asyncio.Event | None = None) -> RunResult
```

`stop` 是业务停止通道（用户点停止/末订阅者断开）：三处检查点（轮首/每个流事件后/每个工具前）优雅停止，返回 `stopped`。
外部 CancelledError（进程关闭/父任务取消）：终态落盘后**重抛**。无 `stream()`——观察走 `on_event`。

### 8.2 turn 循环（完整生命周期）

```
emit run_start
while True:
    stop? → finalize(CANCELLED) → break
    turn += 1
    wire = assemble(...)                      # context_overflow → failed
    assistant = stream provider               # delta 逐事件 emit；stop 检查
    emit turn_end{turn, stop_reason, truncated}
    stop_reason ≠ TOOL_CALLS → finalize → break
    stop_reason == LENGTH 且有 tool_calls → 全部判失败（参数可能截断，§2.1）→ 下轮模型重发
    turn ≥ max_turns → 批次闭合（§8.5）→ finalize(MAX_TURNS) → break
    for call in tool_calls:
        stop? → 批次闭合 → finalize(CANCELLED) → break
        已用 ≥ max_tool_calls → is_error("工具预算已耗尽，请基于已收集的证据作答")
        result = dispatch(call, before, after)
        result.terminal is not None → append/emit → finalize(STOP, output=terminal) → break  # §8.4
        append ToolResultMessage; emit tool_end
emit run_end（外部取消路径不发；stop 优雅路径照发）
```

### 8.3 超时三层：总 deadline（`asyncio.timeout` 包循环）｜每工具 timeout（转 is_error 续跑）｜传输超时（httpx，provider 内）。

### 8.4 terminal 直出：工具返回 `ToolOutput(terminal=payload)` → 运行立即终态化，`RunResult.output = payload`（报告+来源等结构化制品**不经模型转述**，引用编号零失真）。模型调用前的发言仍保留在 messages。

### 8.5 批次闭合（transcript 永远合法）：max_turns 达限、stop 停止、外部取消——**任何路径下未执行的 tool_call 都合成 is_error（"未执行：…原因"）结果追加进 messages**。`RunResult.messages` 可原样作为下次 `history`（上游不会因悬空 tool_call_id 拒绝）。回归测试锁死。

### 8.6 运行中消息注入（RunChannel，v3.5）

pi steer/followUp 队列的移植：`run(prompt, channel=RunChannel())`，调用方在运行期间持有 channel 写入——

- `channel.steer(text)`：下一模型请求前注入（工具批不被跳过，pi getSteeringMessages 位点）；
- `channel.follow_up(text)`：run 本会自然停止时若有排队则作为新输入续跑，否则正常终态；
- `get_follow_up_messages(FollowUpContext) -> Sequence[str]`（v3.10，pi getFollowUpMessages 位点）：**策略层**在
  agent 本要停止时判断"还没做完"并注入续跑消息；排队追问为空时才轮到它（pi agent-loop 同序）。pi 的 follow-up
  来源是队列，这里把同一位置同时开放给策略——循环仍然零业务知识，一切业务判定在应用层。
- 注入的消息发 `message` 事件（data: text/kind=steer|follow_up），进入 transcript 与 RunResult.messages；
- 自然停止的 finalize 延迟到 follow_up 检查之后（`_NaturalStop`），error 终态不被 follow_up 挽救。

CLI 演示：运行中终端输入 `!内容` 即插话。服务端 SSE 场景的消费通道由业务层按需桥接。

### 8.7 轮级钩子（v3.5 / v3.10）

- `should_stop_after_turn(StopContext) -> bool`：每个完成的 turn 后调用，True → 优雅终态 STOP（pi 同名钩子）；
- `prepare_next_turn(StopContext) -> NextTurn(model=…, temperature=…)`：下一轮请求前调用，可换模型/温度（pi AgentLoopTurnUpdate；context 替换由 compaction/截断承担故不提供）。
- `get_follow_up_messages(FollowUpContext) -> Sequence[str]`：自然停止位点的续跑策略（见 §8.6）。
- 三钩子只在循环继续路径（工具轮 / follow_up 续跑 / 自然停止）上执行；钩子异常按观察通道处理不炸 run。

`FollowUpContext` 是**只读 run 事实快照**：messages、stop_reason、final_text、turn、executed_tools、
tool_calls（工具名→次数）、available_tools（本 run 实际可用的工具，latent 未启用不算）、loaded_skills、
read_files / modified_files（按 pi extractFileOps 从工具调用现算）、interventions（本 run 已注入次数，供限流）、
remaining_s（距 deadline 的剩余秒数）。策略与循环的唯一契约就是它——加字段是向后兼容的。

## 9. 事件协议

| 事件 | data |
| --- | --- |
| run_start | run_id, model, resumed, tools[] |
| turn_start | turn |
| message | text, kind=steer\|follow_up（v3.5，注入消息） |
| delta | text? / reasoning? |
| tool_call | tool_call_id, name, arguments |
| tool_end | tool_call_id, name, is_error, duration_ms, summary(≤200 脱敏) |
| turn_end | turn, stop_reason, truncated |
| compaction | before_chars, after_chars, read_files, modified_files（v3.3，§8.0） |
| tools_enabled | names[]（v3.5，latent 工具被结果启用） |
| run_end | status, stop_reason, turns, duration_ms, error?{code,message} |

正常/失败/超时/优雅停止必发 run_end；外部取消不发（消费方已离开）。seq 是 run 内排序号；断线重放由业务层事件日志承载（chat 的 Message.events + Last-Event-ID 是现成先例），基座 v1 不内建。

## 10. Skill 机制（skills.py，Phase 2）

### 10a. 提示词模板（prompt_templates.py，v3.5）

pi harness/prompt-templates 的移植：`prompts/*.md` 即模板（frontmatter 可带 description/argument-hint，缺省取正文首行 60 字符）；正文支持 `$1`/`${@:N}`/`${@:N:L}`/`$ARGUMENTS`/`$@` 位置替换（pi substituteArgs 全语义）。CLI：`/tpl` 列表、`/tpl 名称 参数…` 展开。

### 10.1 目录与信任：`skills/`（第一方，tools.py 可执行，入 git 评审）vs `skills_vendor/`（外部开源，加载器永不 import 其中的代码）。vendor 不得 resident（组合校验失败）；这是**代码执行边界**，不是不可信提示词的完整隔离——引入流程靠人工评审兜底。

两个根的处理口径不同（`SkillRoot.strict`）：

| 根 | 校验失败 | 理由 |
| --- | --- | --- |
| `skills/`（第一方） | **整体装载失败** | 自家配置错误不允许以能力静默缺失上线 |
| `skills_vendor/`（外部） | 跳过该技能 + 告警 | 一个第三方目录坏掉不该拖垮整座技能库 |

`SKILLS_VENDOR` 语义（v3.11 起）：**空/未设置 = 全部启用**；`none` = 关闭整个外部根；逗号分隔列表 = 仅启用列出的。默认全开是为了"随时可装载一切技能"；需要收紧时用列表。

### 10.1a 装载缓存与热更新（v3.11）

`default_store()` 的缓存键 = 技能根配置 + **目录内容签名**（每个 SKILL.md 的 mtime+大小、tools.py 的存在性）。新增/修改/删除技能目录后，下一次取用自动重载——**加技能不需要重启进程**。签名只做 stat，不读文件、不 exec 模块，每请求可负担。

### 10.2 格式函数（pi `system-prompt.ts` 逐字移植）

```
<available_skills> 前导三行（"The following skills provide specialized instructions..."）+
  <skill>
    <name>{escapeXml(name)}</name>
    <description>{escapeXml(description)}</description>
    <location>{escapeXml(path)}</location>
  </skill> × N（disable-model-invocation=true 的不进清单）
</available_skills>
```

read_skill 装载格式（pi `formatSkillInvocation` 移植 + 一处适配）：

```
<skill name="…" location="…">
技能参考文件用 read_skill(name, file="references/xxx.md") 读取。   ← 适配点：pi 原文是
                                                                      "References are relative to {dirname}"
                                                                      （它的 agent 有文件工具自己读；我们没有）

{content}
</skill>
```

### 10.3 渐进披露三级：L1 清单常驻 → L2 `read_skill(name)` 正文（≤20k）→ L3 `read_skill(name, file=...)` 读单个 reference（路径 canonicalize 后必须仍在该 skill 的 `references/` 内；拒绝 `..`/绝对路径/符号链接；单文件 ≤100k；累计计入 pinned 预算）。
防护：重复装载 → is_error"已装载"；read_skill 结果 pinned 截断豁免。
**L4 脚本资产**（v3.11）：技能自带的 `scripts/` 也在装载该技能后才同步进工作区（`sync_loaded_skill_scripts`
挂在 `after_tool_call` 钩子上）——渐进披露同样适用于可执行资产，未装载的技能不占工作区。
pinned 预算是上下文预算的 60%（`max_context_chars × 0.6`），不是独立魔数：技能正文是常驻内容，
能吃多少由上下文预算决定。

### 10.4 校验（pi `skills.ts` 规则集）：name `^[a-z0-9-]+$`、≤64、首尾非连字符、无连续连字符、**必须等于目录名**；description 非空 ≤1024；`yaml.safe_load`；BOM/CRLF 容错；`disable-model-invocation` 标注为 pi 扩展字段。
**严格度分歧**：pi 对 name 问题是 warning 照常加载；第一方与白名单点名 vendor 任何校验错误 = 启动失败（配置错误不能静默上线，见 §10.1 的两级口径）。

### 10.5 tools.py 契约：`def build_tools(client: httpx.AsyncClient | None = None) -> list[Tool]` 工厂；SkillStore.load 求值全部工厂后全局唯一校验工具名。

### 10.5a 技能资产自检：引用完整性

技能正文里的 `references/*.md` 必须真实存在——悬空引用会让模型在 L3 读取时失败，或（实测）
改用自造内容绕过技能自带机制。scholar 曾同时有两个问题：正文引用不存在的 `source_selection.md`，
以及状态脚本路径多写了 `skills/` 前缀（模型跑不到脚本，于是手写了一套自己的 JSON，技能的
去重/饱和判定机制全部落空）。检查方式（提交前跑）：

```bash
python - <<'EOF'
import re; from pathlib import Path
for root in (Path('skills'), Path('skills_vendor')):
    for md in sorted(root.glob('*/SKILL.md')):
        body = md.read_text(encoding='utf-8')
        for ref in sorted(set(re.findall(r'references/[\w.-]+\.md', body))):
            if not (md.parent / ref).is_file(): print('悬空:', md.parent.name, ref)
EOF
```

### 10.6 system 装配顺序：业务 system → 常驻 skill 正文（resident_skills，仅第一方）→ `<available_skills>` 清单 → read_skill 使用说明。

### 10.7 交付契约 completion（v3.10）：把"走完流程"从愿望变成可判定的产物

问题（实测）：模型读完长流程说明后可以直接写一段摘要收工——"不得跳过阶段"写在准则里没有落点。
机制：**技能自己声明交付契约，harness 只做判定**——任何技能写出 frontmatter 就自动获得交付前闸门：

```yaml
completion:
  tools:                    # 阶段产物的最低证据量（工具名 → 最低调用次数）
    paper_search: 3
    scholar_web_search: 1
  artifact:                 # 交付物（本 run 写入工作区的文件）
    suffixes: [.md]
    min_chars: 6000
```

`SkillCompletionPolicy`（skills.py）是 `get_follow_up_messages` 的通用实现，判定口径：

- 只在**本 run 装载过**的技能上生效（没装载 = 本轮不涉及该流程）；
- `available_tools` 里没有的工具不要求——工具不在场不是模型的错；
- artifact 取本 run 写入工作区的**最大匹配文件**，路径仍按工作区禁闭校验（`../` 逃逸不参与判定）；
- 上限：最多 3 次提醒；剩余 <180s 不再打回（实测一次补跑 2-3 分钟，打回只会撞 deadline）；
- 契约解析沿用技能装载的严格口径：字段未知/数值非法 = 启动失败，不允许能力静默缺失。

契约数值来自技能正文写明的阶段底线（不新增流程），正文中同步注明"该契约会被核对"。新增技能只要
按同样格式声明，即自动接入——加技能不改代码。

当前声明方：`scholar-deep-research`（3 次检索 / 1 次公开渠道 / 5 篇精读 / 2 次引文追溯 / ≥6000 字交付物）。

## 11. SZDR 接入（暂缓）

SZDR（Deep Research 引擎）封装方案已设计并验证（薄 HTTP 封装 + terminal 直出），**应用户要求暂时移除**，
`skills/deep-research/` 已删除；恢复时按本文档历史方案重建目录即可。`SZDR_BASE_URL` / `SZDR_TIMEOUT_SEC`
配置保留在 .env.example 中备用。

## 11a. 智能搜索：知识底座作为 Agent 检索能力（已落地）

`skills/kb-retrieval/`（第一方技能）：`paper_search / paper_detail / citation_graph` 三个工具
包装既有 `KnowledgeService → integrations/knowledge` 边界；失败/超时 → is_error 回喂（渠道受限 ≠ 领域空白）。
引用纪律（[n] 编号 + 末尾来源列表）写在 SKILL.md；服务端引用注册表（citations.py）仍是后续增强。
检索算法归知识底座组，本基座只解决"它如何作为 Tool/Skill 接入"。

`skills/deep-research/{SKILL.md, tools.py}`。SKILL.md 要点：description 触发词（系统性调研/综述/多来源对比/深度报告；单点快答不用）；正文：问题原文传工具不改写；返回 clarify → 原样转达并停轮；并发满/超时不连环重试；追问优先基于报告。

tools.py：共享 AsyncClient（cookie jar）；首次 `GET /api/auth/me` 铸 guest cookie；`POST /api/research {"query": ...}`（非 SSE 分支）；响应 pydantic 判别联合严格校验（clarify 分支 / answer 分支，缺字段=契约错误）；answer → `ToolOutput(terminal={'report': answer, 'sources': sources})` 直出；401 → 重铸 cookie 重放一次；timeout_s=960（严格大于引擎 900s）。
部署契约：`SZDR_BASE_URL` HTTPS，或引擎侧 `AUTH_COOKIE_SECURE=false`（Secure cookie 在 http:// 上不会被回传——Codex 实验证实）。
不做（用户边界）：sessionId 取消链、Python 侧信号量、引用重编桥接。已知取舍：外层停止后引擎 run 自行跑完（≤900s）。

## 12. 测试矩阵（unittest.IsolatedAsyncioTestCase + FakeProvider/FakeTool + httpx.MockTransport，零 key）

1 单轮流式等价；2 工具往返 wire 格式（assistant.tool_calls + role:tool 闭环）；3 tool_calls 碎片归并（含重复 id/name 帧）；4 工具异常/未知工具/坏 JSON/校验失败 → is_error 回喂；5 每工具超时 → is_error 续跑；6 总 deadline → timeout；7 stop 事件优雅停（三检查点各一）；8 外部取消 → 重抛 + messages 终态闭合；9 max_turns 批次闭合（messages 合法可续输）；10 零增量重试（前/后两种）；11 429/401 错误映射；12 LENGTH+tool_calls 全判失败；13 轮组截断 + 孤儿安全 + pinned 豁免；14 pinned 越界 → read_skill is_error（Phase 2 随 skills.py 交付）；15 context_overflow；16 terminal 直出（output 不经模型）；17 message 编解码 round-trip；18 钩子顺序与钩子异常→is_error；19 事件序列与 run_end 语义；20 usage 累计。

Phase 2 追加：skill 全部不变量（v3.1 十条）+ vendor demo 四步流程 + 真实引擎 E2E。

v3.10 追加：follow-up 策略续跑与自限流（`test_follow_up_policy_refires_at_natural_stop`）；交付契约解析
（合法/缺省/五类非法配置）；闸门判定（未装载不判、工具不在场不要求、达标放行、提醒上限、剩余时间不足不补跑、
artifact 字数与路径逃逸）；run 内注入后续跑（`test_runtime_gate_injects_then_stops`）；会话 + 上传共用工作区根
（`test_session_and_upload_share_one_root`）。

v3.11 追加：装载两级口径（外部根隔离 vs 第一方严格）；缓存随目录内容签名失效（`test_store_cache_follows_directory_content`，
含新增/删除技能即时可见）；`SKILLS_VENDOR` 三态语义；脚本懒同步（`test_scripts_sync_on_load_only`——
装载前工作区干净、只搬已装载技能；`test_script_sync_selection`——names 选择）。

v3.12 追加：上游 400 可诊断（`test_upstream_400_detail_surfaces`——原文带进消息）；
瞬时 400 重试（`test_transient_400_retried`）；去思考降级不占外层重试（`test_thinking_dropped_on_400_before_outer_retry`）；
forced 技能触发闸门（`test_forced_skill_arms_gate`）。

v3.13 追加：`JsonRepairTests` 覆盖修复阶梯（合法/截断保字段/容器补全/控制字符/永不抛错/规范化文本合法/
wire 兜底），以及 provider 层回归 `test_truncated_tool_call_does_not_poison_next_request`（截断参数不再毒化下一轮请求）。

## 13. 阶段与验收

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| Phase 1 | 五模块 + §12 矩阵（Phase 2 项除外）+ 冒烟脚本（离线默认 / --live） | 单测全绿；--live 真实模型跑通 |
| Phase 2 | skills.py + read_skill + 不变量 + skills/deep-research + vendor demo | 不变量绿；真实调引擎 E2E；cookie 部署契约验证；deadline>960 |
| Phase 3 | citations 注册表（复用 knowledge_context 契约，经 after_tool_call 钩子）+ kb-retrieval（走 KnowledgeBaseClient 补 multistep）+ 智能搜索切 skill 模式 | 现有 chat 来源卡字段零回归 |

## 14. 配置（.env，已预置）

`SZDR_BASE_URL`、`SZDR_TIMEOUT_SEC=960`、`SKILLS_VENDOR`（空=启用全部外部技能，见 §10.1）；
`pyyaml` 声明为直接依赖（锁文件已有）。
模型 Key 沿用现有 `DASHSCOPE_API_KEY` / `DEEPSEEK_API_KEY`（二选一）。
run 预算：`RUN_DEADLINE_S[mode]` 与 `TOOL_CALL_BUDGET[mode]`（policies.py，对齐 SZDR：全模式 900s / 120 次；预算/时间用到 83% 即注入"立即开始交付"指令（runtime.DELIVERY_NUDGE_AT），等用尽才收尾只是兜底），CLI 用 deep 预算。

## 15. 与 pi 的有意分歧清单（每条带理由，防止将来"顺手改回去"）

1. run-scoped runtime（vs pi 有状态 Agent）——会话归业务层。
2. ~~sequential 为默认工具执行模式~~ **v3.14 起默认 parallel，与 pi 一致**（types.ts:267 "Default: parallel"）。sequential 仍是显式可选（`tool_execution='sequential'`），含 per-tool execution_mode 覆盖（pi 语义：sequential 工具所在批次整批顺序）。
3. provider 抛异常（vs pi streamFn 失败编码进流）——Python 惯用法，终态保证等价。
4. 预算内建配置（vs shouldStopAfterTurn 钩子）+ 预算超限 is_error 回喂（vs 硬停）。（v3.5 起钩子本身已提供，见 §8.7。）
5. 启用即严格校验（vs pi warning 照常加载）。
6. read_skill 的 L3 走工具参数（vs pi "相对路径自解析"——我们无文件工具）。
7. terminal 直出为通用能力（pi 无对应物）。
8. 取消三通道（stop 事件/CancelledError 重抛/每工具超时）替代 AbortSignal 逐层传递。
9. `ToolCall.arguments` 保持 **JSON 文本**（vs pi 的 `Record<string, any>` 对象）：我们的 Tool 协议在执行前用 pydantic 校验，文本正好承载"未经信任、执行时才校验"的契约。v3.13 起行为对齐——provider 在 AI 层用 pi 的 `parseStreamingJson` 阶梯把参数规范化为合法 JSON 文本（截断参数还原已写完字段），`context.wire_arguments` 再兜底一次；因此"回传上游的 `function.arguments` 永远合法"与 pi 等价，差别只在内部表示。


## 16. 与平台会话系统的接入说明（对上层五个问题的回答）

| 问题 | 结论 |
| --- | --- |
| Session 与 Agent Run 的关系 | 一次用户消息 = 一次 run（无状态）；Session 是业务层实体，持有消息序列。发消息时业务层从 Session 组装 `history`（`message_to_dict` 编码的 user/assistant 对）传入 `runtime.run()`，run 结束把 assistant 回复追加进 Session |
| Message 与 Agent Event 的关系 | `AgentEvent` 是进程内瞬态观察流（run_start/delta/tool_*/run_end），**不是持久化事实**；业务层照 chat 现有模式筛选翻译后写入自己的 `Message.events`（产品 SSE 协议不变）。`RunResult.messages` 是持久化的对话轨迹（tool 往返含在内，批次闭合保证合法） |
| 上下文恢复方式 | 三层：①跨轮会话记忆 = 业务层 history 回传；②run 内记忆 = 基座轮组预算装配（旧的整组丢弃，pinned 豁免）；③断点恢复 = `CheckpointStore`（turn 边界快照，`runtime.resume(checkpoint)` 续跑；v1 提供内存实现，Postgres 实现按同一 Protocol 由业务层加） |
| 停止 / 恢复 | 停止：业务层置 `stop` asyncio.Event → run 优雅终态 stopped（批次闭合）；或 SSE 断开由业务层决定是否停止（现有 chat 语义保留）。恢复：①重放 = 业务层事件日志游标（现成）；②续答 = 上次 `RunResult.messages` 作 history + "请继续" prompt；③断点 = `resume()` |
| 持久化时机 | 基座只在 turn 边界写 Checkpoint（由调用方注入 store 才写）；业务持久化（Session/消息）在 `await run()` 返回后进行——取消路径绝不阻塞 finalize |

能力清单落位：上下文管理=§7；Runtime/执行循环=§8；Provider=§5；Tool/Skill=§6/§10；附件/PDF=既有
document_parser 管线经 `/agent/run` 注入；流式=事件协议 §9；取消/超时/重试=§8.3/§5；运行状态=RunResult.status；
Memory/Checkpoint=memory.py+§16；可观测性=RunResult.metrics+`app.agent` 日志。
