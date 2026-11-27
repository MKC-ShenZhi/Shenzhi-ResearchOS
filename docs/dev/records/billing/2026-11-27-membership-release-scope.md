# 会员功能最小上线收口

日期：2026-11-27（Asia/Shanghai）。在原工作区继续修改，未调用子 Agent，未提交、推送、合并或操作生产数据库。

## 范围与行为

保留 Basic 免费、注册幂等初始化、Admin initialize_only 补齐、三档分配与高级套餐 1～12 自然月赠予、赠予用户自主同档续费、自然月购买／续费、按需到期回落。Basic 可购买任一高级套餐；有效高级权益只允许同档续费。停用、永久高级权益、未关闭 Grant 的安全保护保留。

移除新增 quote API、expected_quote 契约、前端报价请求与有效期倒计时；新订单不保存报价字段。普通购买／续费忽略旧 quote_expires_at。保留 owner_snapshot 防止付款期间覆盖权益调整。历史 action=upgrade 订单保留原数据，停止支付入口和自动履约；已支付的保留 paid/pending，人工处理。页面不再展示其继续支付入口。

自然月从上海时区计算、月末截断；首次购买从实际履约时间起算，续费从 max(履约时间, 原到期时间) 起算；旧 duration_days 订单继续原固定天数。续费固定原 Policy Revision，不清空 used/held。

到期回落持有 owner 行锁，不反向获取发布锁；跨 Revision 分配必须排空 Grant。授权、permit、start 拒绝过期高级权限；已启动用量仍可验证、入账及重复上报，真实关闭 Grant 后下次访问回落 Basic。Basic 未发布／未批准、异常权益、停用均不静默覆盖。

## 数据库与调用方

无新增表、迁移、依赖或服务。source 为 varchar(32)，无枚举限制；真实 PostgreSQL 测试已写入 registration/expiry。Admin 高级分配强制 duration_months=1..12，已检查现有调用方：AssignmentEditor、Backend SQL fixtures、Agent formal plans；Basic／disable／restore 不传期限。部署需同步 Web、Backend、Admin；旧高级分配调用方不传期限会收到 422。

## 本次验证

- Backend：uv run --no-sync python -m unittest tests.test_admin_membership tests.test_entitlement_lifecycle tests.test_billing_postgres tests.test_billing_membership tests.test_payment_providers tests.test_admin_console tests.test_agent_entitlements：65 tests，OK，无跳过。
- SQL 测试使用本次独立 PostgreSQL 16 临时容器、专用本机端口与 membership_test 库，每项使用随机 schema；未访问现有业务／生产库；测试完成后已校验专用标签并删除本轮临时容器，不操作现有服务或持久卷。覆盖注册并发、Admin 预览／覆盖／重放、Basic 购买、赠予续费、月末计算、旧订单、报价过期不影响普通付款、支付重复通知、金额／身份校验、生产禁用 Mock、Grant 排空、过期拒绝授权／permit／start、真实 Grant 关闭、已启动用量入账及重复上报、并发回落单次审计、used/held 保留。
- Agent：uv run --no-sync python -m pytest tests/test_formal_plans.py -q：13 passed；39 条 SQLite datetime 弃用警告。
- Web：类型检查通过；billing-state 与 checkout-dialog 定向测试 10 passed、0 skipped；相关三个文件 ESLint 通过；最终入口隔离后的生产构建亦通过。
- Admin：pnpm build 通过（含 TypeScript 检查）。git diff --check 通过。
- 初轮测试中的旧升级成功断言已改为拒绝升级；新增安全测试的窗口字段／计量绑定 fixture 已修正，未放松生产约束。并发注册发生在 checkout 后时，测试要求保留新 Basic 并进入 paid/pending；不会为通过测试绕过快照校验。
- 沙箱内 uv 缓存权限及 Next 构建受限；在正常本机权限下使用已有依赖重跑，未修改锁文件。未执行完整全仓测试或真实商户支付、浏览器视觉验收。

## 发布边界

代码验证通过不等于生产验收完成。当前 Pro/Research 仍为 2/3 分测试价；正式收款前必须审核价格及真实渠道配置。生产不能启用 Mock。未确认配置时使用 disabled 支付模式，可发布免费 Basic 与 Admin 赠予能力。

历史永久高级权益需管理员显式设置期限。付款期间 Admin 调整、注册补齐或到期回落导致 owner_snapshot 改变时，保留支付事实并进入 paid/pending；无自动补偿或退款。历史升级订单同样人工处理，不自动关闭／退款。

需在发布前核对现有数据库迁移版本、正式套餐发布／模型授权批准、服务器 SSH 与管理入口隔离、支付通知链路、备份及回退预案。本轮未执行部署或生产迁移。

## 当前工作区文件清单

以下包含用户原有改动及本轮收口，不表示全部由本轮新增。新增报价 API/schema 在收口后与 HEAD 一致，因此不在 Git diff 清单内。

- `apps/admin/README.md`
- `apps/admin/src/features/AssignmentEditor.tsx`
- `apps/admin/src/features/PlansPage.tsx`
- `apps/admin/src/features/UsersPage.tsx`
- `apps/admin/src/types.ts`
- `apps/agent/tests/test_formal_plans.py`
- `apps/backend/app/schemas/admin.py`
- `apps/backend/app/schemas/admin_plans.py`
- `apps/backend/app/services/admin_users.py`
- `apps/backend/app/services/agent_entitlements/admin.py`
- `apps/backend/app/services/agent_entitlements/assignment.py`
- `apps/backend/app/services/agent_entitlements/defaults.py`
- `apps/backend/app/services/agent_entitlements/service.py`
- `apps/backend/app/services/billing/catalog.py`
- `apps/backend/app/services/billing/service.py`
- `apps/backend/tests/test_billing_postgres.py`
- `apps/web/clients/backend/billing.ts`
- `apps/web/features/settings/components/subscription/checkout-dialog.tsx`
- `apps/web/features/settings/components/subscription/subscription-panel.tsx`
- `apps/web/lib/auth/entitlements.ts`
- `apps/web/lib/auth/server.ts`
- `apps/web/tests/settings/checkout-dialog.test.ts`
- `docs/agent/entitlements.md`
- `docs/billing/README.md`
- `apps/backend/app/services/agent_entitlements/dates.py`
- `apps/backend/app/services/agent_entitlements/lifecycle.py`
- `apps/backend/tests/test_admin_membership.py`
- `apps/backend/tests/test_billing_membership.py`
- `apps/backend/tests/test_entitlement_lifecycle.py`
- `apps/web/features/settings/components/subscription/billing-state.ts`
- `apps/web/tests/settings/billing-state.test.ts`
