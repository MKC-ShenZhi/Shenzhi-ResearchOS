# 历史 Grant 管理员对账关闭修复

新增受保护管理员 reconcile-close API，默认预览；复用 Admin 会话/同源保护、owner→grant 锁、UsageSettlement 完整性检查及追加账本、EntitlementAudit。Agent 增加 Fact Reader 只读事实接口。执行必须重新核验实时任务/调用/Outbox/Manifest、实际采纳用量、allocation/window 账本；不清除 overage，不改历史 Usage 或旧 Manifest。无数据库迁移、无自动关闭或权益分配旁路。使用方式见 docs/agent/entitlements.md。

## 定向验证

- Agent：`uv run --no-sync pytest tests/test_a_line_persistence.py -k 'admin_reconcile or overage_preserves or close_missing or sealed_unstarted' -q`：5 passed，28 deselected。
- Backend：`uv run --no-sync python -m unittest tests.test_admin_console -q`：11 tests，OK。
- 覆盖预览无权益变更、追加释放并保留真实用量/overage/旧账本、幂等回放和冲突、任务未完成、过期事实、未提交最终 Manifest、Unknown、窗口账本不一致、管理员会话与同源保护、409 原因映射及原关闭路径。测试使用隔离内存数据库与 mock，不证明 PostgreSQL 并发行锁。
- `git diff --check` 通过。未运行全仓库测试。

## 真实 Grant 只读核验

2026-11-20，对两侧数据库使用显式 READ ONLY / REPEATABLE READ 事务；仅执行预览校验函数，没有调用关闭 API，没有写入审计或任何真实数据。

- Task `7555f06ad52a49e19e78c23365cf1dd9`：completed。
- Grant `794c4d81e1424a92814fecffbc6c5f06`：active，overage=true。
- 14 个 Usage Outbox 全部 delivered，usage sequence=14；无 Unknown，全部执行 sealed，无可启动 Permit；已有最终 Manifest 与当前快照匹配，调用结算及 allocation 核验通过。
- Token allocation：task_held=936000，allocation 账本 held=936000，账本 used=58177。
- daily-tokens 共享窗口：counter.held=936000，window 账本 held=936000；但 counter.used=159480，window 账本 used=83101，差额 76379。
- 该次核验结论：**未通过安全关闭检查**，返回 `WINDOW_USED_LEDGER_CONFLICT`。936000 Token 预留保持不动。不得根据已有报告或过期时间放行；窗口差额来源须另行核对并按授权处理，不能通过本操作覆盖计数或伪造 Usage。

未关闭真实 Grant、未修改真实用户权益、未提交或推送代码。

## 后续差额来源追查

用户执行预览收到 409 后，再次使用 READ ONLY 事务追查，确认差额有历史结转证据，并非当前 Grant 的未结算调用：

- 2026-11-20 10:41:49（Asia/Shanghai）的历史 assign 审计，在 `carried_window_usage` 中明确记录将同一 owner、同一上海自然日的 daily-tokens 用量 76379 从旧策略窗口结转到新策略窗口；`held=0`，`history_preserved=true`。
- 源策略 `free-demo-v1-20261119-local-ai-r1`；源窗口 `sha256:d19c8b75d7594677653ff3455af4e9cc62c470f2819f4358622d567bd4f3288f`。其 counter.used 与源账本累计 used 均为 76379；来源为两个已关闭 Grant 的 40932 和 35447，另一个已关闭 Grant 为 0。
- 目标策略 `free-demo-v1-20261120-personal-2m-r1`；目标窗口 `sha256:706a979abcd5e3fb12d0a1f3705b578f659569f11fb51c43826439f50a043264`。目标自身追加账本为另一已关闭 Grant 的 24924，加当前 Grant 的 58177，合计 83101。
- `76379 + 24924 + 58177 = 159480`，与目标 counter.used 完全相等。结转记录存在于历史审计，未作为目标窗口的 UsageLedger 条目写入。
- 因此当前新校验 `counter.used == 当前窗口 UsageLedger.used_delta 合计` 尚未识别这类有审计证据的历史结转，导致拒绝。不能将 76379 直接从计数中扣除，不能伪造当前 Grant 的 Usage。

后续代码应在严格核验结转审计、owner/规则/窗口身份、源账本及不重复计算后识别该历史基线，并补直接相关测试；在此之前保留拒绝行为。此次追查未修改业务代码或真实数据，未执行关闭。

## 历史结转校验修复与再次预览

用户明确选择“只修正历史结转校验并重新预览，暂不关闭”。已在现有 reconciliation 服务增加有证据的单次历史结转识别，不修改窗口计数、真实 Usage 或真实账本；原严格核验继续保留。

- 必须只有一条对应目标窗口的 assign 结转审计；核对 owner、自然日、时区、规则、源/目标策略、金额及 held=0。
- 源计数必须等于源账本累计 used，源 held 与账本均为0；逐源 allocation 核验采纳用量/账本，逐源 Grant 核验已关闭及实时 Backend Manifest/调用结算完整。
- 源账本条目必须早于结转审计；重复记录、源后续活动、跨用户/日期、金额不符、链式结转等继续拒绝。
- 结果新增 historical_carries，包含核验通过的源审计和源账本引用；以后若获授权执行释放，释放条目一并记录这些引用。当前没有执行该操作。

定向回归：Agent 原命令为 **7 passed，28 deselected**（另含9个拒绝边界 subTest）；Backend 为 **11 tests，OK**；未运行全仓库测试。新增测试使用内存数据库，覆盖预览不改用量/预留，以及隔离测试中的追加释放保留真实消耗和结转基线。

再次真实预览：通过配置好的 Fact Reader GET 获取实时 Agent close-facts，Backend 使用显式 READ ONLY / REPEATABLE READ 事务调用同一 preview 校验函数；结果 **eligible=true、preview=true**。识别历史结转 used=76379，拟释放 Token=936000；Grant 仍 active、overage=true，Token counter.used 仍159480、counter.held 与 task_held 仍936000。未新增真实审计/账本、未关闭 Grant、未修改用户权益。此次检查证明当前快照满足安全关闭条件，后续实际执行仍须重新核验并另获用户确认。

本次未重启或部署运行中的 Backend；重新通过浏览器预览前须确保该进程已加载更新代码，并使用新的 operation_id，避免回放此前409结果。未提交或推送代码。
