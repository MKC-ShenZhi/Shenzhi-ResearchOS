# 用户权益与执行权限（v2 候选实现）

本页描述当前代码及运行约束，不批准设计文档中的 Conditional/Deferred 项。V1 演示 Free 规则见下文，不代表最终商业套餐。v1 Wire 保持原样；v2 不支持时不得删除字段改调 v1，也不得把 authorized 失败请求转成 observation_only。

## 服务边界与实现

Backend `services/agent_entitlements/` 持有 policy、owner/plan assignment、Submission、窗口预留、不可变 Grant Revision、绑定回执、Permit、Inbox、追加账本与结算投影。Agent `control/metering.py` 持有执行世代、Intent、启动事实及追加观察；`control/usage_delivery.py` 投递独立 Usage Outbox。两库没有跨库 FK/查询。

Shared Contracts `canonical.py` 固定 UTF-8、递归键排序、毫秒 UTC、安全整数、显式 null，拒绝重复键、浮点和非规范化字节。`v2.py` 提供三类能力身份、UsageDelta/Batch/Ack、TaskMeteringBinding/Receipt、CallStartFact、PermissionSnapshot、WindowRef/Allocation、BudgetGrant、GrantBindingReceipt、CallPermitRequest/Response、TaskCloseManifest；`execution_v2.py` 是 Worker 本地封套。所有新模型拒绝额外字段，nullable 字段没有省略默认。v1 `wire.py` 未修改。

Grant/Receipt 使用 cryptography Ed25519、compact JWS，固定不同 typ、EdDSA 与 kid 白名单，校验签名原字节和规范化声明。签名外壳不参与 payload digest。初始 null Task payload 不回填；回执引用首次绑定的历史 Revision，后续 Revision 引用同一 Task/receipt。公钥文件由部署者维护 kid→PEM，轮换先发公钥后切私钥，历史验证公钥必须保留。私钥只在 Backend 本地环境引用。

## 调用边界

OpenAICompatProvider 每次 `_stream_once` 内真实发送前独立登记，包括外层重试和参数降级。底层 HTTP Transport 显式 retries=0；自定义 Transport 必须声明 `metering_no_hidden_retries=True`，MockTransport 仅用于测试。摘要通过相同 Provider，purpose=summary。累计 usage 帧不相加；部分最终帧保留下界证据并标 partial，回退冲突标 unknown。没有 usage 的失败、超时、取消不填零。

ToolRegistry 在 `execute_prepared` 登记，prepare/校验失败不登记。顺序和并行共享此边界。forced_skills 在装配注入前激活，read_skill 在正文/参考读取前激活；Control 对 Task＋精确 Skill 版本去重。Skill 的完整受控目录内容参与摘要；装载后资源发生变化时拒绝把旧正文标成新版本。Tool 身份包含稳定执行契约 `workspace_bounded_no_shell_v1`、参数 Schema 和非敏感配置修订；Model 固化 Provider、registry ID、upstream、能力/参数/路由修订、思考开关及 `openai_chat_completions_metered_v1` 协议契约。两者均不再绑定全量 Python 源码或依赖锁。改变安全边界或调用语义时必须更新契约/配置修订；普通实现修复无需重新批准能力。全量构建摘要保留在离线能力导出的顶层 `implementation_build_digest`，仅供追踪。Worker 部署代码、锁和受控资源必须只读，更新时排空旧任务或保留对应版本 Worker。

真实调用必须取得本进程首次 start 回执并在实际发送/执行前再检查截止；重复 start 只有 may_send=false。持久 start 与观察/Outbox 同一 Agent 事务，失败不能外调。Control HTTP 错误不会进入 Provider 的上游重试分支。网络发送与数据库不是原子操作；已发启动回执后崩溃保留 unknown，不承诺外部 Exactly Once。

## API（消息版本均为 1）

| 调用方 | 路径 | 用途 |
| --- | --- | --- |
| BFF/用户 | `POST /api/v2/agent/run` | 非 Session SSE 提交；必需 Idempotency-Key，owner 来自可信 BFF |
| BFF/用户 | `POST /api/v2/agent/submissions` | 独立 Task JSON 提交；与 SSE 入口使用不同路径 |
| BFF/用户 | `POST /api/v2/agent/sessions/{id}/run` | Session/Turn SSE 提交，稳定 Turn→Submission |
| BFF/用户 | `GET /api/v2/agent/sessions/{id}/run/stream` | 产品 SSE 续接与历史恢复 |
| BFF/用户 | `POST /api/v2/agent/run/{id}/stop`、`/steer` | 产品运行控制；V2 存量先查，明确 404 时才查历史 V1 Run |
| BFF/用户 | `GET /api/v2/agent/entitlements` | 当前 policy、权限快照、逐规则窗口/used/held/remaining |
| BFF/用户 | `GET /api/v2/agent/tasks/{id}/usage`、`/ledger` | 实测、估算、未知、预留/已用/释放、结算/对账和审计引用 |
| Gateway | `/internal/v2/tasks`、`/tasks/{id}`、`/tasks/{id}/runs`、`/submissions/{id}` | 提交、pending 绑定恢复及查询；submissions 不接受 obs: ID |
| Gateway | `/internal/v2/runs/{id}`、`/events`、`POST /steer`、`POST /tasks/{id}/cancel` | v2 生命周期 |
| Worker | `/internal/v2/worker/claim`、`POST /runs/{id}/heartbeat`、`/events`、`/report`、`GET /runs/{id}/controls` | 独立 v2 队列、execution 与 fencing |
| Worker | `POST /internal/v2/runs/{id}/call-intents`、`/calls/authorize` | 分别只接受已登记 observation_only/authorized 模式 |
| Worker | `POST /internal/v2/calls/{id}/start`、`/usage-observations` | 单次启动回执、历史执行世代补报 |
| 事实读取角色 | `GET /internal/v2/tasks/{task}/call-facts/{call}` | 只读持久启动事实，不授予发送权 |
| Control | `/api/v2/agent/internal/task-metering-bindings` | Backend 预建 profile 的唯一 Task 绑定；GET 原回执 |
| Control | `/api/v2/agent/internal/grants/{id}/bind`、`/authorization`、`/revisions/{revision}` | 根绑定、当前状态、历史签名原件 |
| Control | `/api/v2/agent/internal/call-permits`、`/{id}/start`、`GET /{id}`、`/{id}/void` | 许可、唯一在线启动及封闭证明 |
| Control | `POST /api/v2/agent/internal/call-permits/abandon` | 未取得 Permit 响应且从未产生本地 start operation 的永久封闭；与迟到 authorize 串行建立 tombstone |
| Control | `POST /api/v2/agent/internal/usage-deltas:batch`、`/grants/{id}/close` | 逐条持久 Ack、完整性核对及确定未用释放 |
| Gateway | `POST /internal/v2/grants/{id}/revisions`、`/revocations` | 追加已签修订和不可回退撤销 |
| 双方 | 各自 v2 `protocol-capabilities` | 只读协议发现，不决定 Task 模式 |

用户请求不能包含 grant、metering_context、owner 或 PermissionSnapshot。v2 模型参数要求精确 registry ID；本实现不在 Backend 重新实现 ModelRegistry。权限快照由批准静态配置提供，未实现 B 主线 Catalog、Manifest 管理、后台 UI 或健康探测。

`code` 保持整数；候选实现复用现有码 20004（已有业务错误保留原整数），另带 reason_code/retryable/request_id/retry_after_ms。常见 reason：IDEMPOTENCY_CONFLICT、QUOTA_EXHAUSTED、POLICY_NOT_APPROVED、GRANT_BINDING_CONFLICT、GRANT_REVISION_CONFLICT、GRANT_INACTIVE、TOKEN_BOUND_UNPROVEN、CAPABILITY_NOT_AUTHORIZED、LEASE_INACTIVE、START_DEADLINE_EXCEEDED、VOID_NOT_PROVEN、START_FACT_UNAVAILABLE、OBSERVATION_CHAIN_CONFLICT、USAGE_IDENTITY_CONFLICT。整数码专项分配仍待契约审查，未擅自占用号段。

## 事务、恢复与结算

Backend 所有权益写操作统一按 owner→grant→allocation/window 的锁顺序串行；多规则检查同事务失败整体回滚。并发 Submission 使用 owner 行锁与 `(owner,client_key)` 唯一约束；同键异请求冲突。服务只保存一份 Task 余额，不按 Run 复制。fixed/natural 窗口半开，Permit/start 截止取所有适用 end、Grant 和 Permit 的最早值，并保守扣除配置偏差；到点拒绝。跨窗口不自动扩额或搬余额，需显式授权修订/新提交。

滚动窗口按可信 start 的追加账本差额计算 used，所有未决 held 始终保留。Policy 明确 metric、unit、purpose、attempted/successful、窗口/时区、预留/调用上界、Token 范围和非收费规则。免费规则须显式声明 free，所有额度为零；原始调用成本仍保留。未获批准、test_only 或缺失 policy 的生产权益不能启用。

Backend start 与 revoke 使用同一根锁；撤销先提交则后续 start 拒绝。历史 start 回放不再赋予发送权。Agent 在远程返回后强制刷新加锁 Task/Run/Intent，避免 Session identity map 沿用旧 Lease。失租不妨碍已有 started 的完成补报，不能借此创建新的调用。未发本地回执的 Intent 可持久永久封闭后提交 void；Permit 响应丢失时 AbandonCall 建立原 call_id tombstone，迟到 authorize 不会重新占额度。原始 lease_token 仅留 Worker-Control 封套/Agent 数据库。

Worker 完成观察在持久目录先 fsync/原子 rename，再送 Control；响应丢失重试相同 observation_submission_id，重启先重放该目录。该目录需持久挂载、限制本机读权限，不属于可公开 Workspace 文件。Control 分配 revision/measurement/Task sequence；相同补报不增修订。Worker 崩溃早于完成观察落盘时仍有持久 started，保守 unknown。

完成观察已写入持久 spool 后，网络/服务端暂时性失败保留 spool 并记录日志，不覆盖已生成的回答；协议或权限拒绝仍停止。Control 已持久化观察和 Outbox 后，暂时性结算失败返回已入库观察，由 Usage Worker 继续投递。未确认调用继续占用 Backend 预留，不把 unknown 当零，不再因某一条完成回执阻塞同一用户的全部新任务；每次 Permit/start 仍在 owner 锁内检查额度，Outbox 容量上限保留。Worker Lease 为90秒，心跳仍每12秒，暂时性心跳失败允许下个周期再试一次；明确拒绝、取消、失租仍停止执行。

Usage Outbox 在网络前提交领取/退避时刻；回执按每项身份校验。accepted/duplicate durable 才 delivered；quarantined 保留独立待核验状态并重试，永久拒绝/超限进入 dead_letter。容量统计包括所有未解决项，达到配置上限阻止新调用。`python -m agent_app.usage_worker` 独立运行投递、失效执行恢复、封闭、void 及关闭清单重投，不能省略部署此进程。

网络故障导致重试耗尽时，在 Agent 目录执行 `uv run --env-file .env python -m agent_app.usage_worker --requeue-transient`，仅将没有永久拒绝回执的 dead_letter 返回待投递队列，然后退出。重复执行不重复处理已返回队列的项；原 ID、payload、Ack 和额度预留不变，操作记录到日志。已知永久拒绝不重排，需按原证据对账。用量批次失败、单条 Permit 恢复或 Grant 关闭失败分别记录日志，不再让该失败阻断后续恢复项。

Inbox 对 measurement、call/revision、Task sequence 唯一，保存原始观察；投影前从预配 Gateway 查询 CallStartFact，核验全部身份、能力摘要、启动摘要及 Permit。404、超时或冲突保持隔离。后续 revision 采用绝对值，账本只追加采纳差额。partial 保留下界和未决持有；estimated 不自动作为实测扣费；unknown 不记零。超额原值入账并阻止该 Grant 后续调用，不自动追扣现金。RunReport 只作结果展示，不二次结算。

TaskCloseManifest 核对 Permit/call、Run/execution、所有 sequence/revision、Ack 高水位、unknown 与执行封闭。缺项不释放。已证明未启动的 void 先回到 Task 预留，只有完整关闭和明确 `sealed_complete_only` 政策才释放确定未用余额；取消/失败不是退款证据。迟到更正可更新历史窗口，已关闭账本重新标记对账。查询按 owner/profile 锁取得一致投影，窗口不能相加。

## 部署和回滚

分别在 Backend、Agent 执行已有 Alembic `upgrade head`，当前版本为 Backend `028_formal_plans`（授权基础表始于 `027_agent_entitlements`）、Agent `0003_agent_metering`。迁移冻结建表定义，分别含 15 和 8 张新表；原 Task/Run/Session 表不加新协议字段。新增唯一约束、FK、状态/关联/投递索引随各库独立维护。生产连接隐藏 SQL 参数，避免日志包含租约/签名封套。

API/Worker/Backend 的角色 Token 必须互不相同，并与旧 AGENT_SERVICE_TOKEN 隔离。Backend 私钥/Agent 公钥文件、issuer/audience、Agent 的模型路由和工具非敏感配置修订、持久 spool、Usage Worker 的容量/退避/批量参数均需显式配置；见各 `.env.example`。`BACKEND_ENTITLEMENTS_URL` 是服务 origin，不能复用带 `/api/v2/agent` 的 Knowledge `BACKEND_INTERNAL_URL`。

Backend 默认 `AGENT_V2_ADMISSION=disabled`。A1 明确设置 observation_only 与 admission revision；A2 改 authorized 前停止旧 observation 新准入，已有 Task 模式不变、按原 ID 排空。正式 Agent 部署将 V1 新 Task 固定拒绝；V1 与 V2 Worker 仍以 `AGENT_WORKER_PROTOCOL=1/2` 分开排空，旧 Worker 不能领取、操作或序列化 V2 Task。V2 授权准入由 Backend `AGENT_V2_ADMISSION` 和签名 Grant 控制，不依赖 V1 admission。`AGENT_V1_ADMISSION=legacy` 只在隔离 Mock 演示环境启用，生产进程即使设置该值也不会恢复 V1 Task 准入。

本 Adapter 没有可信输入 tokenizer 上界验证器，任意 evidence_ref 字符串不被视为证明；没有批准的 model_risk_profile 时拒绝正式模型调用。批准风险策略不等于数学意义上保证真实消耗不超额。显式 max_model_tokens 的单 Run 限制仍沿用原 Worker 的执行前拒绝。

回滚先禁用新准入并停止新 claim，保留 v2 Control/事实查询/Inbox/Usage Worker，排空与对账，导出审计后才允许数据库 downgrade。不能删除 unknown、未投递 Outbox 或未结算预留来强行回滚；有存量时应保留 v2 接收服务。新迁移 downgrade 只删除自身表，Agent 原始 Task/Run 表保留。真实两库集成测试覆盖新迁移 up/down/up，但不代表生产历史数据可直接销毁。

运维使用 `python -m app.services.agent_entitlements.manage ACTION --file <reviewed.json>`：install-policy、assign、revoke、revise、recover-submission、reprocess-usage、adjust。安装/分配/修订须 operation_id/principal/approval_ref；人工调整须原因、证据引用、有效启动时间和幂等操作 ID。只追加审计/调整，不覆盖 Inbox。死信及冲突须保留证据并处理原 ID，不能改 payload 重投旧 measurement；生产审查须进一步确认数据留存、操作授权与告警接入。

## V1 正式套餐与 Admin

正式套餐为 basic/pro/research，上海自然日 Token 额度分别 200000/1000000/3000000，暂时免费，prompt_plus_completion。新用户待分配，initialize_free 与注册通知兼容入口不再写入权益；唯一业务分配入口是独立 Admin。历史 Free Policy、Grant 与用量记录保留，但不再作为注册默认值。历史初始化须在 Admin 按截止时间预览并确认，仅补缺失，不覆盖显式分配。

Admin 发布三档不可变 Policy，固定 daily quota_pool 跨 plan/revision，共享同日使用和预留。旧的上海日 daily-tokens 余额也纳入统一检查，不把多规则限额相加。发布指针位于迁移028新增的 agent_plan_releases；改变指针不改变既有 Assignment。

新 Policy 使用 per_call，初始 Grant allocation 预留为0，签名 execution_constraints 显式声明模式。Permit 在现有 owner→grant 锁内按需预留并写入原账本；实际 start 与计量安全门禁保留。无需追加 Grant 余额或重签任务，每个调用仍需 Permit。task_fixed 是历史默认，不改变已签历史任务语义。真实未启动封闭证明可归还 call-held；Unknown/Partial 和已启动失败继续沿原持有/对账机制。

正式套餐不再依赖固定 call_upper_bound。dynamic_model_budget=true 时，逐模型审批约束与请求预算进入 Permit，在 owner 锁内按输入风险预算、Registry已声明的模型上下文/输出及每日余额计算批准输出，并绑定 Provider max_tokens。risk_assessed_utf8_v1 测量完整正文 UTF-8 字节数；输入预留为 `ceil(input_bytes / input_bytes_per_token) + input_overhead_tokens`。逐模型 Policy 的 `input_bytes_per_token` 缺省为1，兼容历史算法；可显式选择2降低字节估算的过度预留。两者都是部署风险估算，不是严格 Token 证明，2对特殊文本可能低估，不能承诺真实消耗绝不超过估算；没有模型实测依据时保持1。余量只加一次，现有上下文压缩用的字符/4启发式不作为计费保证。真实用量按原幂等账本及时结算并释放多余预留，未知成本保留，超额记录并阻断后续调用；没有独立风险 profile 或对应模型约束时拒绝。若 Provider 无法确认 max_tokens 覆盖输出及思考 Token，则保持阻断。历史 Grant 保留原 call_upper_bound 语义及结算。重试、参数降级和摘要逐次重新授权；仍没有跨日自动续签或无限 TTL。

改变 Policy 时若有未关闭 Grant，拒绝 ACTIVE_GRANTS_REQUIRE_DRAIN；先排空任务，不自动把新权限塞进旧签名。停用拒绝后续 Permit/start，已启动调用继续按历史授权结算。Assignment、幂等 operation_id、原因与审批引用写入现有追加审计。

历史单次 overage 可通过受保护的 `POST /api/v1/admin-console/grants/{grant_id}/reconcile-close` 显式对账。请求包含 `operation_id`、`reason`、`evidence_ref` 和默认 `true` 的 `preview`；复用独立 Admin Session 与 `x-admin-request: 1` 同源校验。不增加自动关闭或套餐切换旁路。预览与执行使用不同 operation_id，同 ID/同请求回放原结果，异请求返回幂等冲突。

Backend 使用独立 Fact Reader 从 Agent 的只读 `/internal/v2/tasks/{task_id}/close-facts` 取得新快照，网络请求在账本锁外；在 owner→grant 锁内要求 active 历史 overage、任务 completed、30 秒内快照、已有对应完整 Manifest、所有观察序列/修订已核验、全部调用已结算、执行已封口且无可启动 Permit。继续核对最新 Inbox/Projection/采纳用量、allocation 和共享 window 的 held/used 追加账本；滚动窗口按原 trusted-start 规则重算使用量。任何不一致均拒绝，正常业务拒绝返回 HTTP 409 与具体 reason，记录成功/预览/拒绝审计及实时事实。事实服务不可用或协议失败保持关闭。

历史 assign 审计若以 `carried_window_usage` 保存了同一用户、同一自然日的 daily-tokens 结转，可将经验证的金额作为目标窗口已有使用基线：必须恰有一条结转记录，源/目标策略和窗口身份一致，held=0，源计数与源账本金额完全匹配，源 Grant 已关闭且调用/Manifest 当前仍完整结算，并且源账本在结转后未新增或变更。不支持推测补差、重复结转或链式结转。结果中的 `historical_carries` 保存源审计及账本引用，未来实际释放也记录该证据；不向目标 Usage 伪造一次新调用，不增加或减去结转金额。`preview=true` 时 `released` 仅表示拟释放金额，真实预留保持原值。

实际关闭仅将经证明的 task_held 追加为 released 账本并扣减当前持有计数，根状态改为 closed/settled；不改 Inbox、历史 UsageLedger、既有 Manifest、真实消耗和 overage 标记。该操作确认历史超额已对账，不减免用量、不增加额度、不修改套餐。部署时 Backend 与 Agent 须同时更新以提供新事实接口，无新增数据库迁移。

Deep Research 由正式 snapshot 中精确 skill:deep-research identity/digest 区分：Basic/Pro 不包含，Research 包含。Backend 提交检查强制 skills；Agent Control intent 对模型选择/forced 都核对签名权限，Worker 在 forced 注入前激活，read_skill 在正文/参考/脚本暴露前激活；Backend Permit/start 再校验。普通 Tool/Skill 规则免费但仍过授权与系统安全门禁。Web Deep Research 演示工作台没有因此变成生产研究执行入口。

正式版本生成、发布、Admin 操作、迁移与回滚及安全配置见 [Admin README](../../apps/admin/README.md#正式套餐与-admin-操作)。未提交真实风险审批时，模型权限保持拒绝，不伪造可用性。

## 部署时的能力同步与资源默认值

新生成的正式套餐 Grant/Permit/启动窗口为7200/120/30秒；已签历史 Grant 和旧 Policy 不修改。启动期限只限制实际发送前的开始动作，不是已开始模型调用的执行超时。快速模式运行300秒、工具预算20次；Deep/Idea/Doubt运行1800秒、工具预算150次；最大执行轮数60，已有上下文压缩不变。套餐每日额度仍为20万/100万/300万。

从旧的全源码身份首次升级，必须同步一次新的模型/工具摘要；不能仅按能力名称接受任意旧版本，因为历史签名只含摘要，无法证明配置兼容。技能身份算法不变，无需单独重注册。后续普通实现修改不会改变模型/工具授权；参数 Schema、路由、安全契约、技能内容等授权相关变更仍需同步。

升级顺序：停止新任务进入，保留旧 Worker/API/Usage Worker 完成任务和结算，排空并关闭旧 Grant；切换 Backend 与三个 Agent 进程到同一份新代码；用最终 Worker 环境导出，再经现有 Admin 发布/分配；恢复新任务进入。不对历史任务自动重签或修改其用量。若存在 unknown/overage，先用原有对账路径处理，不能直接清理账本或强制解除预留。保留旧公钥。

以下离线准备命令不写数据库、不调用模型，可重复生成同一发布包。先在 `apps/agent` 执行：

```powershell
uv run --env-file .env python -m agent_app.export_capabilities --output workspace/formal-capabilities.json
```

然后在 `apps/backend` 执行（`--previous-bundle` 指向之前实际使用的发布包；新修订号须未发布）：

```powershell
uv run --env-file .env python -m app.services.agent_entitlements.plans --capabilities ../agent/workspace/formal-capabilities.json --previous-bundle workspace/formal-plans-20261120.json --release 20261120-availability --output workspace/formal-plans-availability.json
```

这会复用现有逐模型预算与风险配置，不伪造审批。如果旧包的风险引用或逐模型预算为空，命令提前报错，不再生成到运行时才失败的包。`--model-budgets` 按模型ID合并覆盖旧配置；允许只配置要启用的模型，其余没有预算的模型仍拒绝调用。只有决定采用较宽松的输入估算时才追加 `--input-bytes-per-token 2`，并记录该风险参数的依据；不追加则保持原值。无旧发布包时继续使用原 `--model-budgets`、`--risk-profile` 参数。生成文件在现有 Admin「套餐管理」上传发布，再在「用户管理」预览并分配新修订；发布不自动迁移用户，也不重置当日余额。不需要数据库迁移或新增服务。

逐模型预算由部署负责人在本地审核文件中维护，通过 `--model-budgets <REVIEWED_MODEL_BUDGETS_JSON>` 合并到正式三档套餐；仓库不再内置 Free 演示 Policy 或某个 Provider 的固定预算 JSON。历史 Policy、task_fixed Grant 与消费记录继续按既有兼容逻辑读取和结算，不删除数据库记录。

开发环境可显式设置 `ENVIRONMENT=development` 与 `AGENT_ALLOW_TEST_POLICY=true` 使用已批准并已分配的 test_only Policy；不自动创建用户、分配权益或绕过认证。生产环境必须保持该开关为false；在非显式development环境开启会拒绝服务。开发联调也可直接复用上述正式发布包生成方式，使用现有 Admin 分配，不必建立第二套注册或授权流程。

## 测试入口

Agent 目录：`uv run --no-sync python -m pytest tests/test_a_line_persistence.py tests/unit/test_metering_boundaries.py ../../packages/agent-contracts/tests -q`。SQLite 两库事务与 HTTP/MockTransport 测试不证明 PostgreSQL 行锁或真实 Provider。

显式设置 `AGENT_A_LINE_TEST_DATABASE_URL`、`BACKEND_A_LINE_TEST_DATABASE_URL` 为两个不同本机 `shenzhi_a_line_*` PostgreSQL 库后运行 `uv run --no-sync python -m pytest tests/integration/test_a_line_postgres.py -q`。测试创建随机 `a_line_*` schema，实际执行两个新增迁移并只清理自身 schema，覆盖并发预留、同 Submission 竞争、撤销/start、Saga 旧缓存 Lease、void/tombstone、修订、投递、结算、关闭与迁移回滚。不连接生产 Provider；真实 Provider 另需批准环境和费用策略。
