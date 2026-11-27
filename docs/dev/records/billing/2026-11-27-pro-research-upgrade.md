# Pro → Research 差价升级恢复与验收

日期：2026-11-27（Asia/Shanghai），分支 `feat/agent-platform`。用户明确将差价升级纳入 V1；本记录取代此前 [会员最小上线收口](2026-11-27-membership-release-scope.md) 中“暂缓升级”的范围决定，旧记录保留为历史事实。

## 修改前检查与复用

工作区已有会员、Admin、权益生命周期及订阅页的未提交改动；未重置这些改动，未调用 Sub-Agent，未改 Git 远程配置。检查了实际 Git diff、当前代码及上一轮记录：此前报价 API/schema、expected_quote 和升级分支已被移除，不能直接撤销单独提交；仍保留 BillingOrder JSON 快照、owner_snapshot、独立支付确认事务、嵌套履约事务、行锁、审计幂等、assign_policy 与跨 Revision daily_balance。

在上述路径恢复升级，没有建立新订阅授权系统、增加表、迁移或依赖。Backend Catalog 集中维护 Basic 免费、Pro 1990 分、Research 4990 分，周期为上海自然月，仍标记沙盒演示价格。Web 不维护生产价格常量。

## 当前行为与边界

- 恢复 `POST /api/v1/billing/quote`、`expected_quote`、5 分钟报价及订单快照。报价仅面向有效有限期 Pro → Research，管理员赠予同样适用；期限按原到期日向前划分自然月段，按月价差与剩余比例折算，整数分一次四舍五入，最低 1 分。多月权益计入全部剩余月份。具体算法及月底约定见 [Billing 维护文档](../../../billing/README.md)。
- Backend 在锁内重新计算用户、权益、目标 Policy 与金额绑定摘要；拒绝过期、未来、篡改及条件变化的报价。客户端只回传 quoted_at / quote_token，不提交最终价格。
- 同一未过期升级订单复用原快照／金额／渠道；不同确认报价不静默替换已有订单。过期升级订单在成功创建新订单的事务内本地关闭并保留，可重新报价／下单；渠道晚到支付仍确认到账，履约重新核验原权益。
- 普通购买和同档续费不调用 quote、不要求 expected_quote、不检查历史 quote_expires_at。保留历史无 action、固定 30 天订单的兼容路径。显式携带升级报价而升级条件已消失时拒绝，避免差价确认变成全价扣款。
- 支付通知先验签并严格核验金额、币种、商户、App、渠道、模式、交易号，付款独立提交。升级履约固定目标 Revision、保留原到期时间，使用 Research 额度并保留当日 used/held。Research 有效期内不支持主动降级。
- 报价 TTL 仅约束确认报价和获取支付入口，不拒绝延迟回调或已支付订单重试。原权益变化、期限届满、停用、未排空 Grant、Policy 不可用时保留 paid/pending；不覆盖新权益、不延长已过期升级期限、不重复下单或重复发放。排空后通过现有 refresh 重试；永久权益及无法恢复的冲突由管理员处理。
- 历史升级订单缺少必要快照时保留付款事实并返回 QUOTE_SNAPSHOT_INVALID，不猜测期限或原权益。没有新增自动退款、渠道撤单或自动补偿调度器。本地 closed 不代表支付渠道已撤单。
- Web 展示差价升级入口、后端报价／有效期、原到期时间、过期重取及订单恢复操作；正常购买／续费不发报价请求。前端时钟只负责显示和提前阻止过期确认，最终校验在 Backend。

## 验证

- Backend 相关 78 个独立用例全部通过，覆盖 billing_postgres、billing_membership、payment_providers、admin_membership、entitlement_lifecycle、agent_entitlements、admin_console。最终组合运行中 73 项通过，5 项 Admin SQL 因测试命令误用普通 PostgreSQL URL 缺失 psycopg2 而未执行；改用既有 asyncpg URL 后单独重跑整个 admin_membership 模块，6 项全部通过（含重复的 1 项契约测试），无新增依赖或放松校验。
- 真实 PostgreSQL 16 测试使用本轮专属容器、loopback 端口和 `upgrade_test` 库，每项创建随机 schema；未使用现有业务数据库。测试完成后验证专属标签，已删除本轮容器及其匿名数据卷，未操作现有服务。覆盖购买／续费历史报价隔离、自然月／闰月／分舍入、Admin 与 Billing 来源 Pro 升级、旧订单、报价过期与重取、权益变化不转全价、并发订单复用、重复通知、原期限到期、履约异常回滚、paid/pending 重试、原 Policy 快照、Research 300 万 Token 额度及原日用量保留。
- 官方支付宝 SDK 离线生成和校验临时 RSA2 签名，分别验证普通购买与升级的真实通知路由，重复通知仅一次审计，篡改金额拒绝；没有商户网络／钱包支付。
- Web 定向测试 13 项通过（订阅状态、升级报价确认与过期重取、模态交互、订单复用、原始通知转发）；TypeScript、四个相关源文件 ESLint、Next.js 生产构建通过。
- `git diff --check` 通过。初轮旧 2 分签名 fixture 已改为读取订单金额；新增 VM 测试的跨 Realm 对象断言及同步异常断言已修正。支付安全约束未为测试放宽。

未提交、推送、部署或操作生产库；未执行全仓测试、浏览器视觉验收或支付宝沙盒钱包实际支付。发布时需同步 Backend 和 Web；当前价格不代表未来正式售价。
