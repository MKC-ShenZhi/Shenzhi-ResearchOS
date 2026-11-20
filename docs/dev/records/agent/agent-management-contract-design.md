# Agent 管理业务跨服务契约设计

日期：2026-11-19。第三轮定向修订；重新核对 HEAD：`b5707ab84596af940ce25718a1a3fa6023abbcef`，与历史基线相同；分支为 `feat/agent-m0-integration`。状态：T0 技术契约批准候选，等待负责人评审；不表示协议已经正式批准、管理业务已经实现或业务规则已经批准。

本文采用三种标记：**事实**表示已阅读源码可确认的行为；**建议**表示本次提出的技术方案；**待决策**表示负责人必须明确的业务口径。除第 1 节当前实现外，后续 Schema、API、表和状态均为建议，尚不存在于当前 Contracts 或数据库声明中。

本轮只修订本文已有内容。开始时没有已跟踪文件修改；本文及同目录 `agent-management-readiness.md` 均已存在、未跟踪，不能用空的 git diff 推断本文没有既有工作。本轮在原文上定向修订，保留 readiness 原状。未修改 Contracts、业务代码、数据库模型或迁移，未运行服务、连接数据库、运行业务测试、切换分支、创建 Worktree、Commit、Push 或 Merge。现有报告仅作检查线索，不作为实现证据。

## 1. 当前实现核对（事实）

### 1.1 核对范围与依据

已结合 `docs/engineering/architecture-confirmation.md`、`git-conventions.md`、`llm-api-foundation.md` 及 `docs/agent/contracts.md` 核对下列实现。文档中的未来调度描述不能替代当前代码；不据此宣称已实现用户并发额度或 Checkpoint 恢复。

| 范围与源码定位 | 当前行为 | 管理业务缺口 |
| --- | --- | --- |
| `packages/agent-contracts/src/agent_contracts/{tasks,runs,budgets,wire,protocols}.py` | dataclass 记录与 Pydantic Wire 分层；Wire `extra=forbid`。TaskSubmission/RunRequest 带 owner、budget；Session/Turn 成对。UsageReport 用 None 表示未知。BudgetManager 协议返回 BudgetLimits、收终态报告 | 没有 BudgetGrant、submission_id、UsageDelta、统一 Capability Descriptor；协议声明不等于权益服务实现 |
| `apps/backend/app/services/agent_gateway/client.py`：AgentGateway | 服务 Bearer 调用 Agent `/internal/v1`，提交与响应均做 Wire 校验；读取全部 Task Run ID，轮询先读 Run 再读事件 | 没有授权签发、用量消费和额度账本；现有错误解析把 code 转 int，不能直接塞入字符串错误码 |
| `apps/backend/app/services/agent_sessions/service.py`：start_session_run、resume_session_run | Backend 先建 Turn，再用 `backend-turn:{turn.id}` 幂等提交 Task；保存 Agent Task/Run 关联并投影。恢复沿用 `_agent_owner_id` | Turn 不是额度预留；最终展示从 result 取 Token，缺省 0，且未保留 usage_measured，不可直接用于结算 |
| `apps/backend/app/api/agent.py`：run | 非会话路径也直接调用 Gateway.submit；当前没有稳定 submission_id/提交幂等协议 | 不能只保护 Session 路径；请求中仅有 session_id 时仍受共享 Wire 成对校验约束，本文不修复该路径 |
| `apps/agent/src/agent_app/control/repository.py`：submit、claim_run、heartbeat、record_report | Task/首 Run/派发 Outbox 同事务创建；owner＋idempotency_key 唯一且比对请求。领取提升 lease_token，过期接管同 Run；事件、心跳和首次报告校验有效租约。失败/超时且未取消、attempt<3 时新建 Run，复制 budget/history，指数退避 | 无授权账本。接管从头执行，不保证外部调用不重复。终态重放可幂等，但不能涵盖多次真实调用 |
| `apps/agent/src/agent_app/worker/host.py`：execute_claim、report_payload | 心跳失败/取消置 stop；严格工具预算；时长/工具数取模式和显式限制较小值。max_model_tokens 非空直接拒绝；usage_measured 为假时报告 Token=None | 心跳停止是协作式停止，不是上游撤销；内存事件队列不是持久用量 Outbox |
| `apps/agent/src/agent_app/execution/runtime.py`、`provider.py`、`compaction.py` | 主循环累加 Finish.usage，缺失时标记不完整；摘要直接 provider.stream，只收 TextDelta。工具并行路径 prepare 放行才占名额，顺序路径先递增再 dispatch | 两种工具计数细节不同，不能当用户付费次数。摘要 Token 未进入主循环总量；输出 max_tokens 不等于输入＋输出权益额度 |
| `apps/agent/src/agent_app/integrations/llm/{agent_stream,registry,resolver}.py` | 模型/Provider 配置、用途和别名解析；enabled/configured 门禁；请求外层重试及内层不支持参数降级均可能重新发 HTTP 请求。usage 仅完整两项时解析；未向 Runtime 暴露 provider_request_id | 一次 provider.stream 可能有多次真实请求。on_payload/on_response 钩子吞异常，不能直接承担可靠计量。文件内重复辅助定义以后定义生效，不代表两套模型目录 |
| `execution/tools.py`：ToolRegistry | 显式工具对象，名称拒重；ToolSpec.parameters 为原生 JSON Schema；prepare 校验并调用 before，execute_prepared 调用工具；latent/enable 控制披露 | prepare 从 tools 字典查找，隐藏不等于权限拒绝；无管理版本/健康状态 |
| `extensions/skills.py`：SkillStore | 从 SKILL.md/参考文件加载；无效或同名项 warning 后跳过；第一方可经 tools.py/build_tools 贡献工具，vendor 不加载 Python；缓存签名取文件 stat | disable_model_invocation 是展示控制；缓存签名不是不可变发布版本；无统一权益门禁 |
| `application/{composition,policies,facade}.py`、`capabilities/` | 组装工具、技能、模型与模式预算；forced_skills 直接注入正文。Knowledge 经 `integrations/backend/knowledge.py` 调 Backend，再接科研服务；工具还包含 Web、论文、图表等适配 | 没有 Catalog 管理和用户授权交集；强制技能与动态工具均须覆盖门禁 |

用户列出的 `apps/agent/src/agent_app/runtime/` 当前不存在；Runtime 的真实位置为 `execution/runtime.py`。不为适配目录清单创建新 Runtime 层。

### 1.2 持久化事实及核对限制

Agent `infrastructure/models.py` 声明 `agent_tasks`、`agent_runs`、`agent_run_events`、`agent_run_controls`、`agent_outbox`；派发 Outbox 是每 Run 一项，不是调用用量投递表。Backend `models/agent_session.py` 声明 Session/Turn，含 usage/transcript JSON、Turn 幂等和同 Session 活跃 Turn 唯一约束；这不是同 owner 的窗口额度锁。

本次只核对仓库静态实现，未读取本地密钥/部署地址，未验证实际 PostgreSQL 表结构、迁移版本、线上 Provider 返回或服务运行状态。本文不以现有测试文件或盘点报告代替运行验收。

### 1.3 当前 HEAD 的关键源码证据

以下为当前文件的一基行号；HEAD 与历史基线相同，因此没有已提交实现差异。本文后续字段和状态机均为待实现契约，不能据此反推源码已经支持。

| 文件（仓库相对路径） | 类 / 函数与位置 | 核验结论 |
| --- | --- | --- |
| `packages/agent-contracts/src/agent_contracts/wire.py:12`、`:91`、`:207` | WireModel、TaskSubmissionWire、UsageReportWire | extra=forbid、frozen；当前提交无 grant/submission 字段，用量仍是报告级 |
| `packages/agent-contracts/src/agent_contracts/budgets.py:8`、`:23`、`packages/agent-contracts/src/agent_contracts/protocols.py:23` | BudgetLimits、UsageReport、BudgetManager | 单 Run 限制与可空用量；协议仅 authorize / record_usage，无权益账本实现 |
| `apps/backend/app/services/agent_gateway/client.py:29`、`:60` | AgentGateway.request / submit | Bearer；整数错误码；请求和响应均按现有 Wire 校验 |
| `apps/backend/app/services/agent_sessions/service.py:20`、`:133`、`:258`、`:306` | start_session_run、resume_session_run 及投影闭包 | 稳定 Turn 提交与恢复关联；展示用量缺省 0 不可作为结算证据 |
| `apps/backend/app/api/agent.py:96`、`:118` | run、_agent_task_stream | 非会话提交入口也需纳入授权；当前结果投影同样可能补 0 |
| `apps/agent/src/agent_app/control/repository.py:64`、`:150`、`:189`、`:263`、`:302` | submit、claim_run、heartbeat、record_report 及重试分支 | 本地提交事务；领取递增租约；过期接管；失败/超时最多三个 Run，复制 BudgetLimits；无调用级门禁 |
| `apps/agent/src/agent_app/worker/host.py:134`、`:166`、`:204`、`:246`、`:266` | report_payload、execute_claim、maintain_lease | 未测量用量报告为 None；协作停止；拒绝显式 max_model_tokens；严格工具预算 |
| `apps/agent/src/agent_app/execution/runtime.py:482`、`:547`、`:664`、`:684` | _run_turn、_run_tools_sequential / parallel | 只累加主流 Finish.usage；顺序/并行工具计数边界不同 |
| `apps/agent/src/agent_app/execution/compaction.py:270`、`:287` | summarize | 直接 provider.stream，只收 TextDelta，未纳入主流 Token 汇总 |
| `apps/agent/src/agent_app/integrations/llm/agent_stream.py:129`、`:219`、`:259`、`:291`、`:347` | _parse_usage、OpenAICompatProvider.stream / _observe / _stream_once | 完整 usage 才解析；外层与参数降级均可重发；观测钩子吞异常；usage 帧覆盖变量；不能靠该钩子保证可靠上报 |
| `apps/agent/src/agent_app/execution/tools.py:132`、`:147`、`:167`、`:191` | ToolRegistry.enabled / prepare / execute_prepared | latent 控制披露；prepare 参数失败未执行；实际执行在 execute_prepared |
| `apps/agent/src/agent_app/extensions/skills.py:150`、`:181`、`:205`、`:226`、`:384` | SkillStore.load / listing_prompt / read_body / tools、_content_signature | 隐藏不阻止按名装载；第一方工具工厂；stat 缓存签名不是发布版本 |
| `apps/agent/src/agent_app/integrations/llm/registry.py:59`、`:92`、`:163`、`:179` | ModelSpec、ProviderConfig.configured、ModelRegistry.resolve_model / public_models | 精确型号、别名与用途；配置存在性不等于健康，也不是底层权重版本 |
| `apps/agent/src/agent_app/application/composition.py:55`、`:93` | build_runtime | 原生装配和 forced_skills 正文注入点，当前没有统一权限检查 |
| `apps/agent/src/agent_app/infrastructure/models.py:14`、`:33`、`:52`、`:66`、`:80`；`apps/backend/app/models/agent_session.py:14`、`:40` | TaskRow / RunRow / RunEventRow / RunControlRow / OutboxRow；AgentSessionRow / AgentTurnRow | Agent 派发 Outbox 与 Backend 产品投影分属各库；当前没有本文用量 Inbox/Outbox/账本实体 |

## 2. 总体架构（建议）

保持四层 Agent 架构、Next.js/FastAPI 边界和三个原生执行注册机制。Backend 是权益与账本唯一权威；Agent 是执行与调用事实权威；共享包只定义传输无关模型、Wire、枚举和协议，不持有数据库、套餐策略或 Provider 客户端。

```text
用户 → Web/BFF → Backend（可信 owner、Submission、权益、预留、签发）
                         ↓ Gateway：submission + BudgetGrant
                    Agent API / Control（绑定 Task、租约、调用门禁、调用事实）
                         ↓ claim / call permit
                    Worker / Runtime → ToolRegistry / SkillStore / ModelRegistry
                         ↓ 每次真实调用前登记；调用后 UsageDelta
                    Agent 持久调用日志 + 用量 Outbox
                         ↓ 至少一次投递 / 对账
                    Backend Usage Inbox → 额度结算 → 产品用量投影

Agent 原生描述清单 → Backend Catalog / 管理策略 → Grant 权限快照
Agent 部署健康观测 ─────────────────────────→ Catalog 可用性视图
```

额度控制分两级：Backend 在提交前原子预留任务额度，真正调用时由 Agent Control 经 Backend 取得调用许可并归属正确窗口；Agent Control 在自身数据库串行校验租约、Task 状态和调用启动。Worker 不直接调用 Backend 额度 API，不接触任何服务数据库。

上述 Grant/预留/Permit 链描述 A2 authorized 目标流程；A1 observation_only 只走 4.5 的 Backend 模式关联、Agent 本地事实和 Inbox 核验，不伪造该授权链。两种模式均使用 §7 新 v2 协议；旧 v1 仅保留原有契约。

选择调用前在线许可增加延迟和 Backend 可用性依赖，但能在单一账本内处理多任务与窗口切换。离线分片额度可作为后续优化，首版不同时维护第二套可花费余额。Backend 不可用时停止新增付费调用；已发生调用的事实允许延迟补报。

## 3. BudgetGrant Schema 与生命周期（建议）

### 3.1 语义和身份关联

BudgetLimits 继续表达**单 Run 的资源上限**（时长、工具总次数、模型总 Token 上限）；BudgetGrant 表达**Backend 根据用户权益授予一个逻辑提交的执行权限及共享预留**。两者均满足才可执行。不能把 max_model_tokens 填入请求便宣称已具备权益控制。

authorized 的关系为 `owner → Backend submission_id → task_id → run_id[] → execution_id[] → call_id[]`；A1 observation_only 的独立计量关联见 4.5，不冒充该身份链中的正式 Submission。一份 grant 根绑定一个 submission，最终只绑定一个 Task；所有自动重试、同 Run 接管共享其剩余预留。Session/Turn 只提供产品关联，不是授权主键。等待用户输入后形成新的用户提交时使用新 submission/grant；若未来选择恢复同 Task，须显式续授权，不自动恢复已关闭额度。

Backend 在任何远程提交前持久生成 submission_id（随机 UUID），并以 `(owner_id, client_idempotency_key)` 唯一查找。会话入口可用稳定 Turn ID 建唯一映射，但仍输出统一 submission_id；无会话入口要求客户端提供稳定提交键，网关超时后重试沿用它。无键请求若仍支持，必须先返回/持久恢复 submission 标识，不能承诺跨网络重试去重。

Backend 固化最终 prompt/history、附件内容摘要、精确模型版本、技能集合、BudgetLimits 等的规范化 `request_digest`；同提交键不同请求返回冲突。附件过期不应导致重放时重新解析出不同请求。owner 由现有身份边界产生，不信任浏览器传入的 owner。

### 3.2 推荐字段

| 字段 | 类型 / 约束 | 含义 |
| --- | --- | --- |
| schema_version | int，首版 1 | 协议版本，未知版本拒绝 |
| grant_id / reservation_id | 非空 opaque ID | 授权根与 Backend 预留；续期不生成第二份余额 |
| revision | 正整数，单调增加 | 续期/收紧权限后的不可变授权修订 |
| issuer / audience | 服务标识字符串 | Backend 签发者、指定 Agent 环境；禁止跨环境重放 |
| owner_id / submission_id | 非空字符串 | 不可变权益归属与提交关联 |
| task_id | string 或 null，字段必须出现 | 该 Revision 签发时的 Task 声明；初始 null 永久保留，绑定不修改它。根已绑定后签发的新 Revision 必填根的 bound_task_id |
| binding_receipt_id | string 或 null，字段必须出现 | 未绑定时 null；根已绑定后签发的新 Revision 必填原始根绑定回执 ID，不能换 Task 或生成第二次绑定 |
| request_digest | string | 规范化业务请求摘要；不包含可轮换签名或授权时间 |
| policy_revision / catalog_revision | string | 权益规则与能力快照版本 |
| permission_snapshot_id / permission_snapshot_digest | 非空字符串 | 7.3 不可变 PermissionSnapshot 及其规范化摘要；Grant 签名覆盖引用 |
| issued_at / not_before / expires_at | UTC RFC3339 | 服务端时间；expires_at 是新增调用截止，不是释放余额时刻 |
| capabilities | CapabilityPermission[] | 精确 capability_id/version、invocation_modes[]、purposes[]、可空 max_attempts；须为 PermissionSnapshot 允许项的子集，缺项默认拒绝 |
| allocations | 非空 Allocation[] | 见下表；显式免费授权可用 reserved_units=0 的不扣费规则，不能用空规则表示无限权益 |
| execution_constraints | object | 可选任务总截止、允许重试数；不得放 VIP 判断代码 |
| signature | object | kid、alg、compact JWS；覆盖上述全部声明（signature 本身除外） |

Window 引用包含 `window_type`、`start/end` 或 `duration_seconds`、`timezone`（自然日需要）、`anchor`（固定窗口需要）、`accounting_basis`。Backend 解释规则并返回预算快照；Agent 不计算 VIP 或用户跨任务余额。多窗口 allocation 是对**同一次消耗的多个约束**，不能相加为更多可用 Token。

签名建议用固定算法白名单的非对称 JWS（例如 EdDSA）；Backend 持私钥、Agent 取公钥并支持 kid 轮换。实现前确认现有依赖支持，本文不新增依赖。服务认证沿现有 Bearer 边界，逐步分离 Backend 签发/Agent Control/Worker 角色凭据；Worker 凭据不能调用授权签发或冒充 Catalog 管理员。签名验证不是替代在线撤销检查；不接受客户端自签授权。

Allocation 为规则约束和预留引用，字段必须分别表达，不能把 metric、unit、purpose 混作一个字符串：

| 字段 | 类型 / 约束 | 语义 |
| --- | --- | --- |
| allocation_id | 非空 ID，grant 根内唯一且跨 revision 可追溯 | Backend 预留分配项身份；同项重复引用不创造余额 |
| rule_id | 非空规则修订引用 | 指向 Backend 不可变规则定义；不是能力 ID |
| metric | tokens / attempted_units / successful_units | 该规则约束的统计量；不决定产品是否收费 |
| unit | token / call / activation | tokens 只能配 token；次数规则明确 call 或 activation，禁止不同单位相加 |
| scope | owner_window / capability_window | 用户跨能力窗口或指定能力窗口的约束范围 |
| capability_id | ID 或 null | capability_window 必填；owner_window 必须 null，表示该窗口覆盖的所有已授权能力，不表示任意能力获权 |
| purpose | main / summary / tool / skill_activation / all | 规则覆盖用途；all 仍受 capabilities 权限交集限制 |
| reserved_units | 非负整数 | 此 revision 签发时分配的预留快照；不是实时 remaining，也不是每个 Run 可重新领取的份额 |
| window_ref | 非空对象 | window_id、rule_revision、window_type、accounting_basis；固定/自然窗口带 start/end（半开区间）和 timezone/anchor；滚动窗口带 duration_seconds 及账本引用，不伪造固定窗口 |

剩余可用量只由 Backend 账本查询/Permit 结果提供。多项适用规则分别校验同一消耗，不对 allocation 的数值求和。时间戳统一 UTC；业务窗口时区另存。

**不可变修订与签名约束**：`(issuer, audience, grant_id, revision)` 的 payload 原字节、摘要、task_id、binding_receipt_id 和签名发布后均不可修改；若需换签名凭据则追加新 Revision，不覆盖旧凭据。初始 Revision 的 task_id=null/binding_receipt_id=null 永久不变。根绑定是另一条事实，存于 Backend 根记录的 bound_task_id/binding_receipt_id，初始为 null；绑定完成只 CAS 根记录并签发独立回执，绝不回填或重签原 Revision。根已绑定后签发的新 Revision 必须携带 `task_id=bound_task_id` 和原 binding_receipt_id；无需仅为绑定追加 Revision，初始 null Revision 可结合有效绑定回执参与执行门禁。

Backend 签发以 expected_revision 对 current_revision CAS，并同时检查生成 payload 所依据的 expected_binding_revision 与根权限状态；根绑定以 expected_binding_revision=0 对未绑定根 CAS 为 1，同时检查 expected_revision。两者在同一根锁下串行，payload 若在锁外预先生成/签名，CAS 前根绑定状态变化即丢弃未发布候选并重建。若续签先发生，bind 必须针对实际 current_revision 重取申请；若绑定先发生，续签必须读取已固化绑定再构造新 payload，不得发布新的 null Revision。owner/submission/reservation/request_digest 不能通过任一操作改绑。相同 Task 的绑定重放返回原回执（仍须核对不可变身份），不同 Task 冲突；不以旧 expected_revision 制造第二次绑定。

Agent 本地 pending→bound CAS 要匹配 grant 根、Task、receipt 摘要和 binding_revision；授权 current_revision 只 CAS 上升，同 Revision 异摘要冲突，旧版本仅留审计。跳号先获取并验证权威当前完整 Revision；晚到旧回执只能补根绑定事实，不能降低 current_revision、清除撤销或复活权限。bind/续签与撤销均检查根当前权限状态；撤销后的迟到响应不改变该状态。

签发采用固定规范化配置 `canonical_json_v1`：UTF-8、无 BOM/无无意义空白、对象键按 Unicode 码点递归排序、数组保持顺序、禁止重复键/NaN/Infinity；计量数值为整数，超出安全整数范围拒绝；时间固定 UTC `YYYY-MM-DDTHH:mm:ss.SSSZ`；可空必选字段显式 null。有限小数（如时长）采用约定十进制字符串，禁止不同浮点序列化产生不同摘要。字符串不做隐式 Unicode 归一化，签发前业务规范化结果纳入 request_digest。Grant/Receipt 的 signature 外壳不在 payload 中；compact JWS 的 protected header 必含 typ、alg、kid，payload 必须是规范化声明的原始字节。验证先验签原字节，再检查严格 Schema 和规范化字节一致性；禁止解析后丢弃未知字段再验签。request_digest 使用同一规范化配置和 SHA-256，并携带 digest_profile。

算法只接受部署预设的非对称白名单，候选 EdDSA，具体算法/依赖由 T0 批准；拒绝 none、对称替代、未知 alg/kid、非预期 typ、未经允许的扩展头和消息自带取钥地址。signature 外壳的 alg/kid 必须与 JWS protected header 一致，不允许用未签名外壳覆盖验签选择。公钥按预配 issuer/audience/kid 获取，未知 kid 受限刷新失败即拒绝。轮换先发布新公钥、后启用签名；旧公钥保留到已签凭据的最长有效期加允许时钟偏差结束，补报验历史证据需保留验证档案；泄漏密钥可提前吊销并阻止新增启动，不删除历史事实。生产密钥托管、轮换周期和时钟偏差数值另批，规范化与验签正反测试向量须在共享 Schema 发布前完成。

### 3.3 提交与绑定：无跨库事务

1. Backend 本地事务创建 Submission、锁住涉及的所有窗口规则、检查 `used + held + new ≤ limit`，建立 reservation 和 grant 修订。多规则固定锁顺序，事务重试；额度不足不向 Agent 提交。
2. 通过 Gateway 提交业务请求＋submission_id＋签名 grant，Agent 验证签名、受众、owner、摘要、有效期和能力映射。Agent 单事务建立唯一 submission/grant-root→Task 绑定、首 Run 和派发项。初始授权绑定处于 pending，不允许 claim 执行。
3. Backend 收到 Task 后由 Control 调 §7 的 v2 bind 接口确认根绑定；若提交响应丢失，按 owner/submission 查询或重放同一请求。Backend 对同 grant 根只能接受同一个 task_id；本轮固定使用 Control→Backend bind，不另设语义未定义的 Backend 回调分支。
4. Agent 收到 Backend binding 回执后本地激活授权。回执丢失可幂等重取；只在本地绑定及远端预留均确认后允许 claim。此握手是 Saga，不把 HTTP 往返放入数据库长事务。
5. Backend 崩溃后的恢复作业从 Submission 状态继续提交/确认。Agent 已有 pending Task 而 Backend 撤销预留时，该 Task 不能执行，转取消/授权失败。Agent 本地 submission 唯一约束阻止同环境重复任务，audience 阻止把同 grant 在其他环境再花一次。

单独持有首次 `task_id=null` Grant 仅允许创建并查回 pending Task，绝非可绑定任意 Task 的通配符，也不独立授予执行权限；取得并验证根绑定回执后，可在保持原 payload 为 null 的前提下按当前根授权状态执行。pending 是新增 binding_status，不冒充当前已有 TaskStatus 枚举；派发项即便已存在，pending 时 claim、start 均须拒绝。Backend bind 仅接受认证 Control 声明并核对自身 Submission 的 owner、digest、audience、grant/reservation；同一 grant 根绑定同一 Task 返回既有回执（换重试键不重复分配），不同 Task 返回 409，不允许解绑再利用。

**GrantBindingReceipt 独立协议**（全部必填）：`schema_version=1, receipt_id, issuer, audience, grant_id, grant_revision, grant_payload_digest, reservation_id, owner_id, submission_id, bound_task_id, request_digest, bound_at, binding_revision, signature`。使用 bound_task_id 明确它描述根绑定，而不是对 Grant.task_id 的补丁；grant_revision 专指本次首次绑定事务核验的 Revision。receipt_id 标识不可变根绑定事实，binding_revision 首版固定为 1，不随 Run 或续签递增。

grant_payload_digest 准确指向 **grant_revision 对应的已签发 Grant payload 的规范化原字节 SHA-256**，不含 signature 外壳/JWS protected header，也不含后来绑定回执或后续 Revision；它不是整个 compact JWS 的摘要，更不是“补入 Task 后重算”的摘要。绑定时核验的 Grant 通常 task_id=null，回执正是独立补足其根绑定。Backend 同事务固化根绑定及回执声明后签发并持久保存原件再返回；签名失败可按已持久声明恢复，不能另绑。签名配置与 Grant 相同但固定 typ 分别为 `shenzhi-budget-grant` / `shenzhi-grant-binding-receipt`，网络返回成功不代替绑定事务。

Agent 分别验 Grant 与 Receipt 的签名原字节、规范化、typ/alg/kid、issuer/audience；比对根/owner/submission/reservation/request_digest、Receipt.bound_task_id 与本地 Task，以及 Receipt.grant_payload_digest 与所指历史 Revision 的 payload。后续 Revision 的 task_id 和 binding_receipt_id 必须与原回执一致；其 payload 摘要当然可不同，不能要求旧回执摘要等于最新 Revision 摘要。原始 null Revision＋原回执也必须通过最新授权状态校验才可执行。缺少被引用历史 Revision 时取回验签，失败保持 pending/拒绝，不能跳过摘要核验。回执只证明历史绑定，不独立证明根仍 active；丢失后取原件，不重签成新绑定，不因迟到回执复活权限。

### 3.4 三个阶段的门禁

| 阶段 | 必须校验 |
| --- | --- |
| submit | 协议/签名/时间/受众/owner/digest；submission 和 grant 根唯一；模型别名解析为精确版本；强制技能及必需依赖在授权内。相同请求重放返回原 Task，不再预留 |
| claim | 已确认绑定、当前授权修订可用、Task 未取消、未到执行截止；当前环境存在对应版本；领取产生 execution_id，关联 `(run_id, worker_id, lease_token)`。远端检查失败不能占住长事务锁；使用检查回执后本地 CAS 激活，调用前再检查 |
| 每次实际调用 | 当前租约仍有效、Task 可执行、最新已知撤销策略、grant 未过期、精确能力/用途允许、依赖及本地配置可用、BudgetLimits 未耗尽；原子获取唯一 call permit，再在真正发送/工具执行前完成本地启动登记 |

调用许可和 start 协议详见 3.7。Backend 只信任认证 Control 对执行身份的声明；原始 lease_token 只在 Worker↔Control 和 Agent 库内校验，不进入 Backend Permit、UsageDelta、外部账本或日志导出。跨服务仅传 opaque execution_id、control_attestation_id；它们是追溯引用，不是可在 Backend 验证的租约凭据。

持久 start 与网络发送不能形成原子事务。旧 Worker 在 start 后停顿、失租再发送的竞态无法仅靠 fencing 消除：视为已启动的潜在在途调用，额度继续保留，新 Worker 不可复用该份许可；旧 Worker 应在本地截止与 stop 检查后放弃发送。若要求“失租瞬间连已批准的上游请求也绝不发出”，必须引入控制端代发/支持 fencing 的上游代理，这是独立范围和成本，首版不作此保证。

### 3.5 重试、过期与状态

Backend grant 权限状态：`issued → bound → active → expired/revoked/closed`；预留状态单独为 `held → draining → settled` 或 `reconciliation_required`。权限关闭不能自动把预留当未用释放。

- 自动新 Run 沿用 grant 根和 submission，必须重新校验剩余额度，不复制原始 reserved_units 为新余额。授权类拒绝应为不可自动重试错误，不继续套用当前“所有失败最多三次”规则。
- 同 Run 接管增加 lease_token 并生成新 execution_id；已 start 调用即使没有回报也占额度。新 Worker 的真实调用使用新 call_id、新许可；旧 Worker 不能领取新许可或启动旧未用许可。
- 续期追加同 grant 根的新不可变 Revision，并 CAS 提升根的 current_revision，绝不修改旧 Revision；根绑定后新 Revision 必须引用既有 bound_task_id/receipt。续期若跨窗口需重新检查窗口额度；不能仅改旧 payload 的 expires_at。未经批准不自动加额。
- 过期/取消/撤销停止新增调用及摘要/重试，在途调用尽力取消并继续接收用量。任务失败照样结算实际调用；无调用的拒绝不能凭空扣真实 Token。
- Task 完成、取消、失败或等待输入后进入 draining；确认所有 execution 已失效、无可启动许可、用量已投递且未知项有处理结果后才释放确定未用余额。Lease 到期、任务终态或 HTTP 超时单独发生均不足以全额退款。
- grant 到期不影响旧调用事实补报。匿名 owner 会话认领不能改写历史 grant/ledger 的归属；新提交按新身份授权，历史展示关联由 Backend 处理。

### 3.6 并发和跨窗口约束

Backend reservation 及 permit 在同一 owner 的所有适用规则下原子更新，调用许可将任务 held 转为 call held，不重复增加同一窗口占用；实测入账时再以相同事务把 held 转 used，释放差额。Agent 的 Run 内计数不能代替这个事务。

任务预留只在其声明窗口内有效。调用跨固定窗口/自然日时，Backend 先在新窗口原子预留，再撤去旧窗口中确定未启动的对应任务持有量；失败则拒绝该调用，不能先释放后尝试。滚动窗口用发生时间的账本事实＋所有未决在途持有量计算，旧 reservation 即使建立于五小时前也不能因时间到而凭空返还。

建议 Token 按可信 start 时间归属窗口（长调用跨日仍在开始窗口）；迟报按该时间修正，不按接收时刻归属。Backend 保存自己发放许可时刻，检查 Agent start 与许可时限的偏差，异常隔离。此时间口径需负责人确认，且写入 policy_revision。

Permit 必须携带其适用的精确 window_ref；本轮固定/自然窗口强制 `start_before ≤ min(所有适用 allocations 的 window_ref.end)`，窗口为半开区间，本地启动和发送前检查必须满足 `now < start_before`。不以“已取得新窗口持有量”为理由延长旧 Permit：越界须封闭未启动 intent、确认可 void 后另申请正确窗口的新 Permit/call_id；不明旧调用保留 held。滚动窗口按批准的 accounting_basis 保留在途持有量。时钟偏差须采用保守提前截止，不允许把截止向后加宽；具体偏差数值仍待批准。

严格防实际超额还依赖每次请求输入 Token 的可靠上界和输出硬上界。能可靠计算时预留输入上界＋输出限额并收紧 max_tokens；无法证明上界的 Provider 只能采用经批准保守预留，不能声称数学意义上的硬额度保证。实际 usage 超过预留仍完整入账，记 overage 并阻断后续调用，不裁剪或丢弃事实；是否向用户追扣是待决策规则。

### 3.7 CallIntent / CallPermit 状态机及撤销线性化

两服务不共享状态机表：Agent 的 CallIntent 表示启动事实和本地执行权，Backend 的 Permit 表示账本持有量与启动授权承诺。所有网络步骤在本地短事务之外，通过原 ID 查询和恢复，无跨库原子提交。

| 权威 | 状态与迁移 | 不变量 / 恢复动作 |
| --- | --- | --- |
| Agent Control | intent → requesting → authorized → starting → started → completed | requesting 在发申请前落盘；starting 在发 Backend start 请求前落盘。started 及 Usage Outbox 同本地事务持久化后才可返回一次发送许可 |
| Agent Control | intent/requesting/authorized/starting → void | 仅在锁定并封闭该 intent、确认未发布本地启动回执且之后不可能发布时；远端不明先查询。void 后不能恢复为 started |
| Agent Control | starting/started → unknown → completed | starting 恢复先查询 Backend 和本地启动事实；无法证明未启动则 unknown。unknown 不授予再次发送权；迟到可信观察可补齐 |
| Backend | authorized → start_committed → completed / unknown | authorized 仅持有额度，不足以发送；start_committed 表示一次启动门禁已提交，尚不证明 HTTP 已发送；用量修正仍以追加观察处理 |
| Backend | authorized → void / expired；start_committed → void（需未启动证明） | TTL 到期阻止新的 start；expired 仍持有待核对额度，不能仅凭超时退款。start_committed 的 void 要有 Control 持久封闭证据；已有 started 或不明则 unknown |
| Backend | authorized / start_committed → unknown | 远端状态不明或超时恢复无法证明未启动，持有量进入对账；unknown 不是余额释放原因 |

1. Agent 对当前 Run 加锁验证有效租约和绑定后建立 call_id、intent 与请求摘要。Control 向 Backend 申请 Permit；Backend 对 `(audience, call_id)` 唯一，以规范化申请摘要去重。同内容返回原 permit/status，不续 TTL、不重占额度；异内容 409。明确拒绝也保存该申请结果；改变请求或在重新授权后新尝试须新 call_id 并关联同 logical_call_id，不用同 ID 覆盖拒绝。
2. 申请响应后 Control 再验租约/任务状态，把 permit 关联到 intent。Worker start 时 Control 先锁 Run/intent，检查有效租约，将 intent CAS 为 starting，生成不可变 start_operation_id。随后 Control 向 Backend `POST /api/v2/agent/internal/call-permits/{permit_id}/start` 提交同操作键；Worker 不能直接调用该接口。
3. Backend start 与 grant 紧急撤销在同一 grant 根及适用策略锁下串行，先核验 current_revision、绑定、Permit 状态和时限，再 CAS 为 start_committed，返回不可变 `start_authorization_id, committed_at, start_before`。**撤销线性化时刻是 Backend 撤销事务提交**：该时刻之前未获得 start_committed 的 authorized Permit 全部失去启动资格（通过根撤销状态统一判断，无需逐项异步通知）；之后的 start 拒绝。撤销通知丢失不能绕过在线检查。
4. 若 start_committed 先于撤销提交，该次已承诺启动权只在签发的短 start_before 内有效，撤销不承诺追溯消除；`start_before ≤ min(permit.expires_at, grant.expires_at, 所有适用固定/自然窗口的 window_ref.end)`，没有固定/自然窗口时省略第三项。TTL 不可被重试延长，now=start_before 已拒绝。Control 收到后在本地 Run/intent 锁下再验租约、取消、本地已知撤销和截止，CAS 为 started，写 started 观察/Outbox，再返回启动回执；Worker 在真正发送前再次检查同一截止，不能把记录已 started 当成可跨截止发送。失败则按持久事实判断 void/unknown；响应丢失查询恢复，不重复外调。start_authorization_id 的有效时长必须在 A2 验收前批准，紧急撤销端到端 SLA 另批，不以“立即”代替此边界。
5. 本地 start 只创建一次启动事实；重复 start 返回 `already_started` 和原事实，`may_send=false`，不能给第二个发送机会。首次响应可携带 `may_send=true`；回执传输不明时先查状态，查询不能重新发启动权。Worker 仅对本进程首次收到且未使用的回执发送一次；进程崩溃/回执丢失可能造成调用未发却 held，保守 unknown，不能以重放恢复发送。新的真实重试必须用新 call_id、新 Permit。
6. Lease 接管与最后本地 started CAS 使用相同 Run 锁；接管后旧 Worker 不得申请或 start，已有 authorized/starting intent 封闭并恢复远端状态。只有可证明从未发布启动回执且状态已封闭才能 void；一旦发布回执即可能已产生副作用，超时、Worker 自报“没发”、心跳失效均不足以 void。已 started 的旧 Worker 只可补报既有事实；已承诺启动与网络发送间的竞态按前述限制处理，不声称 Fencing 保证外部 Exactly Once。
7. 普通禁用建议作用于新提交的 PermissionSnapshot，现存授权按快照继续；紧急撤销作用于指定 grant 根或精确能力范围的每次 Backend start 门禁，包含 summary、重试、forced Skill 和派生 Tool。已 start_committed / started 的调用按短截止和尽力取消处理，不承诺上游回滚。此处冻结技术作用域表达，采用哪种默认策略由 B2 负责人批准。

void 证明的最小声明为 `void_operation_id, permit_id, call_id, execution_id, control_attestation_id, sealed_intent_revision, sealed_at, start_operation_id（可空）, backend_start_authorization_id（可空）, local_started_record_absent=true, local_start_receipt_never_issued=true, reason_code`。Control 必须先在本地事务永久封闭 intent，并以持久状态保证不会再发布回执，再用服务身份提交证明；Backend 与自身 start 状态核对，重复同操作同内容幂等、异内容冲突。过期 Permit 也只能在此证明成立后 expired→void 并释放确定未用持有量；证明不完整、已有 started 或存在发送可能性则 unknown。证明格式是 A2 Schema 冻结审查项，不要求额外引入授权服务。

**最小 CallPermit 请求**：`schema_version=1, call_id, logical_call_id, request_digest, grant_id, grant_revision, reservation_id, binding_receipt_id, owner_id, submission_id, task_id, run_id, execution_id, control_attestation_id, capability_id, capability_version, invocation_mode, purpose, requested_allocations[]`；每项 allocation 为 `allocation_id, metric, unit, upper_bound_units`（非负整数，不能大于批准规则允许量）。身份和精确版本均必填；Model 需同时有输入上界和输出硬限的证据引用，无法证明时明确 risk_profile，不能自报为硬上界。

**最小 CallPermitResponse**：`schema_version, call_id, request_digest, decision=authorized/denied, reason_code, retryable, current_grant_revision, permit`。拒绝时 permit=null；获批时 permit 包含 `permit_id, status, grant_id/revision, owner_id, submission_id, task_id, run_id, execution_id, capability_id/version, invocation_mode, purpose, policy_revision, issued_at, expires_at, start_before, allocations[]`；分配项带 allocation_id、rule_id、metric、unit、window_ref、held_units。其关联必须与请求一致。服务认证保证来源，start 返回值另包含 start_operation_id、start_authorization_id、committed_at、start_before 和是否首次提交；同键重放返回原状态，不产生第二个启动授权。

## 4. UsageDelta Schema 与生命周期（建议）

### 4.1 调用级追加事实

UsageDelta 是一次真实调用的用量观察事件，不是 Run 最终汇总，也不是“每收到一条就把累计值再加一次”。区分 logical_call_id（一次逻辑请求）与 call_id（每次实际 HTTP 尝试/工具执行）。模型返回的 tool_call_id 仅是关联信息，不能当全局计量 ID。

| 字段 | 类型 / 约束 | 含义 |
| --- | --- | --- |
| schema_version / measurement_id | int / 全局唯一 ID | 首版 1；不可变投递事件 ID |
| call_id / logical_call_id | 全局唯一 ID | 真实调用与逻辑调用；每次重试产生新 call_id |
| observation_revision / supersedes_measurement_id | 正整数 / ID 或 null | 同调用后续补齐/更正版本；保留旧观察 |
| metering_context / metering_profile_id | authorized / observation_only；非空 ID | 由 Backend 持久 Task 模式记录决定，消息只复述；authorized 必须完整授权关联；不能通过选择 observation_only 绕过 A2 |
| submission_id_source | backend / agent_observation | 与持久模式严格对应，防止 A1 计量关联 ID 冒充正式 Submission |
| grant_id / grant_revision / reservation_id / permit_id | authorized 时非空；observation_only 时显式 null | 用量归属、当次授权与预留许可；不能为历史/A1 观察伪造 Grant |
| owner_id / submission_id / task_id / run_id | 非空 | 全链路关联；与持久绑定校验 |
| execution_id / control_attestation_id | 非空 opaque ID | Agent 已持久验证的执行世代和声明引用；失租后仍可归此世代。worker_id/原始 lease_token 仅留 Agent 内部观察封套，不进入此跨服务协议 |
| capability_id / capability_version | 非空精确版本 | 实际执行的能力，不记录模型别名为主键 |
| logical_attempt / transport_attempt | 正整数 | 逻辑层、传输层尝试序号，辅助诊断；不作为唯一键 |
| provider_id / provider_request_id | string 或 null | 上游有 ID 才填；缺失不伪造，不单独据此去重 |
| purpose | main/summary/tool/skill_activation | main、summary 是计量用途，不复用 ModelRegistry 的 chat/agent 用途枚举 |
| parent_call_id / activation_id | string 或 null | 技能派生工具、复合调用因果关联 |
| phase | started/completed/activation | started 为可能产生副作用的启动观察；completed 可 unknown；activation 是技能首次装载事实 |
| outcome | in_progress/succeeded/failed/timed_out/cancelled/unknown | 结果与 Token 测量是否完整相互独立 |
| prompt_tokens / completion_tokens | 非负整数或 null | 部分已知可保留；缺失必须 null |
| usage_status | measured/partial/unknown/estimated | measured 要求两项均有可信实测；estimated 明示估算 |
| usage_source / missing_reason | 枚举 / 可空字符串 | provider_usage、provider_reconciliation、local_estimate；stream_interrupted、no_usage 等 |
| attempted_units / successful_units | 非负整数或 null | 调用次数事实；started 通常尝试 1、成功未知；按策略结算其中之一 |
| started_at / ended_at / observed_at | UTC 时间，ended 可空 | 启动阶段进入、执行结束和采集时间；started_at 不冒称 HTTP 实际发送时刻，Backend 另填 received_at |
| task_usage_sequence | 正整数 | Control 为 Task 的每条观察分配连续序号；revision 补报也有新序号，用于完整性检查，不能替代幂等键 |
| invocation_mode / manifest_revision | 非空 mode / 修订引用或 null | 实际进入方式和能力清单来源；A1 未导出 manifest 时显式 null，仍需 4.5 的 capability_identity/profile 与精确版本；身份对象可由启动事实查询取得，不按当前配置重建 |

估算不冒充 provider 实测；可增加 estimate_method/version 和 estimated 上界信息。已知 0 只用于上游明确返回 0 或可证明尚未实际执行的情况，不能由超时/失败推断。Tool/Skill 的 Token 字段通常不适用，以 null＋missing_reason=not_applicable 表达，不构成模型 unknown 风险项；模型真实费用只由对应 model 调用记账，不重复加到父技能 Token。

**统计与可信度**：started 表示进入可能产生外部副作用的启动阶段，不保证请求已发送或上游已收到。attempted_units 是该 call 进入此阶段的累计次数，单 call 为 1，不随 revision 增加；因此它不是 Provider 收件次数。successful_units 是 Agent 实际执行边界可确认成功的次数，单 call 为 0/1；尚不明为 null，确定失败为 0，成功判据由 capability 版本声明（不能只用 HTTP 200）。activation 的单位是 activation，首次正文装载成功为 1；参考文件读取不再增加。同一 Task、精确 Skill 版本 activation_id 唯一，跨 Run/接管重放返回同一激活事实。重复激活不重计，但执行权限仍重检。

usage_status 与 outcome 正交：measured 是该 metric 所需维度均有可信实测（模型要求 prompt/completion 两项）；partial 是部分维度或部分执行区间有可信实测，其余未知；unknown 是适用维度没有可信实测；estimated 表示至少一项用于投影的数值来自明确标注的估算，必须带 estimate_method、estimate_version 及逐字段来源。估计不能把已知实测覆盖掉；必要时携带 field_sources。失败可 measured，成功可 unknown。Tool/activation 的实际次数本地可测为 measured，Token null/not_applicable；不把“不适用”当 Token=0。

可空字段仍必须出现；schema_version 首版为 1。授信身份、call/logical ID、精确能力版本、purpose、invocation_mode 和 started_at 是不可更改的关联；同一调用的 started/completed/修正 observation_revision 连续递增。measurement_id 是单条不可变观察身份。`supersedes_measurement_id` 在 revision=1 时 null，之后指向紧前观察，允许其尚未到达。Provider 无请求 ID 则 null；不把上游 ID 当唯一调用键。Skill activation 使用独立 call_id、activation_id 和 unit=activation，不用内置 read_skill 的 call_id 顶替。

### 4.2 采集与投递流程

1. Agent Control 持久登记调用 intent/permit/start。start 产生 started 观察并同事务写用量 Outbox。持久登记失败不允许付费外调；“允许丢日志”的观测钩子不能作为唯一采集点。
2. 每次实际 HTTP 发送边界（包括 `_stream_once` 内可选参数降级和 `stream` 外层重试）生成独立 call_id。逻辑调用可共享 logical_call_id；每个真实尝试都走许可、start、finally 终结观察。摘要复用同一计量 Adapter，purpose=summary。
3. Provider 把请求 ID、完整/部分 usage、异常和取消状态交给计量层。收到多个流 usage 帧时按供应商语义选该调用最新累计值，不能逐帧求和。失败且有实测仍记 measured；无实测则 unknown/partial。
4. Worker 将完成观察交 Agent Control 专用用量入口；Control 按持久 started 记录校验历史 execution，追加观察和 Outbox。它不复用普通事件入口的“必须当前租约”条件，否则会丢失旧 Worker 在途费用。失租 Worker 仅能补报已有持久 started 的调用，authorized 另需曾获 Permit；A1 不伪造 Permit。补报不能创建新的调用事实/启动权限，不匹配记录隔离审计。
5. Agent 用量 Outbox 独立于派发 Outbox，至少一次向 Backend 批量投递；Backend Inbox 按 measurement_id 唯一入库，同事务更新账本/预留并返回逐条回执。接收成功后 Agent 标记 delivered；超时复用同一 ID 重发，冲突不静默覆盖。
6. Worker 崩溃没有完成观察时，Control 仍有 started/permit，标为 unknown 并进行对账；不会因没有 RunResult 而丢掉所有调用。重启扫描 intent/authorized/started 各状态，无法证明没发送的项保留持有量。

Backend 不采集模型流，不猜测运行行为；Agent 不决定套餐扣费/退款、不直接更新用户额度。

本节 Permit/账本动作仅适用 authorized；A1 observation_only 对应本地调用日志/观察和 Inbox 投影，不申请 Permit 或调整预留。Worker 补报携带本地 observation_submission_id 幂等键，Control 统一在调用锁下分配 observation_revision、measurement_id 和 task_usage_sequence 并持久返回；重试相同补报不得再生成新 revision。恢复作业与旧 Worker 并发追加也由 Control 串行分配，避免两个生产者占用同一观察版本。原始租约在本地封套验证后不随 UsageDelta 发往 Backend。

SSE Adapter 必须声明 `usage_frame_semantics=cumulative/incremental/unsupported`：累计帧取最终可信完整累计快照，不把重复帧累加；最终缺某字段时保留有证据的已知部分并标 partial，不凭空补 0。若 Provider 明确为增量帧，Adapter 须有可验证帧身份去重后合成绝对观察；无可靠帧语义/重复识别证据时标 partial/unknown。累计值回退或矛盾进入对账，不简单取最大值假装准确。多帧处理发生在单 call 内，不创建多次调用。

隐式 SDK/transport 自动重试必须关闭，或把可靠计量/Permit/start 边界下沉到每次真实发送；无法拦截则该适配器不能宣称满足 A1，也不能用于 A2 硬门禁。Tool 的计量边界是一次实际 `execute_prepared`，内部 HTTP 次数不冒充多次 Tool 执行；其内部若产生受管模型调用则另记 model 子调用并关联 parent_call_id。参数校验失败/prepare 拦截只记诊断拒绝，不产生真实执行次数或 successful_units。

### 4.3 幂等、修正和结算

- measurement_id 相同且规范化内容相同返回 duplicate；同 ID 不同内容返回冲突并留审计。`(call_id, observation_revision)` 同样唯一；核心归属字段和 started_at 不可通过更正搬家。
- 观察上报的是该调用当时的**绝对测量值**。Backend 以每个 call_id 已采纳的版本作投影，只把“新采纳值－旧采纳值”作为账本调整，避免 started、completed 和迟补三次重复扣款。调整为追加记录，可为负数；原始 Token 字段永远非负。
- started 未知不计零，保留 call held。completed measured 时将 held 转 used 并释放确定差额；partial/unknown 保留未决部分。旧版本迟到只存事实，不回滚新投影；有版本断档/修订冲突时请求补齐，不能错误求和。
- RunReport/UsageReport 可作为展示汇总与一致性检查，不能再次扣费。Task 汇总覆盖所有 Run、所有 execution、所有真实尝试和 summary。展示至少提供 known_tokens、unknown_call_count、estimated_tokens、settlement_status，禁止把不完整 total 显示为准确余额。
- 用量接受状态 `accepted/duplicate/quarantined/rejected` 与结算状态 `pending/settled/reconciliation_required/adjusted/not_applicable` 独立。超时、取消及错误分类与计费可信度正交。
- TaskClose 清单包含 submission/grant、全部 Run/execution、call_count、最后用量序号/高水位和 unknown_count。先等用量 Outbox 获回执，再申请关闭；Backend 校验 started 清单/许可集合，终态通知本身不能释放全部余额。缺少清单或序号有洞继续 draining。序号仅供完整性检查，不代替 measurement_id 幂等。
- 用户窗口额度与对上游成本分别保留：无论业务决定失败调用退还与否，真实 Provider 消耗不得删去。迟来的高额用量可触发历史窗口更正和风险标记；保留对账能力，不无限禁止接收迟报。

乱序处理采用绝对观察而非逐条增量：Inbox 先持久接收合规事实；归属可由既有 started/Permit 校验时可采纳最高可信 revision 为当前投影，后到旧版本只补链，不能再扣一次。revision 或 task_usage_sequence 有洞时返回 missing_revisions/missing_sequences 并请求重传，完整性状态保持 pending，禁止关闭/释放未决持有量。缺少可验证启动关联的高版本先 quarantined，不授权其执行；补证后用独立重处理动作解除隔离，不修改已入库原始观察。若 supersedes 链与相邻版本冲突则隔离并告警，绝不按到达顺序覆盖；缺口超期处理是 A3 业务决策。

**UsageBatchAck 最小协议**：请求含 `schema_version=1, batch_id, producer_id, items[]`，batch_id 只追踪传输，同一事件可跨批重投。响应含 `schema_version=1, batch_id, results[]`；每个输入项恰有一项结果：`measurement_id, call_id, observation_revision, disposition=accepted/duplicate/quarantined/rejected, durable, applied_revision, settlement_status, reason_code, retryable, retry_after_ms, missing_revisions[], missing_sequences[]`。applied_revision 在未投影时 null；settlement_status 可为 not_applicable（A1）。整批无法解析时返回明确错误，不伪造逐条成功。

accepted/duplicate 且 durable=true 才确认该观察可靠落库，可标 Outbox delivered；未返回项/超时按原 ID 重试。quarantined 且 durable=true 可转独立待处理队列并确认投递，但不表示已入账，不能静默当完成；冲突记录和补证责任保留。rejected/durable=false 不确认，retryable=false 移入死信告警等待修正，不无限重发；新内容必须用新 measurement_id/revision，禁止覆盖旧 ID。Inbox 写事实和本地投影/账本调整同事务（或持久待投影标记）完成后才回 durable；绝不能先回成功再异步尝试保存。

### 4.4 必须覆盖的调用场景

| 场景 | 记录和结算行为 |
| --- | --- |
| 主模型正常流 | 每真实尝试一 call_id；完成观察含实测，两项齐全才 measured |
| 摘要成功/失败/跳过压缩 | 实际发送仍记 purpose=summary；摘要返回 None 不抹掉费用；空上下文未发送不产生真实调用 |
| HTTP 超时、流中断、取消 | started 留证，finally 写 unknown/partial；不能以无文本推断未收费 |
| 400 参数降级或 429/5xx 重试 | 每次发送单独许可、call_id 和结果；拒绝是否收费依据上游证据，不能默认 0；逻辑 ID 串联 |
| 新 Run 重试 | 新 run_id；原 Run 消耗保留，继续花同 grant 剩余额度 |
| Lease 接管 | 同 run_id、新 execution/token；原调用 held 不复用，新请求独立记；旧 Worker 只补报既有 started 调用 |
| 重复投递或完成先于 started 到达 | Inbox 幂等；按调用版本归并，不按到达顺序加总；可凭 permit/start 查询恢复事实 |
| 完全缺失 usage/Worker 崩溃 | persisted started 形成未知项和告警；按批准的暂扣/估算/人工策略收敛，不用零补齐 |
| Tool 实际执行 / 参数失败 | execute_prepared 为真实执行边界；prepare 参数失败不增加实际执行次数，诊断另存 |
| Skill 首次激活 | 独立 activation_id/call_id，同 Task 精确版本首次装载事实；forced 与 read_skill 都覆盖，参考读取不重计 |
| 用量修正 | 追加新 measurement_id / observation_revision，绝对观察差额调整；缺口与乱序不重复投影 |

### 4.5 A1 独立完成边界

A1 不实现 VIP、套餐、Grant 签名、预留或扣费。A1 start 是本地计量事实，不冒称 Backend CallPermit；验收是可靠接收/幂等投影，settlement_status=not_applicable。其最小依赖为 UsageDelta/Ack、持久 Task 模式关联、可查询调用事实及能力版本身份，不依赖完整 B1 Catalog。

**模式的唯一决定方是 Backend**。在现有 Task 关联/提交元数据边界持久保存 `metering_profile_id, owner_id, agent_audience, metering_context, provenance, admission_revision, request_digest, task_id（确认前 null）, backend_submission_id（A1 为 null）, agent_observation_submission_id（确认前 null）, enrollment_at`；这只是模式及关联记录，不是第二套 Grant/余额服务。Backend 按已批准的服务端准入/迁移规则创建 profile，客户端、Worker、Agent 及消息中的模式字段均不能自行改写它。A2 正式 Submission 创建时原子确定 authorized，并在远程提交前落盘；不能在签名失败后另建 observation_only profile 来承接同一次正式提交。

新任务统一通过 §7 的 v2 提交携带 Backend 决定的 profile/mode，authorized 另需 Grant；A1 observation_only 不需 Grant。Agent 只接受有角色权限的 Backend Gateway 提交，保存不可变镜像，Task 创建后由 Control 调 Backend 的 task-metering-bindings 确认精确 Task 关联。Backend 以 profile 唯一绑定 Task，authorized 还核对正式 Submission 和 Grant 根关联；相同绑定幂等、异 Task/owner/digest 冲突。Agent 得到确认前不启动该新 v2 Task 的计量执行，authorized 还必须完成独立 GrantBindingReceipt，模式确认不替代授权。Backend 用量入口先查自己的 `(agent_audience, task_id)` 记录并校验 profile/mode/ID 来源，而不是看 grant_id 是否为空来猜模式；未知模式/记录缺失/不匹配先隔离，不投影、不结算，也不由这条 UsageDelta 自动创建 observation_only 记录。

模式绑定最小请求为 `schema_version=1, operation_id, metering_profile_id, agent_audience, task_id, owner_id, request_digest, submission_id_source, submission_id`；响应为 `schema_version=1, metering_profile_id, task_id, metering_context, submission_id_source, submission_id, bound_at, admission_revision`。模式取 Backend 预建记录，不能通过请求覆盖；profile 与 `(agent_audience, task_id)` 各自唯一，绑定事务只允许 null→同一 Task，重复同内容返回原件、异内容 409。Agent 仅在响应与本地镜像完全匹配后激活；声明未知/超时保持待确认。字段 profile/mode 在说明中只是简写，正式 Wire 字段统一为 metering_profile_id/metering_context。

| 任务来源 | Backend 判定依据 | 迁移 / 执行 / 接收行为 |
| --- | --- | --- |
| A1 前未接入计量的旧 v1 Task | 原有 Gateway 关联或经核验的可信迁移清单；legacy_unmetered 是历史分类，不是可执行授权模式 | 不伪造历史 started/usage。若继续旧执行则按原 v1 契约隔离排空；只有 Backend 明确登记 observation_only profile、Control 绑定确认并在未来调用前启用计量后，才接收该 enrollment_at 后的事实 |
| A1 observation_only 新任务/已登记旧任务 | Backend 明确准入规则及持久 profile，provenance=a1_admission/legacy_enrollment | 只能计量不扣费；只采接入后的事实。新任务走 v2；旧任务登记使用独立新协议，不给旧 Wire 加字段 |
| A2 正式任务（含显式免费授权） | 持久正式 Submission，provenance=authorized_submission，mode=authorized | Grant/Receipt/Permit 关联必需；模式在整个 Task/所有 Run/execution 生命周期不变，失败或重试也不能切 observation_only |
| 混合部署、未知/冲突模式 | Backend 准入修订及已落盘 Task 记录，而非当前进程开关 | authorized 队列与旧 Worker 隔离；未知配置阻止新启动，未知用量隔离。回滚保留模式记录和接收查询能力，不能修改历史模式 |

协议错误、配置错误、未知版本、解析失败、验签失败、Backend 超时均不能触发降级。全局开关只改变以后准入，不能重分类已有 Task；A2 切换时停止新 observation_only 准入，已登记 A1 任务可在隔离队列按原模式排空并继续补报。若产品需重新授权旧需求，创建新的正式 Submission/Task 并保留迁移关联，不把旧观察搬入新账本。具体迁移名单和切换时间由负责人批准，不在本文预设。

**A1 ID 边界**：UsageDelta 仍有非空 submission_id，但 observation_only 时它是 Agent 生成并持久化的 `obs:<opaque-id>`（source=agent_observation），唯一绑定一个 Task，并经 Backend 模式记录确认。它只用于计量关联，不对应 Backend 正式 Submission、不代表权益或预留，也不能用它申请 Permit。authorized 时 source=backend，submission_id 必须等于正式 Submission 主键，禁止 obs: 命名空间；Backend 两种来源分列存储/索引，不因字符串碰巧相同合并。A1 模式记录可以存在 Backend，但 backend_submission_id 必须 null；A2 不回填/改名 A1 的 ID、mode 或事实。

**启动事实验证（A1 必需）**：增加 Backend→Agent Control 只读 `GET /internal/v2/tasks/{task_id}/call-facts/{call_id}`（schema_version=1），从 Control 持久调用日志读取，不能从 Worker 内存或 Provider 钩子临时拼装。响应最少含 `schema_version, agent_audience, task_id, run_id, execution_id, call_id, logical_call_id, metering_profile_id, metering_context, submission_id_source, submission_id, owner_id, control_attestation_id, fact_kind=started/activation, started_at, capability_id, capability_version, capability_identity_profile, capability_identity, invocation_mode, purpose, parent_call_id, activation_id, grant_id, grant_revision, reservation_id, permit_id, start_record_id, start_record_digest, recorded_at`；parent/activation 可空，四项授权关联在 observation_only 时 null、authorized 时必填。immutable 启动/激活部分与后续完成观察分开；start_record_digest 是上述启动响应字段除自身外的规范化原字节 SHA-256，recorded_at 是持久记录时间，不是每次查询的当前时间。记录一经确认不因失租被抹去。无记录返回 404，不推断执行次数=0。

Backend Inbox 可先 durable 接收并保留 pending_verification，再按本地模式关联选择受信任 Agent 环境查询；首次接受该 call 的投影前必须比对上述全部身份、精确版本、用途和启动时间，重算启动记录及能力身份摘要，authorized 另与自身 Permit/根绑定记录核对，并缓存启动快照/摘要。后续 revision 只可引用相同启动事实；completed 先到时也先查事实。查询失败、404、摘要或关联冲突时保持隔离/待核验，不自动改模式或投影；事实补齐后按原 measurement_id 重处理。Ack 的 durable 只保证保存，settlement_status=pending / not_applicable 与本地 verification_status=pending/verified/quarantined 分别记录，不将接收成功说成验证成功。

服务认证至少区分 Backend 事实读取、Agent Control 用量生产及 Worker 本地角色；沿现有 Bearer 机制配置独立角色凭据/ACL，限制 audience 和可读 Task 范围。Worker/浏览器不得调 Backend Inbox、绑定模式或冒充 Control；仅有通用凭据且不能隔离角色的部署不满足 A1 发布条件。Backend 按预配置环境路由查询，禁止采用事件提供的任意 URL；双方记录 principal、request_id、profile/Task/call、源记录摘要、查询时间、验证结果和隔离原因，不记录原始 lease_token 或凭据。可信声明来自认证 Control＋其持久事实，不证明 HTTP 确已送达、上游实耗或 Control 未被攻陷；上游费用证据另属 A3。无需为 A1 实现 JWS 或跨库查询。

**A1 精确能力身份（B1 复用）**：固定 `capability_identity_profile=capability_identity_v1`，摘要用 canonical_json_v1/SHA-256；每个调用持久化 capability_identity 及其摘要版本，查询返回同一记录，不重新按当前配置计算。字段最小定义如下：

| 类型 | capability_identity 的必需内容 | capability_version 的定义 |
| --- | --- | --- |
| Tool | kind、capability_id、implementation_build_digest（受控实现产物及行为依赖摘要）、parameter_schema_digest（原生 ToolSpec.parameters 规范化摘要）、dependency_digests[] | `sha256:<身份对象规范化摘要>`；实现或参数 Schema 改变均变版本 |
| Skill | kind、capability_id、resource_content_digest（按受控相对路径排序的打包文件内容清单摘要，覆盖 SKILL.md/references/scripts/tools）、dependency_digests[] | 同一身份对象摘要；不使用 mtime、文件大小或 SkillStore 缓存签名 |
| Model | kind、capability_id、provider_id、registry_model_id、upstream_model、configuration_release_digest（协议/能力/非敏感参数及不透明路由修订引用）、dependency_digests[] | 同一身份对象摘要；先解析 alias/default，再固化身份；配置发布版不等于云端权重版 |

没有依赖时 dependency_digests=[]。清单禁止绝对路径、密钥、真实地址；路由变化用非敏感修订引用表征，凭据轮换不改行为版本。不得将整个运行时对象或带密钥配置直接哈希后导出，构建清单缺失则版本身份不合格，不能退化为名称/mtime。A1 只需生成这些最小身份记录，manifest_revision 可 null；B1 Manifest 原样引用同 capability_id、capability_version 和 capability_identity，对同一产物不得重算成另一套版本。发现旧声明错误时追加新版本及审计，不覆盖历史调用身份；ToolRegistry/SkillStore/ModelRegistry 原生机制保持不变。

## 5. Capability Descriptor（建议）

### 5.1 四类状态明确分离

1. **代码存在**：Agent 构建产物/技能资源/声明模型模板中存在对应定义。不意味着在当前环境注册。
2. **系统注册**：Agent 当前部署通过原生 Registry/Store 成功解析，并有 Backend Catalog 可识别的精确版本；管理员建一条目录记录不使代码出现。
3. **管理员允许**：Backend 全局策略与 owner 权益允许；同运行快照或即时策略求交。不能用 Registry.enabled/latent 混代。
4. **环境健康可用**：具体 deployment 上配置完整、依赖满足、最近健康观察有效；configured 不等于 healthy。未知没有探测不能写 healthy。

`effective_allowed(context, invocation_mode) = registered_in_target ∧ native_enabled ∧ admin_enabled ∧ configured ∧ mode_supported ∧ grant_permission ∧ dependencies_satisfied ∧ health_policy_allows`。这是面向 owner/Task/部署/精确版本/调用方式的计算结果，缺权限快照时为 unknown，不能在 B1 的公共清单中默认 true。健康结果是有时间范围的观测，真正调用仍可能失败；unknown/degraded 如何放行由 B3 策略批准，首版只报告本地配置状态，不能声称已探活或默认允许健康未知。

discoverability 单独表示向模型披露的方式/当前状态，不参与授权替代判断。隐藏可调用能力仍必须过 effective_allowed；可见能力也可能无权执行。Catalog 管理员的 enabled 改名为 admin_enabled，避免与 ToolRegistry.enabled 的原生披露含义冲突。

### 5.2 统一管理视图字段

| 字段 | 约束 / 来源 |
| --- | --- |
| schema_version | 1 |
| capability_id | 稳定命名空间 ID，如 `tool:paper_search`、`skill:deep-research`、`model:<provider>/<model>`；不可由展示名随意改动 |
| kind / name / version / description | tool/skill/model；原生名称；version 必须等于 4.5 capability_identity_v1 的不可变 capability_version；非敏感说明，不另起版本体系 |
| capability_identity_profile / capability_identity | 固定 capability_identity_v1 及 4.5 分类型身份对象；Manifest 原样复用 A1 的内容/Schema/配置发布摘要 |
| input_schema | JSON Schema object 或 null，并有 input_schema_status=declared/not_applicable/unknown；不虚构 Skill/Model 参数支持 |
| dependencies | `[{capability_id, version_constraint, required, relation}]`；relation=requires/provides，必需依赖须可解析，无环 |
| admin_enabled | Backend 管理策略允许开关；B1 尚无管理策略时为 null/unknown，不伪造 true |
| discoverability | `{mode: always/latent/hidden, model_visible: bool}`；当前运行态可覆写 model_visible，不代表授权 |
| invocation_modes | 非空枚举数组：model_selected / explicit_user / forced / internal；只列真实支持方式，不自动赋权 |
| effective_allowed / decision_reasons | true/false/null 和拒绝/未知原因；带决策上下文及修订引用，无上下文时 null |
| health_status | unknown/healthy/degraded/unavailable；附 checked_at、valid_until、reason_code |
| configuration_reference | 不透明非敏感配置引用或 null，如 `model-profile:research-default`；只在 Agent 本地解析，不含密钥、URL、任意文件路径或 import 路径 |
| implementation_ref / content_digest | 可信构建清单里的原生标识及摘要，不接受用户提供的可执行路径 |
| code_present / registration_status / native_enabled | 构建来源存在性；registered/unregistered/invalid；环境原生配置启用状态 |
| configured / configuration_status | bool 或 null；complete/incomplete/unknown/not_applicable，配置齐全与健康观察分离 |
| deployment_id / manifest_revision | 环境与构建清单版本；健康与注册状态按 deployment 记录 |
| policy_revision / effective_at / disable_scope | Backend 策略版本、生效时间、新任务或逐调用撤销语义 |

Descriptor 是合并读模型，各字段有单一写入权：Agent 发原生 manifest 和 health observation；Backend 写 Catalog 管理元数据/策略。Agent 上报不能把 admin_enabled 改成 true 覆盖管理员关闭；管理员不能写 healthy。各自消息使用独立 Wire schema，避免互相覆盖字段。

Descriptor 的 kind/name/version/description、capability_identity_profile/capability_identity、input_schema/status、dependencies、implementation_ref/content_digest、code_present/registration_status/native_enabled、configured/configuration_status、discoverability、invocation_modes、deployment_id/manifest_revision 必填；可空字段必须显式 null。Backend 合并的 admin_enabled、policy_revision、effective_allowed、health_status 默认分别为 null、null、null、unknown，附来源及时间；未知不是允许。禁用策略增加 disable_scope=new_submissions/emergency_starts、effective_at，作用域与 3.7 一致。Agent 原生 manifest 不接受 Backend 所有字段。

### 5.3 三种原生机制的映射

| 原生对象 | 管理描述映射 | 执行边界 |
| --- | --- | --- |
| ToolSpec / ToolRegistry | name→原生名称，parameters→input_schema，受控版本清单/实现摘要→version。每个可执行工具一个 ID | 保留 prepare/execute_prepared/dispatch；统一许可覆盖顺序与并行路径，在执行前再次检查，latent 工具也不能绕过 |
| Skill / SkillStore | name/description 来自技能元数据；SKILL.md＋references＋scripts/tools 等打包资源内容摘要作为首版版本，不能用 mtime 缓存签名；无结构化入口时 input_schema=null/not_applicable | 推荐把“本 Task 首次激活该技能版本”作为独立 activation 事实，forced_skills 注入前和 read_skill 装载前统一校验；参考文件重复读取不自动再计付费激活 |
| ModelSpec / ModelRegistry | 精确 spec.id 映射 model ID；版本由声明配置/协议能力摘要和发布标识确定，不承诺云端同名模型权重不可变；输入描述引用受支持的 ModelRequest 参数，不暴露 ProviderConfig | 先解析 alias/default，再对精确 ID/version 许可；摘要同样校验。Provider 路由/配置改变须新修订，不能静默把旧授权切到其他模型 |

Skill 提供 Tool 是 `provides` 关联，Skill 依赖 Tool/Model 是 `requires`；工具授权独立校验，获得 Skill 不隐式获得任意工具。forced Skill 在正文注入前登记 activation，避免只保护 read_skill；内置 read_skill 工具调用与技能激活是两个事实，不默认双重计费。系统核心工具可显式配置免费规则，不能依赖“不出现在目录就免门禁”。

首版 Catalog 从实际装配清单导出，不为了发现能力实例化带副作用的工具或额外执行 tools.py。第一方现有可信 tools.py 加载行为保持原样；不新增动态 Python 插件加载、远端代码安装或基于数据库 import 的机制，不重构三个执行 Registry。若执行能力版本在目标 Worker 缺失，拒绝调度/调用，不能回退到同名最新版。

Tool latent 映射 discoverability.mode=latent、初始 model_visible=false；native_enabled 表示环境原生执行许可（无独立开关时按已注册且可执行导出 true，并注明来源），不能简单映射 `name in ToolRegistry.enabled`。added_tool_names 只改变披露，不给权限；在披露变化、prepare 和执行门禁检查目标精确版本。

Skill disable_model_invocation=true 映射 discoverability.mode=hidden、model_visible=false，并从 invocation_modes 移除 model_selected；仅在实际支持时保留 forced/explicit_user/internal。该字段在当前源码只是展示控制，新增语义须在 B2 门禁落实，B1 不能宣称已阻止按名装载。forced_skills 必须匹配允许 forced 的精确 Skill 权限，在注入正文前校验并登记 activation；不因后端/系统主动选择而绕过授权，Skill 提供的 Tool 仍单独检查。

版本定义以 4.5 capability_identity_v1 为唯一摘要规则：Tool 显式区分 implementation_build_digest 与 parameter_schema_digest；Skill 用资源文件内容清单摘要；Model 用精确模型身份及非敏感配置发布摘要，均排除 mtime/缓存签名。Model version **不是云端底层模型权重版本**；上游同名权重变化无法由此保证不变。只轮换凭据不改模型语义版本，路由/协议行为变化必须新版本；B1 只能复用 A1 身份，不另选“发布号或内容摘要”作为不等价授权版本。

alias/default 在提交时解析并固化精确 capability_id/version，写 request_digest 和权限；调用再次检查同一版本，summary 独立解析授权。不能用裸别名放行再临时解析，也不能默认切到同名新版本。B1 仅导出真实能力/版本和只读 Catalog，不添加动态安装、插件加载或权限管理写接口。

Manifest 需要 deployment 维度分页/全量修订完成标记；只有完整快照才将旧条目标记 absent，部分失败不能删除整目录。滚动部署允许多版本并存，Grant 精确版本应路由到匹配 Worker；首版若无版本路由则限制单活动版本并等待旧任务排空。健康状态过期归 unknown，禁用保留版本历史及账本引用，不物理删除在用版本。

**CapabilityManifest 最小协议**：`schema_version=1, manifest_id, issuer, audience, deployment_id, build_revision, manifest_revision, previous_revision, generated_at, snapshot_digest, total_items, page_index, page_count, complete, items[]`。items 仅包含 Agent 所有的原生 Descriptor 字段；`(capability_id, version)` 在完整快照唯一。manifest_revision 为部署内单调整数、内容不可变；previous_revision 首次为 null。每页同 manifest_id/revision/digest，总量/页数一致；complete 表示生产方声明快照完整，接收方仍须收齐全部页并核验排序后全量摘要，才原子切换 active_revision。相同修订异内容冲突；旧修订不回滚，跳号允许拉完整快照；失败/未收齐页保持旧视图并标 stale，不标 absent。不同 deployment 不互相删除能力。部分能力解析失败时 complete=false 并列 diagnostics，不发布虚假的全量删除。Manifest 通过服务身份认证，不新增动态注册执行机制。

## 6. 职责矩阵与数据库归属（建议）

| 事项 | Backend | Agent | Shared Contracts |
| --- | --- | --- | --- |
| 用户、VIP/套餐、用户覆盖规则 | 唯一事实与管理入口 | 不读套餐，不自行推断 VIP | 不放产品规则 |
| 5 小时/每日额度与能力权限 | 解释政策、原子预留、签发/撤销、结算 | 验证 grant、执行门禁 | Grant/Permission/Window 引用 |
| Task/Run/Lease/Worker | 通过 Gateway 操作与投影 | 唯一执行事实；Control 校验 fencing | ID、状态、关联 |
| 原生能力执行 | 不加载 Agent Python/技能代码 | 三个原生机制执行、环境配置与健康采集 | Descriptor/Manifest/Health wire |
| 管理能力开关/套餐许可 | 唯一管理策略 | 执行交集、缓存策略版本/刷新 | Policy snapshot 与错误语义 |
| Token/能力调用采集 | 校验接收、结算、展示可信度 | 每次真实调用采集并持久投递 | UsageDelta/回执/关闭清单 |
| 密钥与服务配置 | 本地环境持有自身凭据 | 本地环境持有 Provider 凭据 | 只传 opaque reference |

建议 Backend 新增 `services/agent_entitlements/`（权益、预留、签发、结算）和 `services/agent_capabilities/`（Catalog 与管理策略），沿现有 api/schemas/models 组织，只有职责需要时再拆文件。Agent 在 control 增授权/调用状态机，在 execution/provider 边界统一采集，application 负责注入；capabilities 增描述导出适配即可，不新建平行执行引擎。

| 数据归属 | 建议实体与核心约束 |
| --- | --- |
| Backend DB | Submission `(owner, client_key)` 唯一及 digest；PlanRevision/UserPlanAssignment/EntitlementRule；Reservation/GrantRevision 与唯一 submission 关联；WindowCounter/滚动账本索引；CallPermit `(audience,call_id)` 唯一；UsageInbox measurement_id 唯一、观察 `(call_id,revision)` 唯一；UsageLedger/调整账；CatalogRevision/CapabilityPolicy/Health 投影；恢复与撤销 Outbox |
| Agent DB | 现有 Task/Run/Event/Control/派发 Outbox；GrantBinding `(issuer,grant_id)` 和 `(owner,submission_id)` 唯一；授权修订快照；Execution 关联租约世代；CallIntent/Permit/Started/Observation；独立 UsageOutbox；任务关闭清单；部署 manifest 和健康事实（需要持久化时） |
| 共享包 | 纯 Schema/enum/protocol；不存 ORM、密钥、套餐、数据库连接或运行配置 |

跨库只有 opaque ID，没有跨服务 FK、SQL join 或共享写表。Agent 不访问 Backend DB；Backend 不访问 Agent DB。即便部署在同一 PostgreSQL 实例也使用独立连接权限和迁移所有权。Backend 保存 Usage 是消费执行事实形成权益账本，不是另建一套 Agent 执行状态机。删除产品 Session 不级联删除结算审计；保存时限由数据政策另定。

## 7. API、状态与错误码建议

本节明确区分当前已存在的 v1 与待实现的 v2。**保留现有 v1 Wire Schema、响应字段、错误格式及其旧任务语义不变**，不在 v1 加 grant/mode/schema_version 等字段。新授权提交/执行及独立新协议全部使用下列明确 v2 路径，不再使用“先列 v1、发布时再映射”的约定。HTTP 路由版本与消息 schema_version 独立：以下新协议首版 schema_version=1（新响应也显式携带），不是旧 v1 Wire，也不是 HTTP v1 的别名；未知消息版本严格拒绝。URI 中没有 schema_version 参数来动态降级协议。

用户接口不能传入 grant、选择 metering_context 或调用内部结算。内部调用要求服务角色、超时、请求 ID、幂等键与审计，不泄漏凭据。下表每一项都是完整路径；`{...}` 仅表示路径参数，不是可省略前缀。

| 现有接口（事实，均保持 v1） | 既有语义与新协议边界 |
| --- | --- |
| Backend `POST /api/v1/agent/run`、`POST /api/v1/agent/sessions/{session_id}/run`、`GET /api/v1/agent/sessions/{session_id}/run/stream` | 旧产品提交/回放；不新增授权字段或令旧请求隐式进入 authorized。A2 新入口使用下表 v2；截止旧新提交是部署准入策略，不将 v1 载荷改造成 v2 |
| Backend `GET /api/v1/agent/config`、`POST /api/v1/agent/run/{run_id}/stop`、`POST /api/v1/agent/run/{run_id}/steer` | 旧配置、旧运行控制，格式不变；新任务用 v2 对应操作，不经旧 Gateway 解析新对象 |
| Backend 现有 `/api/v1/agent` 下 Session CRUD/import、uploads、workspace、文件/资源及 export；`POST /api/v1/agent/internal/knowledge/search`、`GET /api/v1/agent/internal/knowledge/papers/{paper_id}`、`GET /api/v1/agent/internal/knowledge/graph/{paper_id}` | 本轮不扩展；既有 owner/服务认证边界保留，不作为模式选择或授权旁路 |
| Agent `GET /internal/v1/config`；`POST /internal/v1/tasks`、`GET /internal/v1/tasks/{task_id}`、`GET /internal/v1/tasks/{task_id}/runs`、`GET /internal/v1/runs/{run_id}` | 原 Wire/旧任务对象；不添加 BudgetGrant、模式或绑定字段；不通过 v1 查询序列化新 v2 任务 |
| Agent `POST /internal/v1/tasks/{task_id}/cancel`、`POST /internal/v1/runs/{run_id}/steer`、`GET /internal/v1/runs/{run_id}/controls`、`GET /internal/v1/runs/{run_id}/events` | 旧任务控制及旧事件格式保持不变；新 v2 任务使用 v2 生命周期接口 |
| Agent `POST /internal/v1/worker/claim`、`POST /internal/v1/runs/{run_id}/heartbeat`、`POST /internal/v1/runs/{run_id}/events`、`POST /internal/v1/runs/{run_id}/report` | 旧 Worker 契约不扩字段；v2 队列/任务在路由与调度资格上隔离，旧 Worker 不可领取或操作 v2 任务 |
| Agent `POST /internal/v1/workspaces`、`POST /internal/v1/workspaces/claim/prepare`、`POST /internal/v1/workspaces/claim/commit`、`POST /internal/v1/workspaces/{workspace_id}/files`、`GET /internal/v1/sessions/{session_id}/files` | 不扩展；与调用授权协议无混用 |

| 新增方向 / 明确 HTTP 路径（建议） | 消息 / 阶段及请求响应语义 |
| --- | --- |
| Backend 本地 prepare_metering_profile / authorize_submission（非 HTTP） | A1 建立准入模式元数据；A2 authorize_submission 原子创建正式 Submission/预留/Grant，同键重放不增余额；二者不能在失败时互相回退 |
| 用户/BFF→Backend `POST /api/v2/agent/run`、`POST /api/v2/agent/sessions/{session_id}/run`；`GET /api/v2/agent/sessions/{session_id}/run/stream` | 新产品提交/回放 Wire（schema_version=1），Backend 从可信身份和准入政策决定 mode；请求不接受客户端授权材料/模式。A1 受控准入 observation_only，A2 正式准入 authorized |
| 用户/BFF→Backend `POST /api/v2/agent/run/{run_id}/stop`、`POST /api/v2/agent/run/{run_id}/steer` | v2 运行控制；沿可信 owner 校验，用 v2 Gateway 操作 Agent，不修改原 v1 操作格式 |
| Backend→Agent `POST /internal/v2/tasks` | 新 TaskSubmission（schema_version=1），带 metering_profile_id/metering_context/owner_id/request_digest 和原业务请求；authorized 另必需正式 submission_id/budget_grant，observation_only 必须 budget_grant=null。返回新 Task Wire 含模式关联、binding_status，BudgetLimits 独立 |
| Backend→Agent `GET /internal/v2/submissions/{submission_id}`、`GET /internal/v2/tasks/{task_id}`、`GET /internal/v2/tasks/{task_id}/runs`、`GET /internal/v2/runs/{run_id}` | v2 查询（schema_version=1，owner 过滤）；submissions 路径只查正式 Backend ID，不接受 obs: ID。A1 超时以原提交幂等键重放或按 Task 查询恢复 |
| Backend→Agent `POST /internal/v2/tasks/{task_id}/cancel`、`POST /internal/v2/runs/{run_id}/steer`、`GET /internal/v2/runs/{run_id}/controls`、`GET /internal/v2/runs/{run_id}/events` | v2 生命周期 Wire（schema_version=1），关联持久模式；查询不创建或更改授权 |
| Worker→Control `POST /internal/v2/worker/claim`、`POST /internal/v2/runs/{run_id}/heartbeat`、`POST /internal/v2/runs/{run_id}/events`、`POST /internal/v2/runs/{run_id}/report` | 新 Worker Wire（schema_version=1），claim 含 profile/mode/execution 身份；历史 v1 Task 只有明确登记后才可移交此队列。原始 lease_token 只在此本地边界使用 |
| Control→Backend `POST /api/v2/agent/internal/task-metering-bindings`、`GET /api/v2/agent/internal/task-metering-bindings/{metering_profile_id}` | A1 必需模式关联（schema_version=1）：profile、Task、owner/audience、digest、ID 来源及关联 ID → 持久确认/原记录；Backend 只确认预先创建的 profile，消息不能创建或选择模式，异绑定 409 |
| Control→Backend `POST /api/v2/agent/internal/grants/{grant_id}/bind`、`GET /api/v2/agent/internal/grants/{grant_id}/binding` | A2 bind 请求（schema_version=1）含 expected_revision、expected_binding_revision、owner/submission/digest/task/audience → 独立 GrantBindingReceipt；GET 返回原件，幂等不改根绑定 |
| Control→Backend `POST /api/v2/agent/internal/grants/{grant_id}/validate`、`GET /api/v2/agent/internal/grants/{grant_id}/revisions/{revision}` | A2 当前根状态/current_revision 查询和精确历史签名 Revision 取回；schema_version=1，不续期、不加额 |
| Backend→Agent `POST /internal/v2/grants/{grant_id}/revisions`、`POST /internal/v2/grants/{grant_id}/revocations` | A2 分开的新 Revision 与撤销事件 Wire，schema_version=1；Revision 验签/CAS 上升，撤销按根状态事件去重且不改历史 payload |
| Worker→Control `POST /internal/v2/runs/{run_id}/call-intents` | A1 observation_only 本地调用登记 Wire（schema_version=1），Control 按持久 profile 决定流程；不能拿来替代 authorized 的 Permit，authorized 请求该无 Permit 路径拒绝 |
| Worker→Control `POST /internal/v2/runs/{run_id}/calls/authorize` | A2 authorized 调用登记/授权 Wire（schema_version=1），execution/worker/token、call/logical ID、精确能力用途/上界 → Control 代申请 Permit |
| Control→Backend `POST /api/v2/agent/internal/call-permits` | CallPermit / CallPermitResponse，schema_version=1；只接受 authorized 正式 Submission，按 call_id/digest 幂等分配 |
| Control→Backend `POST /api/v2/agent/internal/call-permits/{permit_id}/start`、`GET /api/v2/agent/internal/call-permits/{permit_id}`、`POST /api/v2/agent/internal/call-permits/{permit_id}/void` | start/query/void Wire，schema_version=1；唯一启动授权及撤销串行、查询不重发启动权、void 必需封闭证明 |
| Worker→Control `POST /internal/v2/calls/{call_id}/start`、`POST /internal/v2/usage-observations` | 本地 start / ObservationSubmission Wire，schema_version=1；按已持久 mode 选择 A1 本地 start 或 A2 Backend 门禁，不按请求猜模式。完成观察由 Control 分配 measurement/revision 后输出 UsageDelta；允许历史 execution 补报 |
| Backend→Control `GET /internal/v2/tasks/{task_id}/call-facts/{call_id}` | A1 必需 CallStartFact，schema_version=1；认证只读持久事实，详见 4.5，不返回租约 token，不授予启动权 |
| Agent→Backend `POST /api/v2/agent/internal/usage-deltas:batch` | UsageDelta batch / UsageBatchAck，schema_version=1；独立传输同时接两种已登记模式，不能把 HTTP v2 等同 authorized，逐项 durable/投影状态独立 |
| Agent→Backend `POST /api/v2/agent/internal/grants/{grant_id}/close` | A3 TaskCloseManifest，首版 schema_version=1；仅 authorized 账本关闭，不以 Task 终态释放全部余额 |
| Agent→Backend `POST /api/v2/agent/internal/capability-manifests`、`POST /api/v2/agent/internal/capability-health` | B1 Manifest / B3 HealthObservation 独立消息，首版 schema_version=1；与 Task 计量模式无关，后者待 B3 冻结 |
| Backend→Agent `GET /internal/v2/capabilities` | B1 Manifest 只读分页快照，schema_version=1；不是 v1 config 的字段扩展 |
| 管理端→Backend `GET /api/v2/agent/capabilities`、`PATCH /api/v2/agent/capabilities/{capability_id}/policy` | B1 只读 Catalog / B2 策略写入，schema_version=1；PATCH expected_policy_revision/admin_enabled/disable_scope/effective_at，冲突 409；不安装代码 |
| Backend→Agent `GET /internal/v2/protocol-capabilities`；Control→Backend `GET /api/v2/agent/internal/protocol-capabilities` | 两端受认证能力发现，schema_version=1；supported HTTP/message schema、execution_modes、deployment/build_revision。只读声明不决定具体 Task 模式，不扩现有 AgentConfigWire |

超时处理：submit/bind/authorize 超时均用原 ID 查询或重试，不能创建新提交/调用以“绕开”不确定响应。启动回执超时先查调用状态；发送不明不重复外调，转 unknown。用量上报超时允许持久积压并退避；积压达到明确容量上限时停止新增付费调用，阈值为运维配置。

### 7.1 错误兼容与重试分类

v1 现有错误格式不变；新 v2 错误 Wire 保留整数 `code` 与安全 message/status，并定义机器可读 `reason_code`、`retryable`、`request_id`、可选 `retry_after_ms`。下表是 reason_code 名称建议，**没有占用新的整数码号段**；整数映射评审时对照全仓错误登记表确定。任何版本的 code 都不能改成 string；不向旧消费者发送 v2 新错误字段。

| reason_code | HTTP | 行为 |
| --- | --- | --- |
| CONTRACT_VERSION_UNSUPPORTED / INVALID_GRANT | 422 / 403 | 不自动执行重试；无效签名/受众拒绝 |
| GRANT_BINDING_MISMATCH / IDEMPOTENCY_CONFLICT | 409 | 同键异请求、跨 owner/task/digest 冲突，人工/调用方修正 |
| GRANT_EXPIRED / GRANT_REVOKED | 403 | 停新调用，Backend 评估续期/重新授权；不触发现有三 Run 盲重试 |
| QUOTA_EXHAUSTED | 429 | 附最早可能再试时间（可未知），不假定滚动窗口必然届时释放 |
| CAPABILITY_NOT_ALLOWED / CAPABILITY_DISABLED | 403 | 权限/管理员策略拒绝 |
| CAPABILITY_VERSION_UNAVAILABLE / CAPABILITY_DEPENDENCY_UNAVAILABLE | 409 / 503 | 缺版本或依赖；不能自动换版本；仅可在同授权下重调度匹配环境 |
| CAPABILITY_UNHEALTHY / AUTHORIZATION_UNAVAILABLE | 503 | 依策略稍后重试，期间不新增付费调用 |
| LEASE_STALE / CALL_ALREADY_STARTED | 409 | 旧 Worker 不可执行；already_started 回读事实不再发请求 |
| USAGE_OBSERVATION_CONFLICT | 409 | 保留冲突审计，不重复扣减；缺 usage 本身不算格式错误 |
| USAGE_ASSOCIATION_INVALID | 422 | 隔离无法匹配持久 Task 模式/启动事实的观察；authorized 另需 Permit 关联，A1 不伪造 Permit |
| METERING_MODE_UNKNOWN / METERING_MODE_MISMATCH / CALL_FACT_UNVERIFIED | 422 / 409 / 503 | 未知模式拒绝启动、冲突/未核验事实隔离；查询不可用可重试，不自动切 observation_only |
| SETTLEMENT_PENDING | 202 | 非错误；明确仍有未知/在途，不展示已全额释放 |

### 7.2 协议升级与可冻结边界

当前 Wire extra=forbid。字段可选不意味着旧接收方能忽略它，响应新增字段同样会破坏旧 Gateway。保留严格校验，不全局改 extra=ignore。§7 完整路径表是本轮唯一命名依据，所有新路径明确为 v2；不存在 Usage/Manifest 走新增 v1 路径的例外。首版新消息 schema_version=1 与 HTTP v2 路由不是同一个版本维度；共享包必须使用新类型区分现有 Wire，不能以数值同为 1 为由复用旧 TaskSubmissionWire。下面兼容矩阵同时约束请求和响应。

| 生产者 / 目标 | HTTP 路径族 | 消息 Schema | 兼容结果与模式约束 |
| --- | --- | --- | --- |
| 旧 Gateway → 旧或升级 Agent 的旧接口 | `/internal/v1/tasks` 及 v1 生命周期 | 现有 v1 Wire，无新增字段 | 保持旧行为，仅旧任务；不变成 authorized，也不自动登记 observation_only |
| 旧 Worker → 旧或升级 Control 的旧队列 | `/internal/v1/worker/claim` 及 v1 Worker 接口 | 现有 Worker Wire | 只分配旧队列；新 v2 Task 在路由/调度资格上隔离，不能靠旧 Worker 忽略字段执行 |
| 新 Gateway/Worker → 升级服务旧接口 | 同上 v1 | 仅旧 Wire | 仅为排空 legacy；不得把 authorized profile 或新字段删掉后重送 v1 |
| 新 v2 Gateway → 旧 Agent | `/internal/v2/tasks` | 新提交 schema_version=1 | 不支持/404 则停止提交并保留待恢复记录；不改调 v1 |
| 新 v2 Worker → 旧 Control；旧 Worker → v2 队列 | `/internal/v2/worker/claim` / v2 生命周期 | 新 Worker schema_version=1 | 版本/角色/队列不匹配拒绝，不返回旧格式的“可执行”任务 |
| 新 v2 Gateway/Worker → 新服务，A1 | `/internal/v2/tasks`、v2 claim/call-intents/start | 新 Wire schema_version=1 | Backend 持久 observation_only profile＋Task 绑定确认；本地 start，无 Permit，不能接 authorized Task |
| 新 v2 Gateway/Worker → 新服务，A2 | `/internal/v2/tasks`、v2 claim/authorize/start | 新 Wire schema_version=1 | Backend 持久 authorized profile＋正式 Submission＋Grant/Receipt/Permit；缺任一必要关联即拒绝 |
| 已有 v1 Task 登记后 → 新计量 Worker | 模式登记及 v2 claim/call-intents/start | 独立新消息 schema_version=1 | 需 Backend 显式准入和确认、旧执行权排空/封闭再移交；只记录接入后的新调用，不改旧 Wire/历史事实 |
| 新模式绑定生产者 → 新 Backend | `/api/v2/agent/internal/task-metering-bindings` | 模式关联 schema_version=1 | 只能绑定 Backend 预建 profile；未知或异绑定拒绝，不能借绑定新建 observation_only 模式 |
| Agent A1/A2 Outbox → 新 Backend | `/api/v2/agent/internal/usage-deltas:batch` | UsageDelta/Ack schema_version=1 | 两种模式共用传输、按持久记录判定；旧未登记任务/模式冲突隔离，authorized 缺 Grant 关联不降级 |
| 新 Backend → 新 Control 持久事实查询 | `/internal/v2/tasks/{task_id}/call-facts/{call_id}` | CallStartFact schema_version=1 | 首次投影前核验/缓存；失败保持待核验，不采信 Worker 或任意查询地址替代 |
| Manifest/Health 生产者 → 新消费者 | Backend `/api/v2/agent/internal/capability-manifests`、`/api/v2/agent/internal/capability-health`；Agent `/internal/v2/capabilities` | 各自 schema_version=1 | 独立消息，不需要 Task Grant；Health 待 B3 启用，B1 不冒称已支持 |
| 任意新协议生产者 → 旧消费者 | 上述 v2 新协议路径 | 新消息 | 未声明支持即停发/持久积压；不将消息包装成旧 RunReport，也不解释失败为计量免费 |
| 新生产者 → 新消费者但 Schema 未知/字段非法 | 任意 v2 路径 | 未知 schema_version 或违反 extra=forbid | 明确拒绝；可解析批次的非法项逐条 rejected/quarantined，不推断模式、不无授权执行 |
| 新产品/管理客户端 → 对应新 Backend | `/api/v2/agent/run`、session run/stream、stop/steer、capabilities/policy | 各自新 Wire schema_version=1 | 经身份/角色授权；mode 由 Backend 决定。旧客户端继续旧产品契约，不解析新响应 |
| 探测/回滚 | 两端 v2 protocol-capabilities / 持久新队列 | 能力发现 schema_version=1 | 发现只选择已声明协议，不能改变 Task 模式；回滚停止新准入，保留模式/新事实接收查询，不降级既有任务 |

1. T0 签署字段/枚举/必选及 null 规则、版本矩阵、整数错误码映射和规范化/状态迁移测试向量；发布 Shared Contracts 新类型，现有 v1 类型行为不变。定义受认证的协议能力查询，返回 supported_http_versions、各消息 supported_schema_versions、authorization_required、deployment/build_revision；不把探测字段塞入旧 AgentConfigWire。
2. 先扩展各服务本地存储和恢复读路径（后续研发任务），部署 Backend 模式记录/绑定与 Inbox、Agent v2 Task/事实查询及 Worker 接收器；B1 时再部署 Manifest 接收器。随后部署按持久 Task 模式/协议路由的 Gateway、Control/Worker，对端未升级时生产方不得发送新字段。错误 reason_code 也只发给匹配响应模型的新消费者。逐对验证矩阵和严格拒绝，不因 A1 先行而依赖完整 B1/A2。
3. A1 由 Backend 显式准入 observation_only，确认 Task 模式绑定后启用采集/Inbox，首次投影核验 Control 持久事实；既有旧任务只在明确登记并移交执行权后接入。B1 随后启用只读 Manifest，并复用 A1 身份摘要；二者不打开付费授权门禁。以持久交付确认、事实验证和缺口对账验收，不把该阶段数据标成已扣费。
4. A2 在明确匹配版本的封闭队列/部署中启用签名、绑定、Permit/start 和 authorized 入口；升级 Worker 必须能识别任务模式，旧 Worker 无权 claim 新任务。启用前验证必要协议能力，未知版本、字段、签名或授权服务故障均拒绝/暂停新执行，不捕获解析异常后改调 v1。
5. A2 切换时按负责人批准的准入修订截止旧入口及 A1 新准入，已有 legacy_unmetered 和 observation_only Task 按持久记录显式隔离、排空，不伪造授权。截止入口不改变仍在服务的旧 v1 Wire/旧任务操作语义。禁止将 authorized Task 路由旧 Worker；免费/匿名的新授权任务也需显式 grant。排空并核对 Outbox/Inbox 后才移除旧协议读路径。
6. 回滚只停止/隔离 v2 新提交并保留新消息接收、补报和恢复能力，不能将 v2 Task 降为 legacy；已发新 Schema 的持久队列未排空前不得回滚成只读旧 Schema 的消费者。未来新增字段/枚举先升级消费者再生产者，不兼容变更用新 Schema/入口，并保留可查询的支持矩阵。

### 7.3 其余配套协议与后续冻结点

**PermissionSnapshot**：Backend 所有的不可变权限快照，最小字段 `schema_version=1, snapshot_id, issuer, audience, owner_id, submission_id, catalog_revision, manifest_refs[], policy_revision, issued_at, expires_at, permissions[], snapshot_digest`；manifest_refs 为 deployment_id/manifest_revision/snapshot_digest。permissions 项必含 `capability_id, capability_version, invocation_modes[], purposes[], admin_enabled, disable_scope, effective_at, dependency_permissions[]`，max_attempts 为可空非负整数。精确版本而非 alias，缺项拒绝；依赖必须显式列出并与自身能力权限取交集。Grant 引用 snapshot_id/digest 并覆盖其完整内容或签名摘要，Agent 获取原件后核验，不接收浏览器覆盖。快照只表示签发时政策，紧急撤销仍在 start 门禁在线判定；普通禁用作用域由该修订声明。B1 无此快照时 effective_allowed=null；A2 可用同 Schema 静态批准快照开发，不依赖 B2 管理 UI。

| 后续协议 | 必要字段（当前最小候选，不表示已实现） | 最迟冻结时间 |
| --- | --- | --- |
| TaskCloseManifest | schema_version、close_id、revision、supersedes_close_id、issuer/audience、owner/submission/task/grant、grant_revision、run_ids[]、execution_ids[]、call_ids 或其可分页完整清单引用/摘要、permit_ids[]、call_count、last_task_usage_sequence、outbox_ack_high_watermark、missing_sequences[]、unknown_call_ids[]、unknown_count、all_executions_sealed、generated_at、manifest_digest。重发同 ID 同内容幂等，修订追加；Backend 对比自己的 Permit 集合及序号连续性，不能只信 count/high-watermark | A3 实现开始前；A1 先保留 task_usage_sequence 和启动/观察事实，以便后续生成 |
| CapabilityHealthObservation | schema_version、observation_id、issuer/audience、deployment_id、manifest_revision、capability_id/version、configuration_revision、status、checked_at、valid_until、reason_code、probe_kind、probe_version、source、可空 system_probe_call_id。按 observation_id 幂等，迟到不覆盖更新 checked_at 的结果；过期 unknown，管理字段不由 Agent 改写 | B3 实现开始前；B1 仅配置状态及 unknown，不承诺探活 |

这些协议只补完整性和健康事实，不增加执行 Registry、调度引擎或结算权威。TaskCloseManifest 没有完整逐调用集合时不能作为全额释放证明。

### 7.4 契约冻结状态表

Frozen 表示技术原则已收敛、提交本轮整体批准；**本轮尚未取得正式签署**。Conditional 的语义与最小定义已在本文补齐，但须按条件核准后才能宣告 Schema 冻结；Deferred 不得写成代码中已批准的默认业务值。批准时记录协议修订、负责人及日期，不能仅把文档状态改成“已冻结”。

| 状态 | 项目 | 冻结边界 / 尚需动作 | 最迟阶段 |
| --- | --- | --- | --- |
| Frozen | 服务所有权、数据库隔离 | Backend 权益账本，Agent 执行事实，共享包纯协议；无跨库读写 | T0 批准 |
| Frozen | 身份链与 Grant 根/Task 关系 | authorized 使用 Backend Submission；根 binding 独立于不可变 Revision，null Revision 不回填；A1 obs: 计量关联不冒充正式 Submission；重试共享根与剩余预留 | T0 批准 |
| Frozen | Run BudgetLimits 与用户权益分离 | 每 Run 上限不能当跨 Run 权益余额 | T0 批准 |
| Frozen | UsageDelta 追加事实、幂等与修订 | measurement_id、call/revision、绝对值、至少一次、unknown≠0；历史租约事实可补报 | T0 批准 |
| Frozen | Capability ID/精确版本、保留原生 Registry | ToolRegistry / SkillStore / ModelRegistry 不重写；A1/B1 使用同一 capability_identity_v1；Model 配置版非权重版 | T0 批准 |
| Conditional | BudgetGrant 完整 Schema / Allocation | 3.2 字段、规范化、签名白名单和 CAS 正反向量、类型/基数及整数码映射由契约负责人核准；算法依赖选型完成 | A2 前（T0 可先冻结语义） |
| Conditional | GrantBindingReceipt | 3.2–3.3 的 bound_task_id、绑定所指历史 Revision 摘要、根绑定/续签串行 CAS、双 typ 验签及迟到撤销向量核准；不得改初始 null payload | A2 前 |
| Conditional | CallPermit / CallPermitResponse | 3.7 双状态机、start/撤销线性化、void 证明及包含所有 window_ref.end 的截止向量核准；TTL/偏差数值另批，不夹带 lease_token | A2 前 |
| Conditional | UsageDelta 完整 Schema | 4.1–4.5 必选/null、profile/mode/ID 来源一致性、次数/activation、乱序和缺口向量核准；authorized 解析/配置失败不得降级 | A1 前 |
| Conditional | A1 模式关联与调用事实验证 | 4.5/7 的 Backend 权威 profile、独立 task-metering-bindings、CallStartFact 查询 Schema/角色权限/核验缓存/隔离与审计向量核准 | A1 前 |
| Conditional | A1 精确能力身份最小 Schema | 4.5 的三类身份对象/规范化摘要向量核准，禁止 mtime/密钥；B1 Manifest 复用，不等待完整 Catalog | A1 前 |
| Conditional | UsageBatchAck | 4.3 逐条 durable/隔离/拒绝语义、批量限制及重投向量核准 | A1 前 |
| Conditional | Capability Descriptor / Manifest | 5 节字段权属、精确版本摘要输入、分页全量激活向量核准 | B1 前 |
| Conditional | PermissionSnapshot | 7.3 版本/权限交集、调用模式、撤销作用域及签名摘要引用核准 | A2/B2 前 |
| Conditional | 协议版本兼容方案 | §7 完整 v2 路径、7.2 双向兼容矩阵及消息 schema_version=1 的独立含义已补齐；服务负责人仍须核准部署/排空/防降级/回滚和旧 Worker 隔离向量 | A1 启动核准子集、发布前验证；B1/A2 各自切换前 |
| Deferred | 套餐数值、窗口额度数值、具体预留参数 | 业务负责人批准后固化 Backend policy_revision | A2 前 |
| Deferred | 缺失用量超期、结算退款、超额差额 | 不把未知当零，不裁剪事实；具体处置等待批准 | A3 前 |
| Deferred | 普通禁用默认口径、紧急撤销 SLA | 技术生效边界已定义，业务选用范围/短 TTL 数值及 SLA 未批 | B2 / A2 启动门禁验收前 |
| Deferred | 健康放行策略 | unknown/degraded、探测费用与系统授权策略未批 | B3 前 |
| Deferred | 生产密钥部署方案 | 不影响 A1/B1；A2 可离线测试签名，生产启用前批准托管/轮换/吊销 | A2 生产发布前 |

## 8. 待负责人决定的业务规则及推荐

以下均为选项比较与推荐，不是已批准规则。业务批准记录需绑定规则修订，测试按批准口径生成，套餐数值另行确定。

| 业务问题 | 推荐方案（仍未批准，含权衡） | 待负责人批准 | 最迟决策阶段 |
| --- | --- | --- | --- |
| 套餐/用户覆盖规则 | Backend 不可变规则修订，先明确免费/匿名/付费边界，Agent 不判断 VIP | 产品/权益负责人（待指定）：套餐档位、数值、用户覆盖优先级、变更时现存授权口径 | A2 前；A1 不等待 |
| 5 小时 Token | 推荐滚动 18,000 秒，平滑但需索引、迟报和持有量处理；固定五小时更简单但边界突发且需 UTC 锚点 | 产品/权益负责人：任意连续五小时或固定窗口、限额数值 | A2 前 |
| 每日 Token | 推荐固定业务时区自然日，候选 Asia/Shanghai；滚动 24h 更平滑但展示复杂 | 产品/权益负责人：时区、日界、额度值、变更时区限制 | A2 前 |
| 每能力次数 | attempted/successful 均记录；风控推荐按尝试，权益计次可按成功但失败成本仍留存 | 产品/权益负责人及能力负责人：Tool 成功判据、模型重试和 Skill activation 是否扣次数，是否收费 | A2 额度口径；A3 收费/退款口径 |
| Usage 缺失 | 推荐先暂扣并查上游证据，超期 reconciliation_required；估算可释放占用但有误扣风险，人工处理成本高 | 结算/财务负责人（待指定）：宽限时长、最终估算权限、人工流程、revision 缺口超期处理 | A3 前；A1 只记录 unknown，不等待 |
| 并发预留 | 推荐小额启动＋按调用分配/补充；整任务预留易占满并发，在线许可方案依赖可用性 | 产品/权益及 Backend 负责人：启动额、补充上限、排队/未决持有时长、无法证明 Token 上界时拒绝或接受风险 | A2 前 |
| 普通禁用及权限范围 | 推荐普通禁用仅新提交，PermissionSnapshot 固化；latent、forced、summary 仍走权限交集 | 产品/安全及能力负责人：默认作用域、调用模式权限、是否取消整个 Task；不以隐藏代替禁用 | B2 前；B1 不等待 |
| 紧急撤销 | 推荐每次 Backend start 在线判定；已 start_committed 只保留短有效期，在途尽力取消 | 安全/运行负责人（待指定）：start_before/TTL 数值、撤销 SLA、范围与紧急操作权限 | A2 启动门禁验收/B2 前 |
| Token 范围及超预留 | 推荐 prompt＋completion 原始实测，不重复累加缓存/推理；超额事实完整保存 | 产品/结算负责人：Token 计入范围在 A2 确定；差额用户承担、退款及追扣在 A3 批准 | A2 / A3 分别批准 |
| 调用时间归属 | 推荐可信 start 归属窗口，UTC 存储；按结束/分段通常缺证据 | 产品/权益负责人：跨日、迟报历史调整、政策切换口径；Backend 授权到本地 start 跨窗口时如何重检或限制截止 | A2 前 |
| 取消、失败与退款 | 推荐只释放确定未用预留，实际上游成本另存，取消不等于无费用 | 结算负责人：失败/取消退还、成功收费、unknown 的最终处置、人工调整审计 | A3 前 |
| 健康放行及探测成本 | 推荐 configured 与 healthy 分离，unknown/degraded 显式策略；探测用独立系统 owner 与授权 | 能力/运行及产品负责人：unknown/degraded 是否放行、观测有效期、探测成本承担 | B3 前；B1 不等待 |
| 密钥生产运行 | 推荐先发公钥再切签名，历史验证档案保留；不在仓库保存真实凭据 | 安全/运行负责人：托管、轮换周期、吊销流程、时钟偏差和短截止参数 | A2 生产启用前 |

如业务选择严格五小时/每日实际硬上限，还必须明确“不支持可靠 Token 上界的模型是否拒绝使用”或接受受控超额风险。不能同时承诺任意 Provider 可用、未知用量立即返还和绝对不超额。

## 9. 研发拆分与并行依赖

```text
T0 契约评审 / 冻结技术语义
 ├─ A1 调用级计量与可靠上报 → A2 权益预留/授权门禁 → A3 结算/对账
 └─ B1 原生清单/统一描述 → B2 Catalog 管理策略 → B3 健康/版本状态
                A2 与 B2 通过 PermissionSnapshot/精确能力版本接口会合
                      ↓
             I 两线集成：从提交到结算与能力撤销完整闭环
```

T0 是当前设计产物及后续评审，不包含实现新 Contracts。本次不因其他阶段未来需要而提前修改代码。

| 阶段及交付物 | 后续修改目录 | 共享协议依赖与独立性 | 验收出口 |
| --- | --- | --- | --- |
| T0 协议批准与发布计划 | 本文；批准后才改 `packages/agent-contracts/src/agent_contracts/`、`tests/` 和 `docs/agent/contracts.md` | 两线共用 BudgetGrant/UsageDelta/Descriptor；A1 另需模式关联/CallStartFact/能力身份最小 Schema；业务未决项不阻塞语义评审，但阻塞相应规则上线 | 三方字段/状态/错误/幂等评审；核准完整 v2 路径/兼容矩阵、模式防降级和不可变根绑定；Conditional 不凭修订自动变 Frozen |
| A1 全调用计量：交付本地调用日志/观察、独立 Outbox、批量 Inbox、模式关联、事实查询及核验投影 | Agent `execution/`、`integrations/llm/`、`worker/`、`control/`、`api/`、`infrastructure/`、`application/` 注入；Backend `services/agent_entitlements/` 仅模式关联/Inbox/核验、`agent_gateway/` 事实查询与 v2 提交、models/schemas/api、对应 tests | UsageDelta/Ack、模式绑定/CallStartFact、capability_identity_v1、v2 Task/Worker 与兼容子集；不依赖 VIP、套餐、Grant 签名/扣费或完整 B1 Manifest | 所有真实调用及 activation 有持久事实；Backend 首次投影前查验；模式未知/篡改/错误降级被拒绝或隔离；Tool/Skill/Model 身份可复现；重投/乱序/历史租约不漏记不重复投影；旧 Wire 不变 |
| A2 权益与执行权限：交付 Submission/预留账本、Grant 签发绑定、Permit/start 与撤销门禁 | Backend `services/agent_entitlements/`、`agent_sessions/`、`agent_gateway/`、`api/agent.py`、models/schemas；Agent control/worker/application/execution、`integrations/backend/` | Grant/Allocation、GrantBindingReceipt、CallPermit/Response、PermissionSnapshot；复用 A1 权威模式关联和事实验证，正式准入记录 authorized；B2 未就绪时用同 Schema 的批准静态快照开发 | 两入口同 submission 幂等、pending 不执行、初始 null payload 不改/根绑定与续签 CAS、全窗口 end 截止、撤销竞态、旧 Worker 不得 start、所有 Run 不重置额度，任意错误不降为 observation_only |
| A3 结算与对账：交付追加账本调整、关闭清单、恢复/对账作业与可信展示投影 | Backend 权益服务/账本/后台恢复作业、agent_sessions 产品投影；Agent control 用量 Outbox/close 清单；后续各自 migrations/tests | UsageDelta/Ack、Grant/Permit 及 A3 前冻结 TaskCloseManifest；依赖 A1/A2 和结算退款批准，可回放事实开发，不等待 B3 | unknown 不变零、迟报/修正调整一次、Task 关闭核对集合和缺口、取消失败释放确定未用、窗口迁移/上游差额可解释 |
| B1 描述与只读清单：交付原生 Descriptor 导出、完整 Manifest 及只读 Catalog API | Agent `capabilities/` 导出适配、application、extensions、integrations/llm、api；Backend `services/agent_capabilities/` 读模型、api/schemas/models（仅按持久快照需要） | Descriptor、CapabilityManifest，复用已核准 capability_identity_v1；A1 不等待 B1，B1 不依赖套餐/完整管理策略；不重写原生机制 | 三类真实能力可枚举；与 A1 同产物版本摘要一致；discoverability/allowed/native/admin/configured/health 分离；全量快照、只读 v2 Catalog、不泄漏密钥/地址、无动态加载 |
| B2 管理策略：交付管理元数据/权限快照、CAS 更新、禁用与紧急撤销消费 | Backend agent_capabilities、api/schemas/models；Agent control/application 策略消费；后续各自 migrations/tests | B1 ID/version、7.3 PermissionSnapshot、A2 Grant/Permit；依赖禁用及模式权限批准，管理 UI 不阻塞 A2 静态快照开发 | 管理记录不能制造代码、CAS 防覆盖、策略乱序不回退、禁用/授权含 forced Skill/latent Tool/summary；与 A2 撤销边界对接 |
| B3 健康与部署状态：交付健康观察、有效期/过期投影和批准放行策略 | Agent integrations/能力健康观测与 infrastructure（按需）；Backend agent_capabilities 健康投影、schemas/api | B1 Manifest、B3 前冻结 CapabilityHealthObservation；与 A2/A3 业务独立，依赖健康策略批准 | 按 deployment/version 观测、过期 unknown、部分 manifest 不误删、发布不匹配明确拒绝；探测成本标记系统 owner 授权 |
| I 闭环集成 | 上述边界及两服务定向集成测试、contracts tests；后续验收记录仍入 `docs/dev/records/agent/` | 等 A3＋B2；若上线承诺健康门禁同时等 B3。负责人批准规则、协议发布方案是上线前置 | 用户提交→授权→绑定→门禁→执行→逐调用用量→结算→可信余额展示全链路；所有拒绝和恢复可追踪 |

后续数据库模型/迁移分别归各服务，表名和索引随实现评审；本次不创建。两线在 shared 包变更时应按 T0 已批准字段集中维护，避免各自定义不兼容 Permission/Capability ID。

表内 Agent 相对目录均以 `apps/agent/src/agent_app/` 为根，Backend 均以 `apps/backend/app/` 为根；测试分别在 `apps/agent/tests/`、`apps/backend/tests/`，共享协议实现及测试在 `packages/agent-contracts/src/agent_contracts/`、`packages/agent-contracts/tests/`。实际只在已有职责内增文件，不机械创建空层。迁移由各服务现有迁移链管理，不能混用数据库。

当前单主工作区安排为 **T0 批准所需 A1 子集 → A1 → 批准 B1 子集 → B1 → A2/B2 会合 → A3/B3 → I**。独立表示需求和协议不相互阻塞，不要求同时启动两个 Codex。A2/B2、A3/B3 仍可按单工作区顺序安排。

| 交叉修改边界 | 风险 | 单工作区协调要求 |
| --- | --- | --- |
| Shared Contracts 的 wire、exports、enum/protocol 和 tests | A1/B1 各自加版本/公共字段可能不兼容 | 共用一次协议修订清单；先核准后改，完成一组消费者兼容检查后再接下一组 |
| `application/composition.py`、`policies.py`、`facade.py` | A1 注入计量上下文；B1 读取装配清单；A2/B2 再加权限 | A1 先完成最小注入边界；B1 复用结果导出，接续前重读实际 HEAD/工作区，不复制一套组装器 |
| `integrations/llm/agent_stream.py`、`registry.py`、`resolver.py` | A1 逐发送计量/精确执行模型；B1 版本清单/别名；A2 精确门禁 | A1 优先修改真实发送边界，B1 随后复用同一 resolved model 身份，不重写 Provider |
| `control/`、`infrastructure/`、两服务 api/schemas/models | 调用事实、授权与 Catalog 演进可能同时修改入口/迁移 | 每阶段记录尚未交付的接口；同迁移链顺序编号，严禁跨服务写表或拿未批准 Schema 临时上线 |

## 10. 后续实施与验收计划

建议下一轮首个实际业务研发任务：**A1 调用级计量与可靠 UsageDelta 上报闭环**，范围从 Provider 每次真实发送开始，到 Backend Inbox 幂等接收结束，包含摘要、隐式重试、Tool/Skill activation、持久 start、崩溃 unknown 和补报。下一项独立任务为 B1 原生能力只读 Catalog，不等待完整权益业务规则；当前不要求并行启动两个 Codex。

A1 最小可启动条件（指批准后开始研发，不表示当前已实现或可生产运行）：负责人核准 UsageDelta/Ack、Backend 权威模式关联及其绑定协议、CallStartFact 只读查询/核验/审计、capability_identity_v1、v2 Task/Worker 及 §7.2 兼容/防降级子集；明确 A1 准入或旧任务登记范围、服务角色边界和执行权移交方式，单主工作区确认修改范围。发布前必须实际验证角色凭据隔离、持久 start/Outbox/Inbox、事实核验和版本矩阵。A1 不等待 VIP/套餐、Grant 签名、生产密钥或完整 B1 Catalog；不能以其“独立”省略模式权威和事实证据。

B1 前批准 Descriptor/Manifest 子集并复用同一能力身份。A2 前确定权益/额度、绑定/Permit 协议和正式准入切换；A3 前确定结算、退款、未知处理；B2 前确定禁用权限，B3 前确定健康策略。业务选项通过 policy_revision 进入 Backend，而不是散落在 Agent 各调用点。其余 Conditional 项不应被误说成 A1 的全部前置，也不能跳过对应阶段的核准。

后续按改动范围跑定向测试，生产 Provider/数据库验证另经明确环境安排。建议验收用可控 transport 和持久数据库并发场景覆盖以下断言，不以全量测试成功替代业务证据：

1. 两个并发提交竞争同 owner 最后额度，双窗口检查同事务完成，只有可覆盖者获批；同提交键重放返回同 Task/grant，异请求 409。
2. Backend 提交响应丢失、绑定任一侧崩溃、撤销与绑定竞态均可恢复；pending Task 不执行，不产生双份预留。
3. 主模型、摘要、外层重试、内层降级各生成正确真实调用数；失败有实测仍入账，无实测显示 unknown，不把 None 转 0。
4. call start 与 Lease 接管竞争：接管后旧 token 不得新增 start；已 start 的旧请求保留持有量并接受晚报。复现“启动回执丢失”证明不会重发同调用。
5. 同 Run 两个 execution、新 Run 三次尝试都完整计量；grant 余额不重置，未知前序请求不会被新 Worker 重复花掉。
6. Usage 重复、乱序、冲突、版本修正、接收成功后回执丢失均只调整一次；未知→实测释放正确差额；额度服务故障时停新调用但不丢补报。
7. 跨五小时/日界、队列久等、长调用、迟报、授权续期与过期、取消/终态竞争，不能仅靠 TTL 全额返还或错误计入接收日。
8. 普通禁用与紧急撤销按批准语义影响新任务/后续调用，forced Skill、read_skill、latent/派生 Tool、模型 alias/default 和 summary 无旁路。
9. Descriptor code/registered/enabled/health 分离；缺版本不换最新版，健康过期回 unknown，管理员不能注册任意 Python import 或读取配置密钥。
10. 逐 Task 核对 permit/start/完成观察/关闭清单/账本；最终展示明确实测、估算、未知和结算状态，Backend 与 Agent 均无跨库连接。
11. 完整 §7.2 矩阵覆盖旧请求/响应不变、新路径不支持、未知 schema/字段/模式、授权配置/解析失败和回滚；任一失败不得删除授权字段改调 v1 或新建 observation_only profile 承接正式 Submission。
12. A1 completed 先到、启动查询 404/超时/身份冲突、未登记 Task、伪造 Control/Worker 越权均保持待核验或隔离；核验恢复重处理原 measurement_id，不重复投影。旧任务只采 enrollment_at 后事实，obs: ID 不进入正式 Submission/Permit。
13. 绑定前后逐字节核对初始 Grant payload/JWS 均未改变；绑定与续签并发只产生唯一 bound_task_id/原回执，Receipt 摘要只指其历史 Revision，后续 Revision 正确引用原绑定，过期/撤销不被迟到回执复活。
14. 多个固定/自然窗口取最早 end，now=start_before、控制端到 Worker 延迟越界、时钟偏差保守截止均拒绝发送；已 started 但未发送的不明事实不因截止自动退款。Tool 实现/Schema、Skill 资源、Model 非敏感发布配置分别变化应改版本，只有 mtime/缓存或凭据变化不得改版本，B1 Manifest 与 A1 版本逐项相同。

第三轮设计自检：本轮六项评审问题已在现有章节闭合，未发现仍未定义的 P0 协议分支；这是文档自检结论，不是负责人批准、实现证明或运行验收。§7.4 的 Conditional 仍需对应契约核准/向量验证，§8 的业务/运行值继续待负责人决定；若评审认为其中任一技术条件未满足，可继续阻止相应批准/发布，不能用本段替代签署。

本文完成条件为：当前事实有源码位置，协议候选可供签署，业务选项保留决策权，只修订指定文档并完成文档结构/内容/工作区范围检查。上述运行验收属于后续研发工作，本次没有执行或宣称通过。正式批准前保持 Conditional/Deferred 标记，本轮完成后等待负责人评审，不提前实施 A1/B1。
