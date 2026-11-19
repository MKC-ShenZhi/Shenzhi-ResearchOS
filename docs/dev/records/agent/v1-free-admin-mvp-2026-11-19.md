# V1 Free 权益与管理员只读控制台交付记录

日期：2026-11-19。范围：Free 默认权益、Token 硬阻断、只读用户控制台。不含订阅有效期、商业付费、充值退款或管理写操作。

## 工程状态与保护

- 当前分支 `feat/agent-m0-integration`，HEAD `0bad958bafea308f6742a67c242fc403112450f9`；在线只读核验同名远程分支提交一致，无需切换分支。
- 开始时已有三份未跟踪文档：`a-line-development-handoff-2026-11-19.md`、`agent-management-contract-design.md`、`agent-management-readiness.md`。保留原状，没有覆盖、清理、暂存或提交。
- 没有修改远程配置、依赖或锁文件，没有修改历史 Migration，没有提交个人配置、连接字符串或密钥。

## 已完成（代码与隔离环境验收）

### Token 硬阻断

保留原 Permit、Start、UsageSettlement、Owner 行锁、Grant overage、窗口/账本和持久 Outbox。完成观察提交后，同步投递原 measurement_id 与前序观察，Backend 确认持久结算后才返回成功。响应缺失、隔离或身份不匹配不能假装确认；仍由原 Outbox/Worker spool 重试。

用户范围有已完成但未确认的观察时，Agent 的 intent、prepare_start、commit_start 拒绝新增调用；不取消已发出的模型请求。Backend Permit 和 Start 重新检查同一 owner 的窗口 used＋held，避免另一 Task 已签 Grant/Permit 绕过迟到结算的超额。Submission 继续原子预留。Unknown 不入零值，Partial 只采纳已知下界并保留未决预留。

### Free 默认权益

用户已明确批准：`free-demo-v1-20261119` / `free`，上海自然日 200,000 Token、Task 预留 100,000、调用上界 16,000、prompt＋completion Provider 实测。它是 V1 演示标准，不是最终商业标准。

提供离线真实能力导出与 Free Policy 生成器；公开模型、普通 Web Runtime 工具与公开 Skills 生成真实 identity/digest，不开放 Shell，不执行模型/工具。Tools/Skills 显式 free accounting，无额外次数上限。默认 risk_profile 为 null，未伪造风险批准。

Better Auth 创建用户后调用可信 Backend 初始化；创建真实 `OwnerEntitlementRow`，Owner 为 `user:<id>`。Backend 不可用/注册事务尚未可见不破坏注册，记录待补齐；首次正式权益访问和批处理可修复。批处理和并发初始化使用 ON CONFLICT DO NOTHING，不覆盖已有套餐、人工分配和禁用状态，不处理匿名用户。

### 管理员只读控制台

Backend 直接用既有 SQLAlchemy 连接读取共享库 `"user"`，按 owner 关联权益；无重复用户表或同步系统。服务端先校验 BFF/真实登录 ID，再校验 `SHENZHI_ADMIN_USER_IDS`。普通用户 403，匿名 401，浏览器 admin 标记无效。

`/admin/users` 复用 AppShell、Button、Input、React Query 与现有 BFF，支持全站统计、用户名/邮箱搜索、套餐筛选、分页、刷新、展开单用户权益。多条规则分别显示，used/held/remaining 分列；展示近实时查询时间、Partial 下界说明和未初始化/不可用状态。菜单由可信管理员 access API 决定，服务端权限校验独立存在。账号切换按 user ID 隔离缓存。

### 现有 Web 入口接入

发现原 Web 入口只会提交 V1；开启 authorized 会拒绝产品所有新任务。因此补充窄范围 Backend 路由选择：正式登录用户＋服务端 authorized 时，现有 run/Session run 进入 V2 Gateway，保留原 SSE。Stateless Web 请求新增 Idempotency-Key；Session 原有幂等键继续保留。停止/插话兼容 V2 与排空中的历史 V1；只有只读 run 查询的 404 才查询旧协议，提交/授权失败绝不降级。其余 V1 行为回归通过。

## API

| 路径 | 变化 | 权限 |
| --- | --- | --- |
| `GET /api/v1/admin/access` | 新增，只读菜单发现，返回 read_only | 管理员 |
| `GET /api/v1/admin/users` | 新增，page/page_size/search/plan_id；返回 stats/items/windows/plans/updated_at | 管理员 |
| `POST /api/v1/identity/entitlements/initialize` | 新增，当前可信用户幂等 Free 初始化，无 owner 请求体 | BFF 验证的正式用户 |
| `POST /api/v1/agent/run`、`/sessions/{id}/run` | authorized 模式复用 V2；保留原 SSE；authorized 必须幂等键 | 既有 BFF 身份 |
| `POST /api/v1/agent/run/{id}/stop`、`/steer` | 兼容 V2 与历史 V1 运行 | 既有 owner 检查 |
| `POST /internal/v2/usage-observations` | 保留请求/响应结构，authorized 完成观察增加同步结算确认 | Worker 角色 |

其余 Call Permit、UsageBatch、签名 Grant、V1 Wire 保持原契约。管理员 page_size 为 1–100，默认 20；`plan_id=__missing__` 查询未初始化用户。搜索为大小写不敏感的字面子串，已转义 `%`/`_`。管理响应不缓存。数据定义见 `apps/backend/app/schemas/admin.py`。

## 数据库与配置

本次没有新增 Migration 或表。Backend 需应用已有迁移至 `027_agent_entitlements`，Agent 至 `0003_agent_metering`；测试验证 up/down/up。业务部署回滚必须先排空和导出审计，不能直接删除权益/用量事实。

新增 Backend 环境变量：

```dotenv
SHENZHI_ADMIN_USER_IDS=<BETTER_AUTH_USER_ID>,<ANOTHER_USER_ID>
SHENZHI_FREE_POLICY_REVISION=free-demo-v1-20261119
```

白名单为实际 Better Auth ID，不带 `user:`。Web `DATABASE_URL` 与 Backend `CHAT_DATABASE_URL` 必须指向相同 `shenzhi` PostgreSQL 数据库，各自保留变量；Agent 数据库独立。其余 issuer/audience、角色凭据、密钥、路由/工具修订、spool、Outbox 参数沿用现有配置，不新增旁路。

## Free 安装与历史补齐

先冻结最终 Worker 构建与配置，设置真实的 `AGENT_MODEL_ROUTE_REVISION`、`AGENT_TOOL_CONFIGURATION_RELEASE`。在 Agent 服务环境执行：

```powershell
uv run --env-file .env python -m agent_app.export_capabilities --output workspace/free-capabilities.json
```

在 Backend 服务环境执行：

```powershell
uv run --env-file .env python -m app.services.agent_entitlements.free_policy --capabilities ../agent/workspace/free-capabilities.json --output workspace/free-demo-policy.json
uv run --env-file .env python -m app.services.agent_entitlements.manage install-policy --file workspace/free-demo-policy.json
uv run --env-file .env python -m app.services.agent_entitlements.defaults
```

路径按实际跨服务文件传递方式调整；导出和 Policy 文件放受控本地位置，不提交密钥或环境文件。安装前审查生成文件和真实运行时能力。install-policy 保留修订不可变约束，重复安装同 revision 会拒绝；defaults 可以重复运行，且只补缺失权益。正式注册成功后默认分配；初始化失败有待补齐日志和首次使用补偿，不能声称分布式注册与 Backend 分配绝对原子。

没有单独风险审批时，生成器保持 `model_risk_profile=null`，Permit 拒绝模型调用。已有真实批准的风险配置时才传 `--risk-profile <APPROVED_PROFILE> --risk-approval-ref <APPROVAL_REF>`；不得为演示随意填写。已安装的修订不可修改；后续变更按新 Policy Revision 的审批/显式分配流程执行，补齐命令不会自动覆盖老权益。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| Backend 权益、V1 API、Session、身份回归 | 40 tests 通过 |
| SQLite 双库、Mock Provider HTTP、计量边界、Shared Contracts | 55 tests＋19 subtests 通过 |
| 实际产品 Runtime 离线能力导出 | 1 test 通过；无网络调用，身份摘要正确，无 Shell |
| PostgreSQL 双独立测试库 | 36 个不同测试通过（完整 33＋后增 3），管理员/Free 最终变更另作定向复核 |
| Web 全量测试 | 443 tests 通过 |
| Web TypeScript、改动文件 ESLint | 通过 |
| Next.js 生产构建 | 通过，包含 `/admin/users` |
| Git diff whitespace | 通过 |

端到端测试运行两个 FastAPI ASGI 服务、两个真实独立 SQL 库及实际 OpenAICompatProvider MockTransport 请求：提交/预留→绑定/claim→Permit/Start→Provider 返回超额 usage→同步结算→当前结果成功→下一 Provider 请求未发出→新 Task 403。该测试不依赖先运行异步投递 Worker。另测 Backend 未确认不能放行、原 observation ID 重投不重复扣费、其他 Task 预签 Permit 的 Start 被超额拒绝、Unknown/Partial 不清零、并发预留不超配。

PostgreSQL 测试使用独立本机 `shenzhi_a_line_mvp_agent` / `shenzhi_a_line_mvp_backend`，每个测试单独随机 schema 并清理自身 schema。测试所需本地凭据仅留在忽略目录。没有连接真实 Provider，没有向业务库写入测试 Policy 或测试用户。没有完成真实浏览器登录后的管理页视觉验收。

## 未完成与正式启用阻塞

1. **没有在业务数据库安装 Free Policy 或批量补齐真实用户。** 本机共享 `shenzhi` 只读检查版本为 `024_knowledge_venue_snapshot`，有 Better Auth 用户表，但尚无权益表；需先应用已有迁移。没有擅自对该业务库执行迁移或数据修改。
2. **当前已检查的 M0 Agent 配置缺少 `AGENT_MODEL_ROUTE_REVISION`，无法导出正式能力快照。** 工具配置修订也需部署者提供；导出失败保持明确拒绝，没有用测试快照顶替。旧 M0 隔离服务端口当前不可达。
3. **仓库没有可信输入 Token 上界验证器，也没有发现正式批准的 model_risk_profile。** call_bounds 会从 Free Policy 传入 16,000，但它不是可信输入证明。生成器不虚构批准状态；Free 数值批准不解除模型调用门禁。
4. **尚未做真实 Provider / 最终部署环境 / 浏览器登录后的验收。** 测试证明隔离 SQL、HTTP 与 Mock Provider 链路，不证明真实上游 usage 完整性和部署健康。

## 明天演示前部署顺序

1. Web/Backend 对齐同一业务库，备份并应用既有 Backend/Agent Alembic head；核验 Better Auth 表与权益表同库。
2. 固定 Worker 构建和真实非敏感配置修订；完成单独模型风险审批。没有风险批准时只演示只读控制台/权益初始化和隔离 Mock 链路，不启用真实 authorized 模型调用。
3. 导出真实能力快照，审查、生成并安装批准的 Free Policy，设置 Free revision，执行历史补齐两次确认第二次零新增。
4. 设置真实管理员 ID 与匹配的 BFF secret；登录管理员访问 `/admin/users`，核验统计、搜索、分页、Free 明细；普通账号验证 403。
5. 启动 Backend、Agent API、V2 Worker 与独立 Usage Worker，挂载持久 spool；确认角色凭据互相隔离、签名公钥/issuer/audience 一致。
6. 排空旧协议任务并按已有方式设置 Backend `AGENT_V2_ADMISSION=authorized`、Agent `AGENT_V1_ADMISSION=drain_only`、Worker `AGENT_WORKER_PROTOCOL=2`；不要把失败请求降级为 observation_only/V1。
7. 最终环境进行注册→真实 OwnerEntitlementRow→受控任务→usage→管理页刷新验收；额度触发测试用独立低额度 Policy/测试库，不覆盖正式 Free 数值。确认未结算预留仍保留，结束演示后继续运行 Usage Worker。

## 修改文件清单

Agent：

- `apps/agent/src/agent_app/api/v2.py`
- `apps/agent/src/agent_app/control/metering.py`
- `apps/agent/src/agent_app/control/usage_delivery.py`
- `apps/agent/src/agent_app/export_capabilities.py`（新增）
- `apps/agent/tests/test_a_line_persistence.py`
- `apps/agent/tests/integration/test_a_line_postgres.py`
- `apps/agent/tests/unit/test_export_capabilities.py`（新增）

Backend：

- `apps/backend/.env.example`
- `apps/backend/app/main.py`
- `apps/backend/app/api/agent.py`
- `apps/backend/app/api/identity.py`
- `apps/backend/app/api/admin.py`（新增）
- `apps/backend/app/schemas/admin.py`（新增）
- `apps/backend/app/data/agent_free_demo_policy.json`（新增，版本化批准配置）
- `apps/backend/app/services/admin_users.py`（新增）
- `apps/backend/app/services/agent_entitlements/defaults.py`（新增）
- `apps/backend/app/services/agent_entitlements/free_policy.py`（新增）
- `apps/backend/app/services/agent_entitlements/service.py`
- `apps/backend/tests/test_agent_api.py`
- `apps/backend/tests/test_agent_entitlements.py`

Web：

- `apps/web/app/admin/users/page.tsx`（新增）
- `apps/web/features/admin/AdminUsersPage.tsx`（新增）
- `apps/web/clients/backend/admin.ts`（新增）
- `apps/web/clients/backend/agent.ts`
- `apps/web/components/common/layout/settings-menu.tsx`
- `apps/web/lib/auth/entitlements.ts`（新增）
- `apps/web/lib/auth/server.ts`
- `apps/web/tests/settings/settings-menu-navigation.test.ts`

文档：

- `docs/agent/entitlements.md`
- 本交付记录。
