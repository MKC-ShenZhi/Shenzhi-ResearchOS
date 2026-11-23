# A 主线研发收尾记录（2026-11-19）

状态：按负责人要求收尾；不是最终验收通过，也不是完整生产交付。A1/A2/A3 已连续实施到代码和测试，但最终 HEAD 对应的整体回归、独立审查与生产审批未完成。

## 已落地范围

- Shared Contracts：独立 v2、必填 schema_version=1、显式 null、严格额外字段、规范化摘要、能力身份、Grant/Receipt JWS、Permit、Usage、关闭清单及 Worker 封套。原 v1 wire.py 未改。
- Agent：独立执行世代、调用 Intent/启动事实/观察/Usage Outbox；逐 HTTP 发送、摘要、重试、Tool execute_prepared、forced/read_skill；持久补报目录、门禁、历史 Lease 补报、恢复/投递进程、封闭证明及未获 Permit 响应的 tombstone 恢复。
- Backend：用户/套餐 policy revision、窗口与原子预留、Submission 幂等、签名/绑定/修订/撤销、Permit/start、Inbox 启动事实核验、追加差额账本、未知保留、关闭核验、查询与人工审计操作入口。
- 产品边界：v2 非会话、Session/Resume、stop/steer、权益/用量/账本 API；复用现有 Session 服务。未建设 B 主线 Catalog/后台/健康探测或 T3 UI。
- 迁移：Agent 0003_agent_metering（8 表）；Backend 027_agent_entitlements（15 表）。收尾时已按最终 ORM 同步冻结迁移；该最后同步未重新执行迁移测试。

## 实际测试证据（不能相加当成最终全量结果）

1. 早期共享 v1 回归：7 passed。
2. 新协议/两侧 SQLite 持久化/Mock Transport 组合：先 36 passed，后续扩展一轮 71 passed、19 subtests（该轮包含真实 PostgreSQL），随后最近定向一轮 51 passed、19 subtests（SQLite/协议/Mock Transport）。
3. 独立 PostgreSQL 首轮：19 passed，实际运行新增迁移和两库 HTTP/Mock Provider 闭环，包含并发预留、同提交竞争及撤销/start 竞态。使用任务新建的本机 PostgreSQL 17 临时容器和两个不同数据库，未连接生产数据库。
4. v1 Worker/Task 定向回归：15 passed；此前包含 Runtime/Skill/Provider 的一轮为 107 passed、14 failed，失败的隔离检查/测试替身问题已修复，相关 15 项重跑通过；更大组合未最终重跑。
5. 现有 Backend Session 回归：15 tests OK；新增 Backend 权益策略单元测试：5 tests OK。
6. 两服务 uv sync --frozen --offline --check 均显示 Would make no changes。
7. 没有真实 Provider 测试；所有 Provider 证据是 MockTransport。没有生产部署或最终验收。

可重复命令：Agent 目录使用 uv run --no-sync python -m pytest tests/test_a_line_persistence.py tests/unit/test_metering_boundaries.py ../../packages/agent-contracts/tests -q；真实两库测试显式设置 AGENT_A_LINE_TEST_DATABASE_URL/BACKEND_A_LINE_TEST_DATABASE_URL 后运行 tests/integration/test_a_line_postgres.py。Backend 使用 uv run --no-sync python -m unittest discover -s tests -p test_agent_entitlements.py -q。

## 尚待处理/审查

- 最后若干协议严格化、Token/撤销范围、恢复及迁移同步修改尚未形成同一最终工作区快照的整体回归证据；不能据历史绿色结果认定当前完整交付。
- 需独立审查状态机、事务锁顺序、补报/关闭恢复、Session 超时及重启恢复、签名/快照/能力身份和错误语义；尤其覆盖尚未充分验证的 Session v2 全流程、授权绑定与续签竞态、死信处置和恢复进程完整运行。
- 运行文档已写 docs/agent/entitlements.md，但最终后加字段与说明仍需核对，文档不能作为已验收证明。
- 套餐数值、窗口口径、预留参数、Token 范围、计次/退款/未知最终处置、风险上界、撤销参数及生产密钥部署仍由负责人批准。未安装任何生产 policy；Backend v2 默认 disabled；测试策略不成为生产默认。
- 本适配器不具备可信输入 Token 硬上界验证器；正式模型调用没有明确批准的风险策略即拒绝。不能承诺实际费用绝不超额或外部调用 Exactly Once。
- 不自动迁移旧 v1 Task。新增路径和运维配置详见维护文档及两侧 .env.example。

## T3 接入材料

API、Shared Contracts、错误/状态及部署说明见 docs/agent/entitlements.md 与 docs/agent/contracts.md；可信查询为 /api/v2/agent/entitlements、/tasks/{task_id}/usage、/tasks/{task_id}/ledger。T3 接入和生产启用须等待本次独立审查与最终回归，不应直接把这些候选接口当成已批准生产契约。

## 工作区保护

开始分支 feat/agent-m0-integration，HEAD b5707ab84596af940ce25718a1a3fa6023abbcef。开始只有两份未跟踪设计文档；未修改它们。未切分支、创建 Worktree、Commit、Push、Merge、改 remote 或删除既有未跟踪文件。新增与修改均留在工作区。

新增必要依赖为 cryptography（两服务）及 aiosqlite（Agent dev）。uv 默认解析导致的无关来源变化已收敛：保留原有锁定包及来源，仅加入解析得到的新包/项目依赖边；原有依赖版本未升级。原镜像当次访问返回 403，新包保留实际解析来源；冻结环境检查通过。
