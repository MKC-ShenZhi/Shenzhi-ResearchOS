# Agent 管理业务就绪度盘点

日期：2026-11-19。分支：`feat/agent-m0-integration`。范围：当前工作区代码、迁移和测试静态阅读；未运行测试，未连接数据库，未启动或停止服务。开始时 `git status --short` 为空。本次仅新增本报告。

证据标记：**T**＝实现且仓库有对应测试断言（不代表本次执行通过）；**I**＝实现但本次未取得有效运行验证；**S**＝仅接口/数据结构；**N**＝在本次相关代码范围内未发现实现；**?**＝运行环境或部署状态无法确认。下列路径均相对仓库根目录，行号对应盘点时源码。工程说明参考 `docs/engineering/architecture-confirmation.md:191,476,496,673`、`known-gaps.md` 和 `git-conventions.md`；实现判断以代码为准。

核心结论：四层已有可用的代码边界，但不是四个独立 Domain。用户归属、持久化任务领取、执行和代码级能力注册已经存在；用户跨任务额度、BudgetGrant、统一数据库能力管理尚未形成闭环。不能把 BudgetLimits 当作授权额度，也不能把 RunReport 或产品 Turn usage 当作完整用户账本。

## A. 四层架构现状

| 层 | 位置和核心模块 | 已实现 | 待验证 | 尚未实现 |
| --- | --- | --- | --- | --- |
| 用户与任务管理 | Web `clients/backend/identity.ts:14,31`；Backend `core/identity.py:46,118`、`api/agent.py:96,249`、`services/agent_sessions/service.py:21`；Agent `api/routes.py:134`、`control/repository.py:64` | T：可信身份转 owner；Session/Turn 产品投影；Task/Run 持久化；owner 查询隔离；幂等提交 | ?：真实鉴权配置、部署数据库与投影恢复；I：当前产品 usage 是否满足未来计量口径，答案目前不能假定为是 | N：套餐授权、用户额度预留/结算、跨任务限流 |
| 调度 | Agent `control/repository.py:150,189,263,327`、`worker/host.py:295` 附近的 `run_worker_forever` | T：数据库轮询、Outbox、行锁领取、Lease/fencing、失败重试、取消意图 | ?：生产并发与租约运行状态；现有 PostgreSQL 集成测试本次未执行 | N：独立 Scheduler 类/目录、用户公平调度、用户并发上限、权益感知派发 |
| 执行 | `worker/host.py:166` 的 `execute_claim`；`execution/runtime.py:173,268,482,644,792`；`execution/tools.py:132` | T：Runtime 模型/工具循环、用量累计、工具预算、取消与超时；I：Worker 汇报和模式预算收紧 | ?：真实 Provider 完整 usage；异常/中断消耗完整性；摘要消耗未计入 | N：Token 总额度执行门禁、用户级能力调用额度 |
| 能力适配 | `application/composition.py:54`；`capabilities/`；`extensions/skills.py`；`integrations/{llm,backend,web_search,public_web,paper_resource}/` | T：ToolRegistry、SkillStore、ModelRegistry；I：具体工具组装和适配器。Knowledge 经 Backend，公共网页/模型等由 Agent integration 承接 | ?：真实能力可用性、上游健康与当前部署清单 | N：统一跨类型 Capability Schema、数据库注册与管理、健康状态机、发布版本管理 |

层间边界应保持：Backend 负责产品身份、会话和权益决策；Agent 持有执行事实、任务控制与运行时门禁；共享 contracts 表达两者契约。这里是推荐演进边界，不表示权益决策已存在。不要把 Backend 的产品投影 Lease 与 Agent 的执行 Lease 合并，也不要把 Worker 当成用户账本服务。

### 调度与执行中与管理业务直接相关的事实

- `packages/agent-contracts/src/agent_contracts/tasks.py:12` 定义 queued/running/paused/awaiting_input/cancelling/completed/failed/cancelled；`runs.py:14` 定义 pending/running/completed/failed/cancelled/timed_out/awaiting_input。枚举有 paused 不等于具备完整暂停恢复产品协议。
- `control/repository.py:64` 同事务建立 Task、首个 Run、Outbox；owner＋idempotency_key 唯一键在 `infrastructure/models.py:17`。`claim_run:150` 领取 pending 或 Lease 过期的 running Run，按创建时间、`FOR UPDATE ... SKIP LOCKED` 锁 Task，再锁 Run，Lease 默认 45 秒、token 递增。Outbox 是数据库领取关联，不是已接入外部消息队列。
- `worker/host.py` 的 `run_worker_forever` 顺序 await 一次 `execute_claim`，单 Worker 循环一次执行一个任务；可有多个 Worker。Runtime 另有并行工具批次（`runtime.py:684`）。这些不等于用户级并发配额。
- `record_report:263` 校验 worker/token/过期时间，允许相同报告幂等重放，冲突报告拒绝。失败或超时且 attempt＜3、无取消时，新建 Run 并指数退避（`:300`）；新 Run 复制原 budget，不扣除前次消耗。Lease 接管重跑同一 Run，而不是从持久化 checkpoint 恢复模型调用。
- `worker/host.py` 的 `maintain_lease` 每 12 秒续租，取消、失租、续租异常设置 stop；`receive_controls` 将 steer 放入 RunChannel。事件持久化失败会 stop，最终可能报告 result=None。`runtime.py:323` 处理 stop/deadline，`tools.py:191` 将工具超时、业务异常转为 ToolResult，取消异常继续抛出。额度设计须涵盖上述所有退出路径，不能只接 completed。
- 测试证据：`tests/unit/test_task_runs.py:73,83,97`（owner/取消/领取）；`test_worker_takeover.py:111,121,135,198,213`（正常、接管、旧 token、重试、取消）；`test_worker_heartbeat.py:14`；`tests/integration/test_control_postgres.py:79,87,94,132`（PostgreSQL 并发幂等/冲突/取消锁顺序/Mock 隔离）。前者不能替代真实 PostgreSQL 并发验证，本次均未重跑。

## B. 用户权益与执行权限现状

### 一次任务的实际数据流

1. Web `clients/backend/identity.ts:14` 调 Better Auth `getSession`，`:31` 的 `attachIdentity` 清除传入身份头并写入已认证 user ID 或匿名 ID。Backend `core/identity.py:46` 的 `request_identity` 先校验 BFF 凭据，`:118` 的 `request_owner` 产生 `user:<id>` / `anon:<uuid>`。这证明有身份种类和归属边界，不证明有 VIP 或付费等级。
2. 会话路径由 `api/agent.py:249` 调 `services/agent_sessions/service.py:21` 的 `start_session_run`，先取 owner 所有的 Session，建立 Turn（`:58`），再通过 Gateway 提交 owner_id/session_id/turn_id/history/skills/model（`:70`）。settings 保留 `_agent_owner_id` 及 Agent task/run ID。无会话 `/run` 路径 `api/agent.py:96` 也提交 owner。两条产品提交路径均未签发 BudgetGrant，未传用户套餐预算。
3. `services/agent_gateway/client.py:60` 用 `TaskSubmissionWire` 校验提交；Agent `api/routes.py:134` 将 Wire 转 `TaskSubmission`，由 `control/repository.py:64` 持久化。`TaskRow.owner_id` 是字符串，不是对 Backend 用户表的跨库外键；RunRequest 再携带 owner。`get_task:124`、`get_run:132` 按 owner 筛选。
4. Agent API 使用服务身份（`api/routes.py` 的 router dependencies、`api/auth.py`），不接收浏览器登录会话，也不自行查套餐。Worker claim 得到 RunRequest；`execute_claim` 将 owner 传给 composition，以隔离 Workspace。身份在此仍是归属上下文，尚非执行授权凭证。
5. `integrations/llm/agent_stream.py:268,283` 构造模型请求，可请求 `include_usage`；`:347` 解析上游 usage，`:398` 通过 Finish 返回。`_parse_usage:129` 只接受完整且有效的 prompt/completion 计量。`execution/runtime.py:546` 累计到本次 Run，缺 usage 将 `usage_measured=False`。
6. `worker/host.py:134` 的 `report_payload` 序列化 RunResult；`usage` 只有在 usage_measured 为真时输出 Token 数，否则为 null。`api/routes.py:247` 转 ExecutionReport/UsageReport，`control/repository.py:263` 存入 `RunRow.report_json`。`GET /runs/{run_id}` 返回 report（`api/routes.py:162`），Backend 经 Gateway 轮询，不是已有的结算回调接口。
7. Backend `services/agent_sessions/service.py:100` 起循环读取各 Run，遇重试转下一 Run；`:132` 附近从最终 report 的 **result** 提取 prompt_tokens/completion_tokens 等，写 Turn usage 并发出 result SSE。`models/agent_session.py:65` 存 usage JSONB。无会话流由 `api/agent.py:118` 的 `_agent_task_stream` 返回结果。

### 已有结构与缺口

| 检查项 | 状态 | 依据及限制 |
| --- | --- | --- |
| 用户、Owner、Task 归属 | T | 上述链路；Backend `tests/test_identity.py:26`、`test_agent_sessions.py:180`；Agent `test_task_runs.py:73` 有对应隔离证据 |
| Budget / BudgetGrant | S / N | `agent-contracts/budgets.py:9` 只有 BudgetLimits（duration/tool_calls/model_tokens）；`wire.py:102` 提交 budget；相关 Agent/Backend/contracts 搜索未发现 BudgetGrant、grant_id、签发或核销实现。不能称已存在 Backend→Agent BudgetGrant 契约 |
| Token Usage | T，覆盖不完整 | `test_agent.py:525` 以 FakeProvider 验证两轮累计为 15/27；只证明主循环正常 Finish。`UsageReport.model_tokens` 在任一分项未知时返回 None（`budgets.py:38`） |
| Token 额度校验 | S，拒绝不支持的预算 | Worker `execute_claim` 显式拒绝任何非空 max_model_tokens，报 configured Provider 不可强制执行；并非“允许执行直到用户余额耗尽”。默认空预算仍可调用模型。单请求 max_tokens 是输出限制，不是输入＋输出或用户窗口额度 |
| 任务预留、释放、结算 | N | submit/claim/report 均无用户余额事务；重试复制 budget；Outbox delivery_attempts 也不是能力计次 |
| 用户策略、VIP/套餐 | N（身份类别已有） | 当前按 mode 选择时长与工具预算（`application/policies.py:12`）；fast/forced_skills 影响工具集，Worker 固定 allow_shell=False。没有按套餐读取权限的策略分支；settings 的 subscription 是通知设置，不是付费订阅 |
| Tool 次数统计与限制 | T/I | Runtime `:792` 放行即计入 executed_tools，包含后续参数/执行失败的调用；Worker 开 strict_tool_budget 并取 mode 与 budget 的较小值。是单 Run 全体工具总次数，不是每工具、每用户窗口限额；事件带 name 可追踪，未形成独立计量表 |
| Skill 次数统计与限制 | N（间接工具计次） | read_skill 是工具调用；SkillStore/SkillToolPolicy 不提供每技能授权次数账本，强制 skill 直接入提示不等于 read_skill 调用。`test_agent_skills.py:290` 明确断言 pinned 预算不阻止装载；不可将其当作付费技能门禁 |

### 当前用量不能直接用于权益扣减的原因

- `execution/compaction.py:270` 的 summarize 也调用 provider.stream，却仅收集 TextDelta，不返回 usage；`runtime.py:626` 未增加主循环计量。这是源码可见的计量缺口。
- Provider 流中断、超时、取消或重试的已消耗 Token 不一定有完整 Finish usage；usage_measured 不能证明所有实际调用完整入账。异常导致 Worker result=None 时报告所有 usage 字段未知。
- Backend 产品投影读取 result 而非 report.usage，未携带 usage_measured，也未汇总前序失败 Run 用量；主循环部分已知累计可能被展示为完整数字。故产品展示、执行计量、权益账本必须分别定义。
- Lease fencing 阻止旧 Worker 覆盖数据库结果，不能撤销旧 Worker 已发生的外部调用；接管同 Run、失败新 Run 都可能产生额外费用。不能用 `(task_id, run_id)` 单条终态覆盖所有调用事实。

真正已有的阻断是任务时长/工具总次数、模型未配置或禁用拒绝、owner 隔离和 Web shell 禁用；没有 5 小时/每日 Token 额度门禁，也没有单能力用户额度。Token 预算非空时直接失败属于保守拒绝，不是完整额度控制。

## C. Capability Registry 现状

| 类型 | 注册、Schema 和配置 | 启停、状态和版本 | 发现与调用 |
| --- | --- | --- | --- |
| Tool | `execution/tools.py:36` ToolSpec，`:68,88` FunctionTool/装饰器；`:132` ToolRegistry；`application/composition.py:54` 显式组装。`capabilities/` 包含 web_search/read_paper/fetch_url/knowledge/chart_tools/html/ask_user 等实现，另有 workspace、memory、skill 工具 | 构造时拒绝重复名称。latent＋enable 是运行中渐进披露，没有数据库 disable API；没有版本/健康字段 | Runtime 取 registry.wire 构造模型函数 Schema；工具调用经 prepare/execute_prepared 或 dispatch；超时、Pydantic 校验及 before/after 钩子见 `tools.py:167,191,222` |
| Skill | `extensions/skills.py:42,55` Skill/SkillRoot；`:150` load 从 SKILL.md frontmatter、正文和 references 读取；第一方可加载 tools.py/build_tools（`:226`），vendor 不 import Python。仓库第一方技能为 `apps/agent/skills/deep-research/` | `:376` SKILLS_VENDOR 支持全部/none/白名单；disable_model_invocation 只隐藏模型清单，非全局禁用。`:384,405` 内容签名缓存刷新不是发布版本。无健康状态或 DB 管理 | listing_prompt→read_skill 正文/参考文献→按提示执行；第一方工具可 latent 按加载启用；forced_skills 经 composition 直接注入正文 |
| Model | `integrations/llm/registry.py:26,44,64,90` Capabilities/ProviderSpec/ModelSpec/Catalog；resolver.py:47 的 load_registry 组合 catalog.json、环境变量及 AI_MODEL_REGISTRY_FILE；密钥从环境读取 | Provider/Model enabled、configured 校验；重复 ID 拒绝，显式覆盖生成的 legacy 条目；无探活持久化，configured 只表示配置条件满足；无独立发布版本 | ModelRegistry.resolve_model（registry.py:169）按用途、别名、默认、tool_calling 和配置解析；OpenAICompatProvider 取 Provider/upstream ID 发送请求 |

不存在覆盖 Tool/Skill/Model 的统一管理 Schema。模型的 `Capabilities` 表示模型特性，不是所有能力的注册模型；ToolSpec 的 JSON Schema 表示入参，不是统一能力元数据。`GET /internal/v1/config`（`api/routes.py:50`）输出公开模型/技能配置，经 Backend `/agent/config` 提供消费，不是 Registry CRUD。

现有测试：`test_llm_registry.py:69,143,182` 覆盖未配置/禁用/自定义文件/重复；`test_llm_config_api.py:17,33` 覆盖公开配置和能力过滤；`test_agent_skills.py` 覆盖装载、渐进披露与路径边界。真实上游健康、版本切换和管理启停没有这些测试所能证明的运行闭环。

重复与职责注意事项：

- 三种 Registry 是不同对象的注册机制，不应为了统一名字合并成一套执行引擎；Skill 可以贡献 Tool，composition 也贡献 Tool，最终 ToolRegistry 拒重名。SkillStore.load 同名保留先到项并 warning 跳过后到项（`:169`），不能推断数据库已有唯一版本管理。
- Skill 文件头宣称第一方严格失败，但 `SkillStore.load:164` 实际对无效技能 warning 后跳过；以实现为准。不要把注释视为保证。
- `integrations/llm/agent_stream.py:62,129` 存在重复 `_parse_usage`，以及相邻重复辅助定义；后定义覆盖前定义。这不是两个能力注册中心，本次不修改。
- 业务适配器与 Runtime 可执行能力描述目前分别存在；能力目录不是上游服务配置数据库。未来科研组 Deep/Auto Research 接入仍应走 Backend integrations 边界，当前 Deep Research Skill 不代表该服务已存在。

## D. 推荐代码组织与数据库边界

### 已有数据库结构

Agent ORM `apps/agent/src/agent_app/infrastructure/models.py:14,33,52,66,80` 定义五表：

| 表 | 核心内容 |
| --- | --- |
| agent_tasks / TaskRow | owner、状态、session/turn、幂等键、request_json、current_run、取消意图 |
| agent_runs / RunRow | task FK、attempt 唯一、request/report JSON、worker、lease_token/expiry、时间 |
| agent_run_events / RunEventRow | run FK、run/seq 唯一、事件名/data/turn/时间 |
| agent_run_controls / RunControlRow | run FK、run/seq 唯一、steer 文本与时间 |
| agent_outbox / OutboxRow | run 唯一 FK、available/delivered、delivery_attempts |

迁移是独立 `apps/agent/alembic.ini`＋`migrations/env.py`（Base.metadata，Agent 数据库连接），`0001_agent_task_run_event_outbox.py:13` 建前四类 Task/Run/Event/Outbox，`0002_agent_run_controls.py:13` 增 Controls，down_revision 形成线性链。迁移调用当前 ORM metadata 的 create_all，不是独立手写冻结表定义；本次不执行迁移。

**实际 Agent PostgreSQL 中有哪些表：? 暂时无法确认。** 本次没有读取本地连接凭据或查询 information_schema/alembic_version，因此以上仅为 ORM/迁移声明，不能声称已经部署。后续如需验收，应在明确目标数据库后只读核验表、列、约束和迁移版本；本报告没有以 SQLite 测试替代实际表清单。

Backend 自有 `models/agent_session.py:14,40` 的 agent_sessions/agent_turns，Turn 以 FK 归 Session，usage/transcript/settings 为 JSONB，Session.owner 为字符串；`:78` 附近 partial unique index 限同 Session 活跃 Turn，并非同用户只能一个 Task。`models/agent_upload.py` 为附件暂存；`models/profile.py`、`settings.py` 为用户资料/设置，不是权益余额。Backend `migrations/versions/007_agent_sessions.py`、`011_agent_uploads.py`、`016_request_idempotency.py` 等维护产品表，独立于 Agent 迁移。实际 Backend 部署表与版本同样未查。

共享包 `packages/agent-contracts/src/agent_contracts/`：tasks/runs/budgets/events 为传输无关 dataclass；wire.py 为 Pydantic Wire 校验；protocols.py 为协议边界。现有 BudgetLimits、UsageReport、RunRequest、ExecutionReport 可演进，但不能凭空当作授权账本协议。

### 用户权益管理的最小落点（建议，未实现）

- Backend 新增有实质职责的 `services/agent_entitlements/`，承载套餐解析、窗口预算预留、签发授权、结算和查询；相应 `models/`、`schemas/`、`api/` 按现有惯例放置。达到复杂度再拆 repository，不新建全仓 DDD 平行架构。
- `services/agent_sessions/service.py:start_session_run` 与无会话提交路径共同调用权益 Service，避免只保护会话路径。管理接口仍在 Backend；Web 仅展示权益与发起操作。
- Agent `control/` 在 submit 校验授权关联、claim 检查授权有效期/剩余额度及重试条件；`application/` 组装只允许的模型/工具/技能；`execution/` 负责统一调用前预留与调用后实测上报。Worker 负责传输上下文，不负责定义 VIP。
- contracts 新增明确 BudgetGrant/UsageDelta（命名待协议评审），扩展 Gateway 和 Agent 后端适配器；不在页面直连科研服务或另建用户系统。当前无需新增泛化 domain/ 目录；权益是 Backend 新业务模块，Agent 是执行策略与计量落点。

### 能力管理的最小落点（建议，未实现）

- 保留 ToolRegistry/SkillStore/ModelRegistry 和原生 Schema。Agent 可在 `capabilities/registry.py` 或有实际职责后设 `capabilities/registry/` 提供统一描述和策略视图；不移动现有全部工具。
- Backend `services/agent_capabilities/`＋schemas/api 管理产品可见、全局启停、套餐能力授权；Agent 管理部署清单/执行适配与运行状态。若需 Agent 持久化健康观测，可沿 infrastructure.models/control 服务增量接入，跨服务仅交换描述和策略快照，不跨库读取。
- 明确单一权威：代码描述决定“能执行什么”，Backend 管理覆盖决定“允许谁执行什么”。管理不能注册任意 Python import 路径；DB 新条目不等于代码已部署。先只读清单，再做启停与授权。
- `before_tool_call`/ToolPolicy 可作接点，但 ToolRegistry.prepare 当前只查 tools 字典，不能把 wire 隐藏或 latent 当安全检查。检查必须覆盖顺序/并行、skill 动态新增工具、强制 skill、模型别名解析与摘要调用，并在真正外调前原子取得名额。

## E. 数据模型建议（仅设计，不建表）

以下是候选实体，不要求首版全部独立成表；权益/额度事实由 Backend 持有，Agent 保存执行关联与必要调用事实。禁止把密钥或真实上游地址写入管理公共描述。

| 候选实体 | 关系与关键字段 |
| --- | --- |
| Plan / PlanRevision | plan_id、revision、名称、enabled、生效区间；权益规则快照版本。VIP 是订阅关联权益，不用散落 is_vip 分支 |
| UserPlanAssignment | owner/user_id、plan_revision、开始/到期、状态、来源；匿名默认策略明确；不把 Session 认领自动等同历史账本转移 |
| EntitlementRule | plan_revision/用户覆盖、metric(tokens/calls)、capability_id 可空、limit、window_type、window_seconds、timezone、计费口径；区分用户覆盖优先级 |
| BudgetReservation / BudgetGrant | reservation_id/grant_id、owner、task/submission 幂等键、policy_revision、预留 tokens/calls、已结算量、expires_at、状态、允许 capability/version 集、受众；Task ID 尚未产生时用稳定 submission_id 关联 |
| UsageLedger / UsageDelta | 唯一 measurement_id、owner/task/run、执行 incarnation(lease token)、provider_request_id/调用序号、capability/version、purpose(main/summary)、prompt/completion、调用数、measured/unknown/estimated、发生时间、报告时间；追加与幂等处理，不能覆盖消耗历史 |
| QuotaWindow / Counter | owner＋rule＋窗口标识，used/reserved、version；固定窗口可缓存计数，滚动窗口以带时间 ledger/reservation 为依据；并发原子检查 used＋reserved＋本次请求 ≤ limit |
| CapabilityDefinition / Revision | capability_id、kind(tool/skill/model)、code_ref、version/content_hash、原生 input Schema 引用、依赖/提供方、部署版本；唯一 kind＋code_ref＋version，展示名与稳定 ID 分离 |
| CapabilityPolicy | capability_id、enabled、禁用原因、生效时间、policy_revision、允许套餐/用户覆盖、单能力次数规则；不能用健康失败冒充管理员禁用 |
| CapabilityHealthObservation | capability/version/provider、status(unknown/healthy/degraded/unavailable)、checked_at、过期时间、错误类别；不存敏感响应。无探测时必须 unknown |

时间口径必须先定：

- “5 小时 Token 限额”建议明确为滚动 18,000 秒，不默认为固定每五小时重置；需同时扣住窗口内未结束 reservation，避免并发绕过和跨窗口释放错误。若选择固定窗口，应在协议写明锚点和重置时间。
- 每日限额建议按明确业务时区（例如 Asia/Shanghai）自然日，记录 UTC 时间和窗口边界；也可选择滚动 24 小时，但不能混称每日。两个窗口同时满足才放行，预留必须原子覆盖两者。
- Token 默认考虑 prompt＋completion（含摘要/重试真实调用），缓存 Token/推理 Token 是否已包含、未知 usage 如何暂扣、结算跨日归属、超额差额策略需与 Provider 口径统一。不能将 None 当 0。
- 单能力次数先明确按“尝试/成功”计费，以及 read_skill/reference/forced skill/skill 派生工具是否分别计数。调用开始前预留，成功或失败按策略结算，真正未外调才可释放。Skill 不是一次模型函数调用，须定义计量事件。
- 模型请求前预留输入估算及允许输出上界，并传剩余输出限制；实际输入、隐式重试、取消后用量仍有偏差，需保守预留、实测对账和未知用量隔离，不能仅事后扣减声称严格防超额。
- 终态报告、增量上报和 Backend 接收都需幂等。Run 重试/Lease 接管不能重新获得整份用户授权；失租不自动证明费用为零，reservation 也不应仅因 Lease 过期无条件返还。

## F. 最短可行研发顺序

1. **先定义跨服务契约（Backend＋Agent）**：确定权益权威、预算窗口、Token/调用口径、未知用量、幂等 ID、grant 有效期/受众/重试继承、用量增量与最终结算、禁用生效语义。BudgetLimits 保留为单次执行上限，BudgetGrant 另表述授权来源。可以立即进行，不依赖服务稳定性改造。
2. **立即可做：只读能力清单与套餐策略模型**：从三类代码注册机制导出统一描述；Backend 先支持固定默认方案和权益查询，明确代码清单与管理覆盖。无需重构 Runtime 或增加独立 Domain。
3. **计量补齐（Agent，Backend 配合消费）**：统一主模型/摘要/重试调用记录，新增调用级标识和 unknown 语义；让产品投影保留权威用量可信度。验证工具并行计数、强制 Skill、失败/取消路径。没有这一步，禁止承诺准确用户余额。
4. **Backend 原子预留＋授权提交**：覆盖所有提交入口、并发请求及幂等复用；Agent submit/claim 校验授权，Runtime 外调前执行 Token/能力预留。先落地单 Run 工具/时长收紧，再上线双窗口 Token 规则。依赖第 1 步契约，不可只在 Web 拦截。
5. **结算闭环与最小启停管理**：Backend 幂等收取消耗、释放确定未用预留、处理取消/失败/重试；Agent 运行前与每次调用前检查能力权限。健康状态先 unknown，观测接口随后增加；VIP 通过方案关联规则生效。
6. **上线强额度保证前的定向验证**：复用现有 Lease/fencing、重试和 PostgreSQL 并发测试能力，补齐“同用户多任务跨 Worker、失租后旧调用、回报丢失、摘要调用、跨窗口结算、禁用后的并行调用”等额度场景。这依赖调度/执行上述语义稳定，并需真实 Provider usage 与目标 DB 只读结构核验；无需再做全面可靠性审计。

本报告未执行全量或局部测试，未验证真实上游、数据库部署和过去测试运行结果；测试证据均为已阅读的仓库测试/断言。后续是否可上线必须依据新增管理闭环的定向验证，不能由现有任务运行测试替代。
