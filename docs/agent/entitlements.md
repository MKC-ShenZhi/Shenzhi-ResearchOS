# 用户权益与执行权限（v2 候选实现）

本页描述当前代码及运行约束，不批准设计文档中的 Conditional/Deferred 项。V1 演示 Free 规则见下文，不代表最终商业套餐。v1 Wire 保持原样；v2 不支持时不得删除字段改调 v1，也不得把 authorized 失败请求转成 observation_only。

## 服务边界与实现

Backend `services/agent_entitlements/` 持有 policy、owner/plan assignment、Submission、窗口预留、不可变 Grant Revision、绑定回执、Permit、Inbox、追加账本与结算投影。Agent `control/metering.py` 持有执行世代、Intent、启动事实及追加观察；`control/usage_delivery.py` 投递独立 Usage Outbox。两库没有跨库 FK/查询。

Shared Contracts `canonical.py` 固定 UTF-8、递归键排序、毫秒 UTC、安全整数、显式 null，拒绝重复键、浮点和非规范化字节。`v2.py` 提供三类能力身份、UsageDelta/Batch/Ack、TaskMeteringBinding/Receipt、CallStartFact、PermissionSnapshot、WindowRef/Allocation、BudgetGrant、GrantBindingReceipt、CallPermitRequest/Response、TaskCloseManifest；`execution_v2.py` 是 Worker 本地封套。所有新模型拒绝额外字段，nullable 字段没有省略默认。v1 `wire.py` 未修改。

Grant/Receipt 使用 cryptography Ed25519、compact JWS，固定不同 typ、EdDSA 与 kid 白名单，校验签名原字节和规范化声明。签名外壳不参与 payload digest。初始 null Task payload 不回填；回执引用首次绑定的历史 Revision，后续 Revision 引用同一 Task/receipt。公钥文件由部署者维护 kid→PEM，轮换先发公钥后切私钥，历史验证公钥必须保留。私钥只在 Backend 本地环境引用。

## 调用边界

OpenAICompatProvider 每次 `_stream_once` 内真实发送前独立登记，包括外层重试和参数降级。底层 HTTP Transport 显式 retries=0；自定义 Transport 必须声明 `metering_no_hidden_retries=True`，MockTransport 仅用于测试。摘要通过相同 Provider，purpose=summary。累计 usage 帧不相加；部分最终帧保留下界证据并标 partial，回退冲突标 unknown。没有 usage 的失败、超时、取消不填零。

ToolRegistry 在 `execute_prepared` 登记，prepare/校验失败不登记。顺序和并行共享此边界。forced_skills 在装配注入前激活，read_skill 在正文/参考读取前激活；Control 对 Task＋精确 Skill 版本去重。Skill 的完整受控目录内容参与摘要；装载后资源发生变化时拒绝把旧正文标成新版本。Tool 的受控源码/依赖锁、参数 Schema 及非敏感配置发布引用形成身份；Model 固化 Provider、registry ID、upstream、能力/参数/路由修订及 Adapter 构建摘要。Worker 部署代码、锁和受控资源必须只读，更新时排空旧任务或保留对应版本 Worker。

真实调用必须取得本进程首次 start 回执并在实际发送/执行前再检查截止；重复 start 只有 may_send=false。持久 start 与观察/Outbox 同一 Agent 事务，失败不能外调。Control HTTP 错误不会进入 Provider 的上游重试分支。网络发送与数据库不是原子操作；已发启动回执后崩溃保留 unknown，不承诺外部 Exactly Once。

## API（消息版本均为 1）

| 调用方 | 路径 | 用途 |
| --- | --- | --- |
| BFF/用户 | `POST /api/v2/agent/run` | 非 Session 提交；必需 Idempotency-Key，owner 来自可信 BFF |
| BFF/用户 | `POST /api/v2/agent/sessions/{id}/run` | 复用原 Session/Turn 服务，稳定 Turn→Submission |
| BFF/用户 | `GET /api/v2/agent/sessions/{id}/run/stream` | 原 Task 及全部 Run 回放；每条 SSE data 含 schema_version |
| BFF/用户 | `POST /api/v2/agent/run/{id}/stop`、`/steer` | v2 owner 过滤的运行控制 |
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

Usage Outbox 在网络前提交领取/退避时刻；回执按每项身份校验。accepted/duplicate durable 才 delivered；quarantined 保留独立待核验状态并重试，永久拒绝/超限进入 dead_letter。容量统计包括所有未解决项，达到配置上限阻止新调用。`python -m agent_app.usage_worker` 独立运行投递、失效执行恢复、封闭、void 及关闭清单重投，不能省略部署此进程。

Inbox 对 measurement、call/revision、Task sequence 唯一，保存原始观察；投影前从预配 Gateway 查询 CallStartFact，核验全部身份、能力摘要、启动摘要及 Permit。404、超时或冲突保持隔离。后续 revision 采用绝对值，账本只追加采纳差额。partial 保留下界和未决持有；estimated 不自动作为实测扣费；unknown 不记零。超额原值入账并阻止该 Grant 后续调用，不自动追扣现金。RunReport 只作结果展示，不二次结算。

TaskCloseManifest 核对 Permit/call、Run/execution、所有 sequence/revision、Ack 高水位、unknown 与执行封闭。缺项不释放。已证明未启动的 void 先回到 Task 预留，只有完整关闭和明确 `sealed_complete_only` 政策才释放确定未用余额；取消/失败不是退款证据。迟到更正可更新历史窗口，已关闭账本重新标记对账。查询按 owner/profile 锁取得一致投影，窗口不能相加。

## 部署和回滚

分别在 Backend、Agent 执行已有 Alembic `upgrade head`，新增版本为 Backend `027_agent_entitlements`、Agent `0003_agent_metering`。迁移冻结建表定义，分别含 15 和 8 张新表；原 Task/Run/Session 表不加新协议字段。新增唯一约束、FK、状态/关联/投递索引随各库独立维护。生产连接隐藏 SQL 参数，避免日志包含租约/签名封套。

API/Worker/Backend 的角色 Token 必须互不相同，并与旧 AGENT_SERVICE_TOKEN 隔离。Backend 私钥/Agent 公钥文件、issuer/audience、Agent 的模型路由和工具非敏感配置修订、持久 spool、Usage Worker 的容量/退避/批量参数均需显式配置；见各 `.env.example`。`BACKEND_ENTITLEMENTS_URL` 是服务 origin，不能复用带 `/api/v1/agent` 的 Knowledge `BACKEND_INTERNAL_URL`。

Backend 默认 `AGENT_V2_ADMISSION=disabled`。A1 明确设置 observation_only 与 admission revision；A2 改 authorized 前停止旧 observation 新准入，已有 Task 模式不变、按原 ID 排空。A2 同时设置 Agent `AGENT_V1_ADMISSION=drain_only`，新旧 Worker 以 `AGENT_WORKER_PROTOCOL=2/1` 分开；旧 Worker 不能领取、操作或序列化 v2 Task。示例保留 v1 默认值，仅在完成评审后显式切换。

本 Adapter 没有可信输入 tokenizer 上界验证器，任意 evidence_ref 字符串不被视为证明；没有批准的 model_risk_profile 时拒绝正式模型调用。批准风险策略不等于数学意义上保证真实消耗不超额。显式 max_model_tokens 的单 Run 限制仍沿用原 Worker 的执行前拒绝。

回滚先禁用新准入并停止新 claim，保留 v2 Control/事实查询/Inbox/Usage Worker，排空与对账，导出审计后才允许数据库 downgrade。不能删除 unknown、未投递 Outbox 或未结算预留来强行回滚；有存量时应保留 v2 接收服务。新迁移 downgrade 只删除自身表，Agent 原始 Task/Run 表保留。真实两库集成测试覆盖新迁移 up/down/up，但不代表生产历史数据可直接销毁。

运维使用 `python -m app.services.agent_entitlements.manage ACTION --file <reviewed.json>`：install-policy、assign、revoke、revise、recover-submission、reprocess-usage、adjust。安装/分配/修订须 operation_id/principal/approval_ref；人工调整须原因、证据引用、有效启动时间和幂等操作 ID。只追加审计/调整，不覆盖 Inbox。死信及冲突须保留证据并处理原 ID，不能改 payload 重投旧 measurement；生产审查须进一步确认数据留存、操作授权与告警接入。

## V1 Free 与只读管理员

Web `DATABASE_URL` 与 Backend `CHAT_DATABASE_URL` 在 V1 部署中连接同一个 `shenzhi` PostgreSQL 库，分别保留各自配置。Better Auth `"user"` 是唯一正式用户来源；Backend 以 `owner_id='user:' || id` 读取权益。Agent 持久库仍独立。

`SHENZHI_FREE_POLICY_REVISION` 指向已安装、approved 且非 test_only 的 Free Policy。注册后的 Better Auth 生命周期调用 Backend `POST /api/v1/identity/entitlements/initialize`，身份由服务端 BFF 凭据和真实 user ID 传递，不接受浏览器选择 owner。Backend 不可用或注册事务尚未可见时不破坏注册；首次正式权益访问及批量补齐修复缺失记录。使用 `INSERT … ON CONFLICT DO NOTHING`，不覆盖特殊套餐、禁用状态或人工分配；匿名身份不分配正式 Free。

用户批准的演示规则：revision `free-demo-v1-20261119`、plan `free`、上海自然日 200,000 Token、每 Task 预留 100,000、每次模型调用上界 16,000，计量 prompt＋completion 的 Provider 实测。Tool/Skill 使用显式零收费规则，不设调用次数限制。批准定义保存在 `apps/backend/app/data/agent_free_demo_policy.json`，由 Policy 生成/安装工具消费，运行时从数据库读取。Grant/Permit/Start 技术 TTL 分别为 3600/60/10 秒，时钟安全偏差 1000ms。

能力快照必须在**最终部署的 Worker 源码、锁文件和运行环境**生成。`python -m agent_app.export_capabilities --output workspace/free-capabilities.json` 复用公开模型目录、普通 Web Runtime（allow_shell=false）、工具/Skill 的真实 identity/digest，不调用 Provider 或工具。导出命令会创建一个空的、无用户数据的导出工作区。模型路由修订 `AGENT_MODEL_ROUTE_REVISION`、工具非敏感配置修订 `AGENT_TOOL_CONFIGURATION_RELEASE` 需要由部署者设置，API/Worker 配置必须一致。代码、资源或配置变动后身份会变化，需新的 Policy Revision；不得覆盖已签权限来绕过版本检查。

在 Backend 目录依次执行（使用正确服务环境的本地 `.env`）：

```powershell
uv run --env-file .env python -m app.services.agent_entitlements.free_policy --capabilities ../agent/workspace/free-capabilities.json --output workspace/free-demo-policy.json
uv run --env-file .env python -m app.services.agent_entitlements.manage install-policy --file workspace/free-demo-policy.json
uv run --env-file .env python -m app.services.agent_entitlements.defaults
```

生成器默认 `model_risk_profile=null`，**不会把 Free 数值批准当成模型风险批准**。已知没有可信输入 Token 上界验证器时，模型 Permit 继续返回 `TOKEN_BOUND_UNPROVEN`。只有部署负责人提供真实批准的风险配置和审查引用，才可在生成时传 `--risk-profile <APPROVED_PROFILE> --risk-approval-ref <APPROVAL_REF>`。此批准接受调用上界可能被真实消耗超过的风险，不是精确 Token 上界证明。不应为演示随意填写字符串。若已安装 null-risk 的不可变修订，后续风险变更应另建、审批并安装新修订，显式管理分配，不覆盖现存记录。

安装前核验生成 JSON。既有 install-policy 对重复 revision 保持不可变拒绝；批量 defaults 可反复执行，且只补缺失用户。部署后先补齐历史用户，再开放注册/流量；注册补偿日志 `auth.entitlement_initialization_pending` 表示需修复，不表示成功分配。

模型完成观察在 Agent 事务提交事实和 Outbox 后，沿原 `usage-deltas:batch` 同步投递原 measurement_id 及该 Task 尚未确认的前序观察；Backend 核验持久启动事实并提交结算，Agent 校验逐项 durable Ack 后才确认观察。已确认历史不重复全量重放，避免长任务投递成本累积。失败保留原 Outbox/Worker spool，后续新增调用在用户范围的已完成但未确认观察存在时拒绝。该保护在 intent、prepare_start 和 commit_start 三处检查；不撤销已经发出的 HTTP 请求。独立 Usage Worker 继续负责投递、恢复和关闭，不能取消部署。

Backend Permit/Start 继续按 owner→grant 锁序检查 Grant overage，并再次检查其权益窗口 used＋held 是否超限，覆盖其他 Task 的迟到超额结算。新 Submission 保留原有 owner 级窗口原子预留。unknown 保留预留，partial 只入账已知下界并保留未决预留；不当作零。

现有 Web `/api/v1/agent/run` 与 Session run 在 Backend `AGENT_V2_ADMISSION=authorized` 且正式登录时选择 V2 Gateway，继续输出原 SSE；必须有 Idempotency-Key。浏览器不能选择准入模式。停止/插话按可信 run 查询识别 V2，只有只读 404 才查询历史 V1 run，不能将拒绝的提交退回 V1。Session 回放沿用持久 `_agent_protocol`。关闭 authorized 时原 V1 路径保持不变；匿名保持既有身份和准入约束，不自动分配 Free。

管理员配置仅为 Backend `SHENZHI_ADMIN_USER_IDS`（逗号分隔 Better Auth user ID，无 `user:` 前缀）。API 使用 `require_user`，先验证 BFF、再验证白名单；空白名单拒绝所有人。`GET /api/v1/admin/access` 供菜单发现，`GET /api/v1/admin/users?page=1&page_size=20&search=…&plan_id=…` 返回全站统计和分页明细；page_size 上限 100，plan_id=`__missing__` 查缺失权益。搜索仅用户名/邮箱，按大小写不敏感字面子串匹配。普通登录用户返回 403，匿名 401，不接受 admin 标记。

页面 `/admin/users` 在现有 AppShell 中显示统计、搜索、套餐筛选、分页、刷新和展开权益详情。数据经现有同源 BFF，无新用户表、同步系统或管理写接口。自然/固定窗口读取现有计数器，滚动窗口按相同 trusted-start 账本口径只读计算；used、held、remaining 分列，多个规则分别显示，未初始化/不可用 Policy 不伪装成零额度。数据标注 Backend 查询时间与近实时状态，不保证尚未上传的 Provider 消耗已结算。`model_calls_enabled` 只表示用户/Policy 的模型风险门禁配置齐备，不表示剩余额度充足、上游健康或所有单次调用均会获准。

## 测试入口

Agent 目录：`uv run --no-sync python -m pytest tests/test_a_line_persistence.py tests/unit/test_metering_boundaries.py ../../packages/agent-contracts/tests -q`。SQLite 两库事务与 HTTP/MockTransport 测试不证明 PostgreSQL 行锁或真实 Provider。

显式设置 `AGENT_A_LINE_TEST_DATABASE_URL`、`BACKEND_A_LINE_TEST_DATABASE_URL` 为两个不同本机 `shenzhi_a_line_*` PostgreSQL 库后运行 `uv run --no-sync python -m pytest tests/integration/test_a_line_postgres.py -q`。测试创建随机 `a_line_*` schema，实际执行两个新增迁移并只清理自身 schema，覆盖并发预留、同 Submission 竞争、撤销/start、Saga 旧缓存 Lease、void/tombstone、修订、投递、结算、关闭与迁移回滚。不连接生产 Provider；真实 Provider 另需批准环境和费用策略。
