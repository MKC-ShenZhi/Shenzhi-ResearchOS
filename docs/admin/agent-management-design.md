# ShenZhi Agent Management 详细技术设计

审查基线为 MKC-ShenZhi/Shenzhi-ResearchOS 的 dev 提交 `60188121277bdeb738f19e6e414d82e386533b6c`。本文中的 **现有** 指该提交可验证的行为，**Proposed** 指新增设计，**待核实** 指需要部署证据或产品决策的事项。路径链接以仓库为根解析，文末源代码索引注明基线行号。

## 1. 建设目标与范围

在 Admin Console 增加「Agent 管理」一级导航，覆盖运行总览、Provider 与 Model、Tools、Skills、Task 与 Run 五个模块。交付分为只读可见性、深入诊断及受控配置三期。Phase 3 为预留技术设计。本文不实施任何一期的产品代码、配置或迁移。

## 2. 原有 Admin 功能保护边界

保留总览、用户管理、原有能力管理、套餐预览与发布、用户套餐分配、权益停用与恢复、历史账号迁移、Token 计量与结算、原有操作审计及历史 Grant 对账。保留页面入口、同源会话、API 路径和契约、业务事务与幂等语义。原能力页继续通过 `GET /api/v1/admin-console/capabilities` 提供公开 Model/Skill 投影，该接口也是套餐发布在线检查所用的数据来源。新模块共享 Registry 源数据，使用独立管理投影和服务边界。[S1](#源代码索引) [S2](#源代码索引)

## 3. 整体架构 · Proposed

~~~mermaid
flowchart LR
  UI["Admin SPA"] -->|"同源管理 API + Cookie"| B["Backend Agent 管理模块"]
  B -->|"服务端管理读取 / 诊断凭据"| A["Agent API 管理投影"]
  B --> BA[("Backend 独立管理审计")]
  B -->|"只读获取授权及结算摘要"| E[("Backend 现有权益数据")]
  A --> R["API Registry / SkillStore"]
  A --> AD[("Agent 运行库及管理观测数据")]
  W["Worker 实例"] -->|"独立状态上报"| A
  W --> X["Runtime / Workspace"]
~~~

- **Admin** 负责导航、筛选、脱敏投影展示、用户确认和请求状态。复用 `App`、`api` 和 `useResource`。
- **Backend** 负责管理员身份、审计、管理契约、响应脱敏与聚合。通过 Agent 管理 Adapter 调用 Agent，只读聚合自身权益及结算摘要。跨库关联经明确的 Task/Grant 业务标识，分别保留各来源状态。
- **Agent** 负责 API、Worker、Registry、Store、Runtime、Workspace 和执行事实。Agent 管理服务输出允许列表 DTO。Worker 上报与 Run 租约分离。
- 浏览器请求仅抵达同源 Backend。内部管理读取、受控诊断、Worker 上报及未来发布使用不同权限的服务主体，沿用现有 v2 分角色校验模式，凭据由部署注入。[S1](#源代码索引) [S7](#源代码索引)

## 4. Admin 页面信息架构 · Proposed

| Hash 路由 | 页面与组件 | 主要交互 |
|---|---|---|
| `#/agent` | `AgentOverviewPage`、`ServiceHealthPanel`、`WorkerTable`、`RunSummary`、`AlertList` | 环境筛选、刷新、展开来源与采样时间，从异常跳 Worker 或 Run |
| `#/agent/providers`、`#/agent/providers/:id` | `ProvidersPage`、`ProviderDetail` | 查看真实 Provider ID、关联模型、状态、最近探测，Phase 2 发起诊断 |
| `#/agent/models`、`#/agent/models/:id` | `ModelsPage`、`ModelDetail` | 按 Provider 和状态过滤，查看能力、版本、默认用途、授权差异 |
| `#/agent/tools`、`#/agent/tools/:id` | `ToolsPage`、`ToolDetail` | 按组装场景与 Worker 过滤，查看 Schema、加载条件和最近使用 |
| `#/agent/skills`、`#/agent/skills/:name` | `SkillsPage`、`SkillDetail`、`SkillResourcePreview` | 查看版本、文件清单、静态检查和 Worker 覆盖 |
| `#/agent/tasks`、`#/agent/tasks/:id`、`#/agent/runs/:id` | `TasksPage`、`TaskDetail`、`RunDetail` | 筛选、翻页、追踪 Run、事件、调用与结算状态 |
| `#/agent/audit` | `AgentAuditPage` | Phase 2 查看本模块管理审计和诊断关联 |

新增前端 Feature 内的 `agentApi` 薄封装调用现有 `api`，集中处理命名空间、路径参数编码、过滤、游标和返回类型。基于读取来源显示加载、失败、空及过期状态。POST 禁止组件自动重试，人工重试沿用原操作 ID 与请求。Phase 1 仅挂载只读路径。配置表单和确认组件属 Phase 3。

## 5. 五个功能模块 · Proposed

### 5.1 Agent Overview

| 对象 | Phase 1 读取与展示 | Phase 2 增强 |
|---|---|---|
| API 实例 | 现有 API 健康仅证明所请求实例存活。展示已验证入口、响应时间、API 声明的 build revision；实例总数未知时标未知 | 配置允许列表中的实例级快照，逐实例区分 liveness 和 readiness |
| Worker | 从 Run 租约和 Execution 推导“近期有执行活动”，展示 Worker ID、最近观测、关联 Run；空闲 Worker 数未知 | 独立上报、配置和构建修订、实际能力清单、活跃 Run、健康结果 |
| Runtime | 展示已持久化 Run 状态、启动与结束信号，区分真实观测与组装模板 | Worker 报告 Runtime 自检以及按场景记录的实际加载能力 |
| PostgreSQL | 对明确的数据源做有超时的只读连通检查。Agent DB 与 Backend 权益 DB 分列 | 展示诊断采样时延及失败分类，结合独立观测区分 Agent API 故障和数据库故障 |
| Workspace | 对配置根目录做最小只读存在性及权限检查，仅返回结果，真实写入可用性保留未知 | Worker 自报挂载状态，必要时在独立诊断目录执行受控探测 |
| Task / Run 与告警 | 统计队列任务、执行中 Run、超时租约和时间窗内失败；报告统计窗口及数据时间 | 增加最近 Provider/工具失败、Worker 上报过期和配置漂移。告警含规则、目标、首次/最近发生和当前状态 |

聚合接口按子系统返回 `status`、`observed_at`、`source` 和 `reason_code`。后端可以区分单项失败与整体无数据。第一期告警由查询窗口内证据计算，不承诺历史告警留存。[S7](#源代码索引) [S8](#源代码索引)

### 5.2 Provider & Model Management

| 页面 | 数据与显示 |
|---|---|
| Provider | `provider_id`、协议类型、脱敏 Base URL、凭据存在、配置启用、关联 Model、最近探测和成功时间。地址只展示经部署批准的无敏感 URL 或脱敏地址，URL 路径可含部署信息时也脱敏。始终从真实 `ProviderSpec.id` 建关联。 |
| Model | `model_id`、`provider_id`、`upstream_model_id`、label、brand、能力规格、启用状态、按用途的默认标志、配置和能力修订、诊断结果。已有兼容字段 `provider` 表示品牌展示值。 |

**现有行为。** `load_registry` 读取内置 Catalog，合并环境派生定义、Provider URL 和 legacy alias，再合并 `AI_MODEL_REGISTRY_FILE`，显式默认值覆盖文件默认值。Provider 的凭据按 `api_key_env` 在当前进程解析，`ProviderConfig.configured` 同时要求配置启用和密钥非空。公开目录是 API 进程的投影。Worker 在每次组装 Runtime 时从自己环境解析并创建 Provider Registry；后续模型流从该实例解析模型。配置页与 Worker 实际部署应分别显示。[S3](#源代码索引) [S4](#源代码索引)

凭据存在、DNS/TLS 可达、上游鉴权成功、目标模型可用和 Tool Calling 均单列证据。探针见第 9 节。Phase 1 查看有效配置，Phase 2 诊断，Phase 3 才允许候选配置内修改。

### 5.3 Tools Management

列表和详情提供 Tool 名称、`tool:<name>`、描述、参数 Schema、来源、能力版本、Schema digest、组装条件、最近调用及诊断。来源枚举采用 `core | knowledge | workspace | skill_factory`，需要附上观测场景 `mode`、是否存在 Session/Workspace、Skill 集合签名及 build/config 修订。

- **基础或条件注册** 来自受控组装清单。Phase 1 可以发布无业务执行的静态描述或已有部署导出，标记覆盖场景和已知缺口。没有清单证据时返回未知。
- **Worker 已加载** 来自真实 Runtime 组装报告。**Run 可调用** 需要结合该 Run 的有效工具集、latent 状态以及相关调用门禁；历史调用仅证明曾使用。
- **Policy 授权** 用 `(capability_id, capability_version)` 对照指定 Policy，并保留用途和调用模式的限制。
- **最近调用** 从 Agent Call 元数据或受控运行事件得到，显示时间、状态及耗时。缺失结构化事实时保留未知。

当前 `build_runtime` 受 fast/deep、显式 Skill、Workspace 等上下文控制，`ToolRegistry` 区分注册和 latent。Tool 标识包含名称、参数 Schema 摘要、固定执行契约摘要及配置修订。完整构建摘要独立存在。读取接口不得为取得目录而新建用户 Workspace 或执行 Tool；独立检查采用第 9 节 Health Handler。[S5](#源代码索引) [S6](#源代码索引)

### 5.4 Skills Management

列表及详情展示名称、说明、来源（内置/vendor）、受控资源 digest、Worker 部署覆盖、加载、激活、可执行和依赖检查。详情列出 `SKILL.md`、references、scripts 的逻辑名、类型、大小和 digest。Phase 1 可预览经脱敏的 `SKILL.md`，references 和 scripts 默认展示清单。未来如需要读取受限正文，使用独立审计诊断，不接受任意路径。渲染 Markdown 时禁止原始 HTML、远程资源及可执行链接。

区分发现文件、Store 接纳、Runtime 加载、目标 Worker 部署、Run 激活、脚本/工厂具备执行资格和依赖检查成功。来源分别为发现报告、Store、Worker 上报、Call/Activation 事实及专用静态检查。现有 SkillStore 以文件元数据签名缓存，资源身份另按目录内容散列并在激活时核对。文件元数据相同或只修改引用资料时，缓存可能未更新。使用不可变资源产物。受控加载验证仅在隔离的候选 Worker 上对已审阅第一方工厂进行，普通 GET 与健康探针均不执行任意脚本。[S5](#源代码索引) [S6](#源代码索引)

### 5.5 Task / Run Monitoring

| 页面 | 数据契约 |
|---|---|
| Task 列表 | Task ID、用户 ID、模式、请求指定的模型、状态、创建时间、最近 Run、最新稳定错误码。支持 task_id、run_id、user_id、worker_id、status、from/to、model_id、tool_id。 |
| Task 详情 | Task 状态/时间、Run 时间线、失败类别、分来源 Token 摘要。Task 列表筛选中的 Model 表示请求模型，实际模型调用以 Call 事实为准。 |
| Run 详情 | Run/Execution ID、attempt、Worker、开始/结束及耗时、事件和模型/Tool/Skill 调用列表；接管时同时显示各 Execution 归属。Call 含类型、能力 ID/版本、状态、耗时、脱敏错误和必要的计量摘要。 |

Agent `agent_tasks`、`agent_runs`、`agent_run_events`、`agent_executions`、`agent_calls` 为运行事实。用量分列 Agent 已观测与 Backend 已核验/入账/预留，明确 measured、partial、unknown、unsettled，未知为 null。Tool 筛选按真实 Call 记录匹配，不填推测值。优先精确 ID 与时间范围，使用 `EXISTS` 支持关联过滤，按查询计划决定新增索引。Event 只返回允许列表属性，例如 seq、类型、时间、稳定错误码和脱敏摘要。普通管理视图不返回完整 prompt、history、工具入参/回包、报告正文、授权信封、签名回执或全部 Workspace 文件路径。[S7](#源代码索引) [S8](#源代码索引) [S9](#源代码索引)

## 6. 统一能力状态模型 · Proposed

| 状态轴 | 成立证据 |
|---|---|
| Registered | Catalog、Store 或指定 Tool 组装清单中的稳定 ID |
| Configured | 对象有效配置通过静态检查。独立返回 `enabled`、`credential_present`，区分启用和配置完整 |
| Loaded | 指定 API/Worker/Run 的实例报告实际装载成功 |
| Deployed | 指定目标 Worker 的新鲜报告确认该 build/config/能力版本已生效 |
| Reachable | 指定观察位置的依赖连通性探测成功 |
| Healthy | 该对象定义的必需检查通过且未过期；网络、鉴权、实调及 Tool Calling 分项显示 |
| Authorized | 带 Policy revision 或 Grant 上下文的实际能力版本匹配，并标明用途/模式。是否能启动调用仍由现有 Permit 裁定 |

每轴 `state = yes | no | unknown | not_applicable`，另带 `freshness = fresh | stale | unknown`。检查记录 `CheckResult` 含 `check_id, target_kind, target_id, check_kind, mode, observed_at, received_at, source, worker_id?, build_revision?, config_revision?, capability_version?, status, reason_code?, last_success_at?, expires_at?`。`mode` 为 `static | passive | active`，`status` 为 `pass | fail | inconclusive | unsupported`。按目标、检查种类、版本和观察者关联历史。新 build、修订或能力版本使用新的证据键，旧检查只在历史区展示。没有证据返回未知。

## 7. API 设计 · Proposed

### 公共契约

Backend 前缀 `/api/v1/admin-console/agent`。读权限 `R` 为 `require_admin`。`W` 为 `require_admin_write`，用于主动探测和未来配置写操作。`D` 也使用写依赖和独立诊断审计，用于敏感诊断。继续使用 `{code:0,data:...}` 或 `{code,message}` 和 no-store。错误定位使用稳定枚举，避免回显原始上游错误或输入凭据。身份失效返回 401，权限 403，对象不存在 404，修订/幂等冲突 409，参数不合法 422，限频 429，依赖不可用 503。单项失败保留在组合响应子段中。探测受理响应 202，带可查询 ID。

列表统一 `{items,next_cursor,observed_at}`，默认 20 条、最多 100 条。时间有时区并以 UTC 传输。任务默认近 24 小时，建议初始最大查询窗口 31 天，容量验证后确定。游标不透明，绑定排序键、排序方向及筛选摘要。任务列表按 `created_at DESC, task_id DESC`；事件使用递增 seq，调用与审计按时间及稳定 ID。条目 Schema 使用第 5、6、8、10 节定义的字段组合，未知标 null 或状态枚举。

### Backend 管理 API

| Phase | 方法与路径（相对前缀） | 权限 | 请求 | 响应 | 数据来源 | 副作用 |
|---|---|---|---|---|---|---|
| 1 | GET `/overview` | R | `from?,to?` | `{api,workers,runtime,postgres,workspace,task_counts,alerts,observed_at}` | Agent 管理投影、Backend DB 只读检查 | 无业务写入 |
| 1–2 | GET `/workers`、`/workers/{worker_id}` | R | 列表 `status?,config_revision?,cursor?,limit?`；详情可选 `instance_id` | Worker 列表或详情，含快照和能力覆盖；P1 返回推导信息 | Agent Run/Execution、P2 上报记录 | 无 |
| 1 | GET `/providers`、`/models`、`/tools`、`/skills` 及各自 `/{id}` | R | 列表通用分页，`provider_id?,worker_id?,mode?,config_revision?` 按资源适用；详情可选 `policy_revision` 或 `run_id`，二者互斥 | 第 5 节条目、状态和 `checks`；有授权上下文时附独立匹配摘要 | Agent Registry/Store/清单；Backend 只读 Policy 或经过 Owner 关联验证的 Grant | 无 |
| 1 | GET `/skills/{name}/document` | R | `resource_digest` | `{name,resource_digest,render_safe_markdown,truncated}` | Agent 指定 Skill 已登记资源 | 无；只提供限长预览 |
| 1 | GET `/tasks` | R | 第 5.5 节筛选及游标 | 分页 Task 摘要 | Agent Task/Run/Execution/Call | 无 |
| 1 | GET `/tasks/{task_id}`、`/tasks/{task_id}/runs` | R | ID；Runs 使用游标 | Task 详情与 Token 摘要，或分页 Run 项 | Agent 运行事实，加 Backend 只读结算视图 | 无 |
| 1 | GET `/runs/{run_id}`、`/runs/{run_id}/events`、`/runs/{run_id}/calls` | R | ID、游标、`kind?`；Event 可用 `after_seq`，与 cursor 互斥 | Run 详情、脱敏 Event 或 Call 分页 | Agent 运行事实 | 无 |
| 2 | POST `/checks`；GET `/checks/{check_id}` | W / R | POST `{operation_id,reason,kind,target_id,profile,worker_id?,expected_config_revision}` | 受理或历史结果，`{check_id,state,results}` | Backend 诊断操作、Agent 有界探针 | POST 写独立审计并可进行网络探测 |
| 2 | POST `/diagnostics`；GET `/diagnostics/{id}` | D / D | POST `{operation_id,reason,target_kind,target_id,profile}` | `{id,state,summary,expires_at}`，受限字段 | Agent 脱敏诊断、Backend 审计 | 审计发起及受限结果读取；主动探测需专用 profile |
| 2 | GET `/audit`、`/audit/{operation_id}` | R | `action?,target_id?,from?,to?,cursor?,limit?` | 独立管理审计分页或详情 | Backend Agent 管理审计 | 无 |
| 3 | POST `/config/revisions`；GET `/config/revisions`、`/config/revisions/{revision}` | W / R | 写 `{operation_id,reason,base_revision,changes}`；读游标和状态 | 候选修订、脱敏差异和状态 | 独立配置存储 | POST 创建候选，未部署 |
| 3 | POST `/config/revisions/{revision}/validate` | W | `{operation_id,reason,expected_active_revision}` | 验证 ID、状态、阻断项与兼容性报告 | Backend 权益只读视图、Agent 候选校验 | 写验证及审计，可触发受限探测 |
| 3 | POST `/config/revisions/{revision}/activate`、`/config/revisions/{revision}/rollback` | W | `{operation_id,reason,approval_ref,expected_active_revision,validation_id}`；`rollback` 的 revision 是恢复目标 | `{operation_id,target_revision,state,blocking_reasons}` | Backend 发布操作、Agent 应用确认 | 配置激活/回退、独立审计 |

Phase 3 的 `changes` 使用 Provider/Model/Tool/Skill 专用白名单变更结构，接受安全引用及部署产物 ID。发布和回滚对 `expected_active_revision` 执行 CAS。候选状态和探针结果查询可通过已有修订详情及检查 ID 完成。

### Agent 内部 API

沿现有版本化风格，建议前缀 `/internal/v2/management`。`MR` 为 Backend 管理只读主体，`MD` 为 Backend 受控诊断主体，`WR` 为 Worker 上报主体，`MC` 为未来配置执行主体。Bearer 权限与现有 Gateway、Fact Reader、Control、Worker 执行角色隔离。请求响应使用版本化 `schema_version:1` DTO，失败用 HTTP 状态及稳定 `reason_code`。

| Phase | 方法与路径（相对前缀） | 权限 | 请求 | 响应 | 来源 | 副作用 |
|---|---|---|---|---|---|---|
| 1 | GET `/overview`、`/workers`、`/workers/{worker_id}` | MR | 时间窗、状态、分页；详情可带 instance_id | Agent 运维子段、带证据的 Worker 投影 | API 及运行表，P2 加 Worker 状态库 | 无 |
| 1 | GET `/providers`、`/models`、`/tools`、`/skills` 及各自 `/{id}`；GET `/skills/{name}/document` | MR | 游标、来源/上下文、可选 worker_id/config_revision；文档必带 digest | 脱敏定义、证据、能力身份或安全摘要 | Agent Registry/Store/部署清单 | 无 |
| 1 | GET `/tasks`、`/tasks/{id}`、`/tasks/{id}/runs` | MR | 受限过滤、ID 和分页 | Task/Run 脱敏投影 | Agent 运行表 | 无 |
| 1 | GET `/runs/{id}`、`/runs/{id}/events`、`/runs/{id}/calls` | MR | ID、分页、kind 或 after_seq | Execution、Event、Call 摘要 | Agent 运行与计量事实 | 无 |
| 2 | PUT `/worker-instances/{instance_id}/heartbeat` | WR | `WorkerReport` | `{accepted_seq,received_at,expires_at,want_manifest}` | Worker 采样 | 更新管理快照，与 Run 租约独立 |
| 2 | PUT `/worker-instances/{instance_id}/manifests/{digest}` | WR | `{report_seq,build_revision,config_revision,scope,capabilities}` | `{digest,accepted}` | Worker 实际组装或装载证据 | 幂等存储清单 |
| 2 | POST `/probe-jobs`、GET `/probe-jobs/{id}` | MD | `{operation_id,check_profile,target_id,worker_id?,expected_config_revision,deadline_at}` | `{id,state,results}` | 受控探针 | POST 可联网、写独立诊断状态 |
| 2 | POST `/diagnostics`、GET `/diagnostics/{id}` | MD | `{operation_id,target_kind,target_id,profile}` | `{id,state,summary,expires_at}` | 脱敏事实投影和允许的诊断任务 | 写诊断记录；有副作用的检查继续走 probe |
| 3 | POST `/config/candidates`、GET `/config/revisions/{revision}` | MC / MR | 写 `{operation_id,revision,artifact_ref,expected_active_revision}`；读 revision | `{revision,validation_state,issues,effective_workers}` | Agent 候选产物与 Worker 报告 | POST 加载隔离候选 |
| 3 | POST `/config/deployments`、GET `/config/deployments/{id}` | MC / MR | 写 `{operation_id,revision,expected_active_revision,rollout_mode,validation_id}` | `{id,state,desired_revision,effective_workers,blockers}` | 受控部署协调与 Worker 确认 | POST 调度配置变更；回滚使用同接口指定历史目标 |

既有产品按 Owner 的 Task/Run 查询、用量和 Fact Reader 接口继续使用原权限和响应。Phase 1 跨用户读取使用新的管理投影。跨库聚合以已验证 Task/Owner 关系对账，Backend 账本或 Agent 事实不可用时保留来源和不完整状态。[S7](#源代码索引) [S8](#源代码索引)

## 8. Worker 状态上报 · Proposed

`WorkerReport` 含 `worker_id, instance_id, report_seq, sampled_at, config_revision, build_revision, manifest_digest, active_runs, health_status, lifecycle`。`instance_id` 每次进程启动更换，避免复用 Worker ID 导致新旧心跳混淆。`active_runs` 为有限长度的 Run/Execution ID 引用加计数，显示时与 Agent 当前租约核对。`capabilities` 在独立清单上报中记录 ID、能力版本、类型、来源、组装条件和观察范围。包含真实加载和已知条件清单两类，当前 Run 状态单独报告。

1. Worker 启动并完成基础初始化时上报，空闲和执行中都以独立循环上报；配置、Runtime 或能力清单变化时加发。建议初值间隔 15 秒并抖动，45 秒进入 stale，90 秒无有效心跳视为 offline；阈值随部署容量验证。Agent 使用服务器接收时间判定有效期。
2. 以 `(instance_id,report_seq)` 防重放。相同序列且内容相同返回原确认；不同内容冲突，乱序不覆盖较新记录。绑定部署身份与实例声明，限制每次报告大小和速率。Agent 计算规范化 manifest digest 校验内容。`want_manifest` 让 Worker 在服务端缺快照时补发。
3. 按在线证据与自检分层展示 `online | stale | offline | unknown`，另显示 lifecycle、健康、build/config 及实际生效确认。Worker 发出 drain 状态由 Phase 3 调度落实。上报失败采用退避、只保留最新快照，不能影响 Run 心跳、结算或控制循环。
4. Phase 1 仅展示有事实的 Worker 和过期租约，空闲状态未知。Phase 2 的状态库采集独立于现有 `claim_run` 和 `heartbeat`。Phase 3 明确选择新增的可领取能力约束，在未验证前不依赖本状态库作调度判断。[S7](#源代码索引)

## 9. 健康检查 · Proposed

| 对象/级别 | 检查内容与边界 |
|---|---|
| 静态 | 配置 Schema、Registry 引用、默认值、Tool JSON Schema、Skill Frontmatter、受控资源文件/摘要及已声明依赖。检查依赖时仅查询可用元数据。 |
| 被动观测 | 从真实 Call 与 Run 提取成功率、延迟和稳定错误码，声明时间窗和样本量。被动成功只证明观测到的版本和上下文。 |
| Provider 连通性 | 经目标允许列表及部署 egress 策略执行受控 DNS/TLS/HTTP 检查，限制重定向和结果字段。单独显示连接成功及认证成功。 |
| Model 主动探测 | 使用固定诊断输入及指定 Model ID，验证真实模型回复。Tool Calling 只验证受控声明的返回格式，无实际工具执行。 |
| Tool | 每项可选登记无业务副作用 Health Handler，验证 Schema、依赖是否可访问。缺少受控检查时返回 unsupported 或未知。 |
| Skill | 默认只检查资源、Frontmatter、声明依赖和 digest。隔离候选环境受控加载仅针对经审阅工厂，不调用 Skill 脚本。 |

主动诊断采用独立服务身份和预算，与用户权益计量隔离。初始建议真实模型探测单目标并发 1、请求间隔至少 60 秒、单次总超时 10 秒、请求输出上限 128 Token；同时限制固定输入规模和部署级日预算。仅使用可约束输出的 Provider 及独立诊断凭据。调用失败或用量未知时，上报诊断开销和未知状态，不能把未知当作零。诊断结果绑定到实际执行 Worker 和配置修订，修订改变时旧结果失效。禁止用户输入任意 URL、凭据、诊断 prompt、工具参数或文件路径。预算、时限和限频阈值均为 Proposed 初值，需在 Phase 2 容量和供应商可计量性验证后确定。

## 10. 独立 Agent 管理审计 · Proposed

Backend 存储 `operation_id`（唯一）、`principal`（服务端从管理员会话导出）、`action`、`target_kind/id`、`before_revision`、`after_revision`、`reason`、`approval_ref?`、`request_digest`、`result_code`、`diagnostic_id?`、`created_at` 及受限结果摘要。记录 Provider/Model/Tool/Skill 变更、配置审批/验证/部署/回滚、人工主动探测和敏感诊断访问。常规轮询采用访问日志。`audit` 按操作者、动作及目标范围返回安全摘要，不回显完整模型消息、内部控制凭据或 Secret 引用细节。

先持久化管理操作与审计请求，再调用 Agent。以相同操作 ID 下发；网络超时时进入 `unknown` 或 `pending_reconcile`，查询 Agent 回执后补记结果，禁止为未知结果生成新操作 ID 自动再次执行。同 ID 与同主体/请求摘要返回原操作，冲突返回 409。追加阶段事件保留尝试、拒绝、部分成功、完成以及回退的时间顺序。旧 `agent_entitlement_audit` 与旧 `GET /audit` 保持原有查询、写入和重放契约。[S2](#源代码索引)

## 11. 配置版本与兼容性 · Proposed / Phase 3

~~~mermaid
flowchart LR
  D["候选修订"] --> S["静态校验"]
  S --> P["隔离探测"]
  P --> C["Policy / Grant / Worker 兼容性检查"]
  C --> A["审批与发布"]
  A --> W["Worker 生效确认"]
  W --> M["运行观察"]
  M --> R["回滚到已验证目标修订"]
~~~

1. **候选隔离。** 配置 revision 由规范化非敏感配置、构建和资源产物引用固定。候选在隔离 Worker 上加载，不能领取正式任务。凭据由部署密钥系统提供，修订记录仅保存受限的引用。Provider 路由语义改变必须更新非敏感路由 revision。Tool 行为变化应提升 Tool 配置修订，即使 Schema 一致。Skill 资源采用不可变目录。
2. **兼容性判定。** 静态验证后，在候选 Worker 探测环境与依赖。对照用户实际绑定的已发布 Policy、排队任务及未关闭 Grant 的模型和权限快照，比较能力 ID、版本、用途、模式和依赖。报告区分同版本可执行、需旧版本 Worker、需重新发布套餐和无法证明。保持旧授权元数据，未来 Provider/Model 默认值或 alias 变更不得改变已持久化的模型身份。
3. **并行模式。** 为新 Task 在准入前确定兼容执行配置，并在 Agent 侧独立保存执行修订约束与证据。不改现有 Grant 签名字段或 Policy 语义。新领取和租约接管查询必须在现有事务及锁顺序下加入兼容筛选，核验 Worker build/config、健康有效期和上下文能力；没有兼容 Worker 时保留队列并告警。v2 Task 没有新约束的存量记录只适用有明确证据的旧部署修订，否则采用排空路线。影子检查先验证选择一致性，再启用分流。
4. **排空模式。** 兼容调度上线前，涉及行为变化且无法证明兼容的发布先停止受影响新准入，保留旧 Worker 处理排队/在途任务及结算，核验未关闭 Grant、Outbox 和未决计量状态。无法排空时须明示阻断原因并暂停发布。普通配置变更不得通过强制关闭历史 Grant 腾出发布窗口。
5. **激活和确认。** 用 CAS 固定旧指针，经批准发布候选。分别记录 desired revision 和逐 Worker effective revision。仅健康且确认能力清单的 Worker 可进入可用集合。观察错误率、等待时间、接管拒绝和结算积压，超过经审批的阈值暂停后续分批。
6. **凭据轮换与紧急停用。** 能并行有效时先部署新凭据并确认探活，再撤旧凭据；旧凭据必须立刻撤销时记录存量调用可能受影响。紧急停用区分拒绝未来准入与阻止下一次调用，显式审批和审计；涉及权限撤销时使用既有受控权益/Grant 机制，Agent 管理不自行改写授权。已开始调用继续交付事实与结算。
7. **失败及回滚。** 以历史不可变修订为目标重新验证其 Worker、凭据及依赖，CAS 恢复 desired revision，等待生效确认。隔离无法应用配置的 Worker。已在新修订下准入的工作按对应修订保留兼容 Worker 或排空；禁止用回滚改写请求、能力快照或账本。跨服务失败保留状态并按第 10 节对账。

**现有限制。** Agent API 与 Worker 分别加载配置；活跃 Run 通常使用已构造的实例，但撤销凭据、上游停服或原地更新 Skill 资源仍能影响后续步骤。现有 claim/接管未筛选能力版本。Grant 和 Permit 的确切版本门禁可能让任务在接管后停止执行。按版本路由和管理审计均属新增能力。[S3](#源代码索引) [S4](#源代码索引) [S6](#源代码索引) [S7](#源代码索引) [S9](#源代码索引)

## 12. 与原有套餐体系的边界

Agent 管理可以读取能力和授权匹配状态，配置修订不会授予任何用户能力。原有不可变 Policy、发布指针、Owner、Grant、Permit、Token 预算、Usage Ledger、旧审计及 SQL 迁移保持原有所有权和规则。Model 启用、Tool/Skill 注册和运行健康均与授权分列。正式新增授权继续走 **受控 Worker 能力导出 → 审阅能力及风险 → 原 Admin 三档 Policy 发布 → 显式用户分配**。现有在线发布校验保留 Model/Skill 集合验证，离线包继续承担受控 Tool/能力版本证据。存在未关闭 Grant 时的现有 Policy 切换门禁保持。[S2](#源代码索引) [S6](#源代码索引) [S9](#源代码索引)

## 13. 数据模型变更建议 · Proposed

| Phase / 所有权 | 建议模型 | 键与用途 |
|---|---|---|
| 1 / Agent | 现有 Task、Run、Event、Execution、Call 的管理只读投影 | 先复用现有索引。对复合筛选建立查询计划及容量基线，确有瓶颈再单独设计增量索引 |
| 2 / Agent | `agent_management_worker_instances`、`agent_management_capability_manifests` | 实例 ID 唯一、状态序列单调；清单按 digest 去重并关联 build/config/观察范围 |
| 2 / Agent | `agent_management_probe_jobs`、`agent_management_check_results` | 以操作 ID 幂等受理，按目标/检查种类/配置及时间查询，保存最小证据及有效期 |
| 2 / Backend | `agent_management_operations`、`agent_management_audit_events` | 操作 ID 唯一；阶段事件按操作 ID 与序号关联，受控查询 |
| 3 / Backend 与 Agent | Backend 候选及发布操作记录；Agent 不可变配置修订、生效确认、任务执行约束 | 修订、部署和激活指针独立持久化。Task 约束存 Agent 侧，保持现有授权合同不变 |

Worker/探测记录采用有限留存并允许按部署负载调整，审计按组织策略保留。所有拟议表为新增，涉及数据保留、索引和迁移方案另行评审。无跨数据库外键。Phase 1 默认无新持久化，实例级探测不足时返回未知。

## 14. 安全性及故障处理

- 保留管理 Cookie、本地入口、写请求防护和 no-store。部署文档中的 SSH 隧道免密码是目标，固定基线只实现本地密码。上线前核验公网路径隔离、可信代理、Origin/Host 与跨站请求处理。
- Registry 读取、Skill 文档读取和主动检查均通过白名单 DTO；文件读取基于已登记资源 ID 和不可变 digest，对路径规范化、符号链接、最大长度、内容类型做边界校验。Provider 地址由受控配置解析并受部署 egress 约束。
- Agent 超时、DB 失败、Workspace 未就绪和 Worker 漂移分别返回稳定原因。Backend Adapter 为聚合分配总时限及单依赖时限，限流并避免请求雪崩。可返回标记过期的旧证据，操作权限与授权判断不可基于过期结果放行。
- 带用户 ID 的筛选仅给经过管理认证的请求。默认隐藏用户内容，诊断结果限制可见范围和有效期。跨服务日志和审计只用允许的结构化字段。
- 配置执行进入未知态时按操作 ID 查证，先保留现状，再由确定回执推进；保护旧 Worker、Run 心跳、用量 Outbox 和既有结算链路。[S1](#源代码索引) [S7](#源代码索引)

## 15. 分阶段实施路线

| 阶段 | 交付 | 进入下阶段条件 |
|---|---|---|
| Phase 1 · 只读 | 独立导航、总览、Provider/Model、Tool/Skill 清单、Task/Run/Call 脱敏视图、基础静态/被动健康 | 回归通过；无实例证据处正确展示未知；只读链路无业务写入 |
| Phase 2 · 深入诊断 | 独立 Worker 上报、实际加载清单、统一诊断、主动健康检查、修订差异和独立审计 | 上报/重放/过期验证；探测预算及审计可核验；Worker 与业务链路隔离 |
| Phase 3 · 受控配置 | 候选修订、兼容调度或受控排空、配置修改/启停、部署确认和回滚 | 本文只设计。生产开放前须通过存量任务、租约接管、故障回退及结算验证 |

## 16. 验收标准

| 范围 | 可验证结果 |
|---|---|
| 原有 Admin | 五个导航及套餐子流程可用。既有 API 响应快照、认证/CSRF、发布不可变、批量预览/执行/重放、权益恢复、迁移保护、对账和审计测试保持通过 |
| 原有数据 | 针对每个新增管理读取和主动诊断，对比 Policy、Release、Owner、Grant、Ledger、权益审计。无新增管理侧修改。Provider/Model 配置验收同样检查 |
| Phase 1 | 浏览器只访问 Backend；全部页面有加载/空/错误/过期态；API 目录与 Worker 证据分别标识；目录无密钥，Run DTO 无 prompt、授权信封或原始工具输出；筛选与游标稳定 |
| Phase 2 | 空闲 Worker 可见、退出过期、多实例并存、乱序和重复上报不会覆盖新事实；主动探测按目标限频、超时、预算并产生独立审计；无安全 Handler 时状态为 unsupported；旧权益审计列表无新管理事件 |
| Phase 3 | 验证旧模型 ID/旧 Tool/旧 Skill 在已排队、已运行和接管场景继续执行；不兼容 Worker 不能领取。验证凭据轮换、排空阻断、部分部署、回滚、缺少兼容 Worker 和存量用量持续结算 |

回归可沿用 `test_admin_console.py`、`test_admin_audit_accounts.py`、`test_formal_plans.py`、`test_a_line_persistence.py` 和 Agent Registry/配置/导出测试，增加隔离环境的页面、权限、状态上报、主动检查及兼容调度覆盖。需要数据库的验收使用专用测试库。本文只做技术设计与文档核验，未执行产品测试。

## 17. 技术风险及待确认事项

| 事项 | 风险或待确认条件 |
|---|---|
| 真实部署拓扑 | 待核实 Agent API 实例枚举方式、Worker 进程数量、配置发布渠道、实际公网代理和内部凭据隔离。 |
| 容量与留存 | 待核实 Task/Call/Event 规模、PostgreSQL 索引与运维查询延迟、心跳采样开销、审计及诊断保留期限。 |
| 探测费用与支持 | 待确定每部署诊断日预算、独立凭据可用性、Provider 对低成本探测与 Tool Calling 验证的支持。 |
| 历史数据不齐 | 历史任务可能缺少结构化 Call、Execution 或能力版本证据。以数据来源和未知状态呈现，避免从事件文本估算正式结算。 |
| 兼容 Worker 选择 | 评审 Task 约束持久化、Claim 事务锁序、旧任务迁移和版本并存窗口。当前领取机制缺少此能力。 |
| 文件与端点暴露 | 待确认部署允许展示的 Base URL 粒度、Skill 文档预览的内容范围及敏感诊断审批策略。 |
| 停用与回退可行性 | 上游退役、密钥强制撤销或产物缺失会阻断旧版本执行。发布审批应明确可回退目标和存量中断条件。 |

## 源代码索引

| 编号 | 基线文件与关键位置 |
|---|---|
| S1 | [Admin App](../../apps/admin/src/main.tsx) `App:9–15`；[Admin API](../../apps/admin/src/api.ts) `api:4–15`；[Backend 管理认证](../../apps/backend/app/core/admin_auth.py) `settings:14`、`require_admin:53`、`require_admin_write:68`；[部署约定](../engineering/deployment.md) Admin 入口一节。 |
| S2 | [Admin 路由](../../apps/backend/app/api/admin_console.py) `capabilities:43`、`publish_plans:60`、`assign_plans:67`、`audit:89`；[权益 Admin 服务](../../apps/backend/app/services/agent_entitlements/admin.py) `list_audit:12`、`replay:47`、`publish:87`、`change_one:130`、`assign:174`。 |
| S3 | [Registry](../../apps/agent/src/agent_app/integrations/llm/registry.py) `ProviderSpec:43`、`ProviderConfig:94`、`ModelRegistry:121`、`resolve_model:165`、`public_models:181`；[Catalog](../../apps/agent/src/agent_app/integrations/llm/catalog.json)；[Resolver](../../apps/agent/src/agent_app/integrations/llm/resolver.py) `load_registry:43`；[Agent Config](../../apps/agent/src/agent_app/api/routes.py) `agent_config:63`。 |
| S4 | [模型流](../../apps/agent/src/agent_app/integrations/llm/agent_stream.py) Provider 构造及 Registry `211–231`、模型调用身份绑定 `329–340`；[Worker](../../apps/agent/src/agent_app/worker/host.py) `execute_claim:184`，组装及运行 `281–318`。 |
| S5 | [Tool Registry](../../apps/agent/src/agent_app/execution/tools.py) `ToolSpec:38`、`ToolRegistry:134`；[组合入口](../../apps/agent/src/agent_app/application/composition.py) `default_runtime:47`、`build_runtime:55`；[Runtime](../../apps/agent/src/agent_app/execution/runtime.py) Skill 工厂及 ToolRegistry `225–239`；[Skills](../../apps/agent/src/agent_app/extensions/skills.py) `_load_skill:100`、`SkillStore.load:156`、`tools:232`、`_content_signature:394`、`default_store:415`。 |
| S6 | [Execution Metering](../../apps/agent/src/agent_app/execution/metering.py) `controlled_resource_digest:32`、`implementation_digest:48`、`tool_identity:60`、`skill_identity:72`、`model_identity:81`；[导出](../../apps/agent/src/agent_app/export_capabilities.py) `export:18`；[Policy 构建](../../apps/backend/app/services/agent_entitlements/plans.py) `build:16`。 |
| S7 | [Agent API 入口](../../apps/agent/src/agent_app/main.py) `health:21`；[Agent v2](../../apps/agent/src/agent_app/api/v2.py) `role:48`、`protocols:88`、`submit:95`、`claim:199`、`run:301`、`events:310`、`heartbeat:334`；[Repository](../../apps/agent/src/agent_app/control/repository.py) `claim_run:163`、`heartbeat:212`；[Control Metering](../../apps/agent/src/agent_app/control/metering.py) `intent:89`。 |
| S8 | [Agent 运行模型](../../apps/agent/src/agent_app/infrastructure/models.py) `TaskRow:14`、`RunRow:33`、`RunEventRow:52`；[计量模型](../../apps/agent/src/agent_app/infrastructure/metering_models.py) `ExecutionRow:28`、`CallRow:39` 及用量观测/Outbox；[Workspace](../../apps/agent/src/agent_app/extensions/workspace.py) `WORKSPACE_ROOT:474`。 |
| S9 | [Backend Gateway](../../apps/backend/app/services/agent_gateway/v2.py) `submit:26`；[Entitlements](../../apps/backend/app/services/agent_entitlements/service.py) `authorize_submission:130`、`permit:284`、`start:447`；[结算](../../apps/backend/app/services/agent_entitlements/usage.py) `ingest:25`、`task_usage:268`；[权益模型](../../apps/backend/app/models/agent_entitlements.py) `EntitlementAuditRow:180`。 |
