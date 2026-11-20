# 正式套餐与 Admin 权益管理交付记录（2026-11-20）

## 交付范围

- Basic 200000 / Pro 1000000 / Research 3000000 Token，上海自然日，输入＋输出，暂时免费。
- 真实 Worker 导出生成三档不可变 Policy；同一受控 Model/Tool/Skill 集合，只有 Research 含 skill:deep-research。
- 新注册/首次访问不再自动获得 Free，兼容通知仅返回 initialized=0；正式用户新任务只走授权 Gateway，不会因准入配置回落未计量 v1。
- Admin 发布、预览、单用户/批量分配、停用恢复、历史缺失初始化、审计；Cookie+loopback 校验保留，写请求还需同源自定义 Header。
- 现有 Policy/Assignment/Grant/Permit/Usage Ledger/Audit 复用；不新建用户认证或业务后端。

## API

前缀 /api/v1/admin-console：GET /plans；POST /plans/publish；POST /entitlements/assign；POST /migration/preview；GET /audit。
契约、确认与重试规则见 apps/admin/README.md。assign 支持最多100个用户，逐用户保存点返回 success/failed，预览不写入，真实操作使用 operation_id 和追加审计去重。同 ID 异请求冲突；审批引用、操作者、前后计划/版本/启用状态及结果保存在审计 payload。

## 数据库与版本

028_formal_plans 只新增 agent_plan_releases，指向不可变 Policy，不修改历史账本。生成 release=20261120 时版本为 basic-v1-20261120、pro-v1-20261120、research-v1-20261120。未擅自发布真实 Policy、分配真实用户或填写风险批准；业务数据库未执行迁移，部署者须运行 alembic upgrade head 后在 Admin 发布。已建立两个本机专用 shenzhi_a_line_plans_* 测试库，测试仅在随机 a_line_* schema 中执行。

回滚先停止新准入、排空并结算 per_call 任务，保留接收/核验用量的服务。028 downgrade 只删发布指针；不能删除历史 Policy、审计或未知用量。不要在存量 per_call 任务中直接回退预算代码。

## 预算与权限边界

- 签名 Grant 的 execution_constraints 标明 per_call，allocation 身份固定、初始预留为0；每次 Permit 在 owner→grant 锁内从当天共享余额原子预留并写入原 Ledger，不靠 Grant Revision 伪造续额。
- reservation_units 不再成为任务累计上限。所有套餐共用独立审批的部署 call_upper_bound，仍满足原 Rule 约束；没有将三个数都设成每日额度。单任务可在当前自然日、Grant TTL 内持续取得 Permit。
- measured 结算释放已证明未用部分；Partial 保留下界及剩余持有，Unknown/缺失 Usage/无证据失败不退款。未启动调用须持久封闭证明才能 void，崩溃恢复/追加账本沿用原实现。
- quota_pool=formal-daily-tokens-v1 将跨套餐/版本的同日用量放进同一窗口，旧的同日 daily-tokens 债务也计算在内，不合并不同规则限额。
- Policy 切换遇未关闭 Grant 返回 ACTIVE_GRANTS_REQUIRE_DRAIN，已签授权不原地替换；停用禁止新 Permit/start，已启动调用继续结算，恢复不清零。
- Deep Research：Backend 强制 skills 提交检查；Agent Control 对精确 Skill identity/digest 的 intent/PermissionSnapshot 检查；Worker forced 注入前激活；read_skill 正文/参考读取前激活；Backend Permit/start 再检查。现有 Web 专用页仍为演示，没有声称完整研究产品已上线。

## 实际验证

- 现有 Agent 双库持久化、计量边界和共享协议测试：55 passed，19 subtests passed。
- 新增正式套餐 SQLite 双库测试：10 passed（分配/预览/幂等、注册不自动分配、模型风险门禁、Deep Research、连续调用与 Unknown、Partial、切换/停用/恢复、余额/历史债务及不可变发布）。
- Backend Admin API：10 tests OK；Agent 产品 API：14 tests OK；权益 Policy 单元：6 tests OK。
- Web pnpm typecheck：通过。
- Admin pnpm typecheck / pnpm build：通过。
- 按用户节省额度的补充要求停止较大的 PostgreSQL 回归（未报告其整体通过）；保留直接相关的两项：2 passed，9 deselected。涵盖真实 PostgreSQL owner 行锁多任务并发、切换保留用量，且各自初始化都执行028 up/down/up。
- git diff --check：通过（仅已有 LF/CRLF 提示）。
- 本次新增的控制台写操作未另做完整浏览器自动化；接口/服务/数据库链路已实际测试。无真实 Provider 调用和费用消耗。

## 明确限制与上线条件

没有可信 Token 上界验证器，因此仍依赖真实批准的模型风险 profile/引用及统一调用上界；预算不足以装下已批准上界时会提前拒绝，即使某次调用实际可能更小。未实现自适应 bound、跨日自动续签/自动延长 Grant TTL，不声称无限调用。Tool build 摘要的在线验证接口尚不存在，须在最终部署 Worker 离线导出并由管理员审批；运行配置接口只核对公开 Model/Skill 集合。历史用户初始化仅补缺失，已有 Free/特殊/禁用用户须显式选择调整，不自动覆盖。

上线前：迁移028；最终 Worker 重新导出身份（本次 Agent 源码变更会改变 Model/Tool 摘要）；发布审批后的三档版本；核对签名 key/历史公钥、隔离角色 Token、authorized 与 v1 drain_only、真实模型风险批准、Usage Worker 与持久 spool。Admin 仍只允许本机，远程部署必须另行实现强认证，不能关闭 local-only。

## 实际修改文件

- `apps/admin/README.md`
- `apps/admin/src/api.ts`
- `apps/admin/src/features/AssignmentEditor.tsx`
- `apps/admin/src/features/PlansPage.tsx`
- `apps/admin/src/features/UsersPage.tsx`
- `apps/admin/src/main.tsx`
- `apps/admin/src/style.css`
- `apps/admin/src/types.ts`
- `apps/agent/src/agent_app/control/metering.py`
- `apps/agent/src/agent_app/execution/metering.py`
- `apps/agent/src/agent_app/worker/host.py`
- `apps/agent/tests/integration/test_a_line_postgres.py`
- `apps/agent/tests/integration/test_formal_plans_postgres.py`
- `apps/agent/tests/test_a_line_persistence.py`
- `apps/agent/tests/test_formal_plans.py`
- `apps/backend/.env.example`
- `apps/backend/app/api/admin_console.py`
- `apps/backend/app/api/agent.py`
- `apps/backend/app/api/agent_v2.py`
- `apps/backend/app/core/admin_auth.py`
- `apps/backend/app/models/agent_entitlements.py`
- `apps/backend/app/schemas/admin_plans.py`
- `apps/backend/app/services/admin_users.py`
- `apps/backend/app/services/agent_entitlements/admin.py`
- `apps/backend/app/services/agent_entitlements/defaults.py`
- `apps/backend/app/services/agent_entitlements/manage.py`
- `apps/backend/app/services/agent_entitlements/plans.py`
- `apps/backend/app/services/agent_entitlements/policy.py`
- `apps/backend/app/services/agent_entitlements/service.py`
- `apps/backend/app/services/agent_gateway/v2.py`
- `apps/backend/migrations/versions/028_formal_plans.py`
- `apps/backend/tests/test_admin_console.py`
- `apps/web/lib/auth/entitlements.ts`
- `docs/agent/entitlements.md`
- `docs/engineering/architecture-confirmation.md`
