# Phase 4 实施与整体审查

日期为 2026-11-26。基线为 `18501dc692b8030a4cb7df77ca42c715295f249c`。功能分支为 `feat/agent-management-console`，从原 HEAD 创建并保留原有八个未合并提交。全部成果保留在工作区。

## 1. 完成情况

| 编号 | 状态 | 交付及边界 |
| --- | --- | --- |
| P0-01 | 已完成 | 完整 Spec 导入、Provider / Model 表单、内部与上游 ID、默认用途、Capabilities、Secret Reference、依赖预览；沿用候选、验证、审批、发布、回滚及 Worker 确认。外部客户端引用保留 unknown，发布前由管理员核对。 |
| P0-02 | 已完成 | Tool Schema、来源、版本、条件登记、Worker 分布和调用失败；指定 Run 的工具启用 / latent 证据与当前 Execution 调用 start 关联。Permit 仍在真实调用开始时裁定。 |
| P0-03 | 已完成 | 受控 Metadata、资源与依赖声明、完整性、文档预览、激活上下文及 Worker 版本证据。缺失声明或证据明确显示未知，检查不执行脚本。 |
| P0-04 | 已完成 | `#/agent` 统一入口，旧 hash 映射至 Provider；套餐使用的旧 API 保留并回归。 |
| P1-01 | 已完成 | 批量保存证据摘要、版本匹配、stale、检查步骤及 coverage。查询不主动探测，静态通过与覆盖不完整分别说明。 |
| P1-02 | 已完成 | 独立心跳巡检、持久告警、实例 / 序号去重、迟到恢复、重启及版本历史、确认与恢复后关闭。 |
| P1-03 | 已完成 | 管理员 Task / 当前 Run 取消、可信 Owner 核验、请求与确认状态、超时提示、幂等审计；Worker Drain / Resume 及超时状态。人工重试完成接口与风险设计，按授权范围保留关闭。 |
| P1-04 | 已完成 | 运行总览整合原服务 / 任务 / 失败证据、四类能力的健康摘要、Worker、告警和配置发布，提供详情链接。 |
| P2-01 | 本地实现及隔离验收完成 | SSH 公钥隧道、可信专用入口、管理 Cookie、Host / Origin 与跨站拒绝；独立离线审批签名保持身份分离。实际服务器账号与外部入口需现场验收。 |
| P2-02 | 已完成 | production Docker target、非 root 静态 Nginx、只读文件系统、正式 Compose overlay、健康检查和重启验证。 |
| P2-03 | 实现及替身验证完成 | Secret Reference 允许列表和环境注入、旧新 Registry 分离、缺失注入拒绝、独立探测 Key、轮换审计流程；实际 Provider 运行 Key 轮换需专用凭据。 |
| P2-04 | 外部阻塞 | 未提供明确授权的专用非生产 Provider 凭据。本轮未读取生产密钥；实际 Completion、Streaming、Tool Calling、故障及轮换须另行验证。受控探测和协议回归已有测试。 |
| P2-05 | 隔离验证完成 | Worker 真实容器断网、恢复和重启，告警生命周期及 Drain；PostgreSQL 发布 / 回滚 / 并发 / 超时 / 对账、Lease 故障和 Outbox；取消与迟到用量结算。 |
| P2-06 | 实现完成，平台运行待触发 | GitHub Actions 覆盖构建、契约、Backend、Agent、浏览器、PostgreSQL 管理与迁移、生产镜像和 Compose；文档已同步。依用户要求保留本地，Actions 尚未触发，分支保护未核验。 |

P0 / P1 的功能及当前环境可执行的 P2 工作已交付。Phase 4 全部外部验收尚未闭合，当前不能宣布 Production Readiness。

## 2. 架构与代码

管理链路继续为 Admin Feature → 同源 Backend API → Service / Integration → Agent 内部 API。浏览器不连接 Agent、数据库或 Provider，不持有内部服务 Token。

Provider / Model 编辑以完整 ConfigSpec 为基准，仅变更指定字段。首次配置可导入完整部署 Spec，JSON 高级入口保留。依赖预览会读取默认用途、Policy、Owner、Grant 和持久 Task 引用。来源不完整或扫描超限会拒绝给出完整结论。配置发布仍复用原审批、CAS、fencing、兼容性和权益屏障。

新增 WorkerRuntimeRow 保存运行观测；Loaded 只在新鲜 Worker / Run 证据下推导。Run Callable 的肯定证据来自当前 Lease Execution 的实际调用 start，并附观测时间。旧 Worker 未提供 latent / 完整性标志时保留未知；截断清单不会推导工具不存在。

健康摘要使用一次目标集合 SQL 查询及一次 Agent 当前身份查询。待处理检查按目标 fingerprint 查询，结果不明或未完成检查不会被旧成功记录覆盖。过期和版本变化显示 stale。

管理控制通过服务端认证、幂等操作和审计实现。Worker 控制使用独立配置管理 Token，读取 Token 无法执行 Drain / 告警变更。Task 取消复用已有 Gateway v2 与 repository 协议。awaiting_input 的 Task 可以结束，原 checkpoint 报告保留。

## 3. API 和 Contract

Backend 路径前缀为 `/api/v1/admin-console`。

| API | 用途 |
| --- | --- |
| POST `/agent/config/preview` | 校验完整候选并只读查询依赖 |
| POST `/agent/checks/summary` | 批量读取保存检查及当前版本匹配 |
| GET `/agent/alerts` | 分页查询持久告警及巡检启用状态 |
| GET `/agent/worker-control/{worker_id}` | Drain、存量 Run 和超时状态 |
| POST `/agent/actions` | 取消、Drain、Resume、告警确认 / 关闭 |
| GET `/agent/control-status/{kind}/{target_id}` | 取消请求、任务终态和 Execution 确认 |
| GET `/agent/tools/{tool_id}?run_id=...` | 指定 Run 的工具观测 |

Agent 内部新增 identities、model-references、alerts、worker-control 和 config/actions。内部接口使用既有角色和 NoStoreRoute 边界。

Run 取消经 `/internal/v2/tasks/{task_id}/runs/{run_id}/cancel` 原子核对当前 Run。预条件在 Task 行锁内检查，旧 Agent API 不支持该路径时拒绝执行，避免查询与取消之间发生重试切换竞态。

共享 Contract 增量加入运行工具清单的 latent / 完整性标志、运行证据、Skill Metadata / 激活上下文、调用失败摘要、Task 取消意图、检查 coverage、管理动作及外部审批证明。旧 WorkerReport 和 Approval 未提供新字段时，序列化保持原请求摘要形式。

## 4. 数据库与部署

Agent 迁移 `0008_management_operations` 新增以下四张表。

- `agent_management_runtime_evidence`
- `agent_management_worker_control`
- `agent_management_worker_alerts`
- `agent_management_operations`

迁移在独立 PostgreSQL 执行 upgrade → downgrade 至 0007 → upgrade。降级移除上述管理表，原 Task / Run / Execution / Usage 表保持。应用回滚前需停止新控制和巡检、处理 Drain 并导出管理历史，详见维护说明。

Admin production 镜像从完整源码生成静态产物。验收复用缓存 Node 开发镜像作为构建依赖，Backend / Agent 复用已有依赖镜像并只读挂载当前源码。最终报告中的容器结果对应当前源码执行，未声称本轮重建了 Backend / Agent 镜像。

正式入口使用共享网络命名空间和 loopback 端口映射，Nginx 覆盖入口 Header，Backend 验证专用文件密钥及管理会话。公开 Nginx 拒绝片段在隔离代理实测阻断精确路径、子路径及编码斜杠路径。Backend 无 Docker Socket 挂载。

## 5. 安全审查

| 边界 | 结果 |
| --- | --- |
| 管理认证 | local_password 回归保留；ssh_tunnel 必须有专用入口密钥、稳定部署身份和 Cookie。直接 Backend、错误 Host、Origin 和跨站请求被拒绝。 |
| Secret | Spec 和浏览器只接收引用。运行与探测 Key 分离，生产 Key 未读取。无私钥文件或密钥明文进入新增源码；无效候选响应不回显提交的敏感值。 |
| 审批 | 单管理员可提交独立审批者 Ed25519 证明；证明绑定修订、验证和摘要并有时效。Agent 只持有公钥，真实人员与私钥独立性由部署落实。 |
| 发布 | 沿用候选、验证、审批、CAS、fencing、Worker 确认和权益屏障；未扩大为跨服务分布式事务承诺。 |
| 审计 | 控制操作带操作 ID、操作者、目标和原因；相同 ID 不同请求冲突。已拒绝操作不会因目标后来出现而在重试中执行。 |
| 取消 | Owner 从可信 Task 获取，旧 Run 无法取消新 Run；取消不会新建执行或重用 Permit。在途调用取消后，迟到真实用量仍按原身份结算。 |
| Worker | Drain 与领取通过 PostgreSQL Worker 级事务锁串行化；存量运行继续，超时保持拒绝领取。上报与巡检使用相同管理写锁和数据库协调。 |

隔离 SSH 验收使用临时容器及合成密钥，生产部署仍须使用普通专用账号和受保护私钥。本机替身、localhost 网络和临时 SSH 服务的证据范围在验收脚本中明确标注。

## 6. 测试结果

各命令包含重叠用例，以下保留独立运行结果。

| 检查 | 实际命令或范围 | 结果 |
| --- | --- | --- |
| Agent 全套 | `uv run --no-sync python -m pytest -q --tb=short` | 323 passed、79 skipped、0 failed，129 subtests passed；耗时 278.98 秒 |
| 收尾专项 | `tests/test_management_operations.py tests/test_management_config.py tests/unit/test_task_runs.py` | 29 passed、1 skipped、0 failed；覆盖新增候选依赖、运行控制、版本检查和取消 |
| 取消预条件复验 | 上述运行管理与 Task 用例中按 cancel / rejected_control / run_tool 筛选 | 6 passed、0 failed；包含 Task 行锁内旧 Run 拒绝及 checkpoint 报告保留 |
| 权限复验 | `tests/test_management_operations.py -k drain_blocks` | 1 passed，读取 Token 无法执行控制 |
| Backend | `uv run --no-sync python -m unittest tests.test_admin_console tests.test_admin_tunnel tests.test_agent_entitlements tests.test_agent_gateway_transport tests.test_agent_contracts -q` | 27 tests，全部通过 |
| 共享 Contract | `uv run --no-sync python -m unittest discover -s ../../packages/agent-contracts/tests -q` | 8 tests，全部通过 |
| PostgreSQL 配置及管理 | `tests/test_management_config.py tests/integration/test_management_operations_postgres.py`，显式指定两项测试 DSN | 23 passed、1 skipped、0 failed；包含 Drain / Claim 事务锁等待、事件去重、审批与控制 |
| PostgreSQL A-line | `tests/integration/test_a_line_postgres.py` | 41 passed、0 failed，9 subtests passed |
| 新增 PostgreSQL 取消与结算 | 上述 A-line 中 `-k cancel_preserves` | 1 passed、41 deselected；真实 v2 HTTP 预条件拒绝、重复取消、心跳确认、迟到用量和单次入账 |
| PostgreSQL 套餐 | `tests/integration/test_formal_plans_postgres.py` | 14 passed、0 failed |
| 浏览器 | 三个管理测试文件中 `-k admin_browser`，显式设置本地 Chrome | 三项通过；覆盖管理读取、检查 / 诊断、表单往返和旧入口 |
| 构建 | `pnpm --dir apps/admin build` | TypeScript / Vite 通过 |
| 迁移 | 独立 PostgreSQL 上 `alembic upgrade head`、`downgrade 0007_worker_lifecycle`、再次 `upgrade head` | 全部通过 |
| Compose | 合成测试环境变量及 `config --no-env-resolution --quiet` | admin profile 及迁移依赖校验通过 |
| 生产镜像 | production target，复用缓存 Node 构建依赖 | 当前源码构建通过 |
| 容器 / SSH | `uv run --no-sync python tests/integration/phase4_container_acceptance.py --network shenzhi-phase4-accept --postgres shenzhi-phase4-postgres-20261126 --ssh-image shenzhi-phase4/sshd:accept` | 静态服务、可信入口、Cookie、直连拒绝、公开代理阻断、跨站拒绝、重启、入口 Secret 轮换、Worker 断网恢复、告警确认关闭、Drain / Resume、真实公钥隧道均通过 |
| 差异和 Secret 检查 | `git diff --check`，另扫描新增文件行尾、私钥块及前端敏感环境引用 | 通过 |

全套中的跳过项包括显式双库 A-line、正式套餐、Phase 4 PostgreSQL、既有 M0-C1 专用数据库及 Chrome 选择条件。可用双库、管理 PostgreSQL 和 Chrome 已通过上列独立命令验证。既有 M0-C1 专用库未选中，相关领取和 fencing 场景通过当前隔离 PostgreSQL 专项覆盖。收尾专项中的单项 skip 是未在该命令设置 Chrome，浏览器另行执行。

收尾补充了少量回归用例，上列全套数量反映该次全套执行时的集合，新增用例的独立结果另行列出。全套的 42 条提示来自 Python SQLite 默认 datetime adapter 弃用；Backend TestClient 还提示底层适配的弃用，均未造成测试失败。

构建期间曾遇到 Docker Hub Dockerfile frontend manifest 请求 EOF。隔离构建使用相同 Dockerfile 正文和 Engine 内置 frontend，复用已缓存依赖，随后成功生成 production 产物。应用 Dockerfile 的默认来源保留。

## 7. 修复过的验收问题

- 原 MemorySession 测试夹具缺少 bind、参数化查询和 get，按真实 SQLAlchemy Session 接口补齐。
- 旧预算与 Lease 断言落后于当前基线，核对 HEAD 的实际常量后更新测试；运行预算未因测试调整。
- PostgreSQL A-line 隔离夹具缺少新增 Worker 控制表，补充测试结构后全部回归通过。
- Nginx 在只读文件系统中尝试创建默认临时目录，所有临时目录改用 tmpfs 后复验通过。
- 生产 Compose 的 admin profile 缺少 Backend 迁移依赖服务的 profile，补齐并通过配置验证。
- Windows OpenSSH 拒绝测试私钥的继承 ACL。隔离 SSH 客户端改用 WSL 私有临时目录和 0600 权限，不更改用户真实 SSH 文件。
- 隧道关闭后的 Windows / WSL 转发可能表现为连接超时，验收同时核对 SSH 进程退出和管理请求不可达。
- 浏览器导航曾用多个页面共有的“查看诊断”等文本判断页面已切换，可能点击前一页按钮。导航改为等待目标页面唯一标题，再执行后续动作；同时增加场景 Lease 时长并输出失败页面文本。相关三项复验通过。

## 8. 最终 Git 与外部条件

当前分支为 `feat/agent-management-console`，HEAD 仍为 `18501dc692b8030a4cb7df77ca42c715295f249c`。保留全部未提交修改，未推送、未合并、未创建 PR，未部署生产环境。文件清单和最终 diff 统计见文末。

内部受控使用需要先部署当前源码、迁移 0008、配置角色凭据和入口，再按需求启用巡检及管理写入。独立审批公钥和签名流程需配置后才能完成身份分离发布。

本轮创建的入口、SSH、Worker 和应用验收容器已在脚本结束时移除。独立 PostgreSQL 测试容器已停止，测试卷和构建镜像保留以便复核。临时测试密钥由验收脚本清理。

上线剩余外部条件包括明确授权的专用非生产 Provider 凭据与实际轮换验收，真实服务器普通 SSH 账号、公开代理 / 防火墙与访问隔离验证，审批者私钥保管及独立性落实，以及后续授权推送后的 Actions 运行和平台策略核验。

维护入口为 [管理控制台说明](../../../admin/agent-management-console.md) 和 [正式部署说明](../../../../infra/docker/ADMIN.md)。

## 9. 最终文件清单与统计

已跟踪文件的 git diff --stat 如下。新增未跟踪文件另列，全部保留在工作区。

```text
apps/admin/Dockerfile                              | 18 +++++-
 apps/admin/README.md                               |  6 +-
 apps/admin/src/features/CapabilitiesPage.tsx       | 50 ---------------
 .../admin/src/features/agent/AgentConfigCenter.tsx | 72 +++++++++++++++++-----
 apps/admin/src/features/agent/AgentDiagnostics.tsx | 26 ++------
 apps/admin/src/features/agent/AgentManagement.tsx  | 37 ++++++++---
 apps/admin/src/main.tsx                            |  8 ++-
 apps/admin/tests/agent-management-smoke.mjs        | 40 +++++++++++-
 apps/agent/.env.example                            |  3 +
 apps/agent/src/agent_app/api/config_management.py  |  7 +++
 apps/agent/src/agent_app/api/management.py         | 62 ++++++++++++++++++-
 apps/agent/src/agent_app/api/v2.py                 | 10 ++-
 apps/agent/src/agent_app/config_deployment.py      |  9 ++-
 apps/agent/src/agent_app/control/repository.py     | 15 ++++-
 .../agent_app/infrastructure/management_models.py  | 41 ++++++++++++
 apps/agent/src/agent_app/main.py                   | 17 ++++-
 apps/agent/src/agent_app/management_catalog.py     | 11 +++-
 apps/agent/src/agent_app/management_checks.py      | 32 +++++++---
 .../agent/src/agent_app/management_observations.py | 58 ++++++++++++++++-
 apps/agent/src/agent_app/management_workers.py     | 36 ++++++++++-
 .../src/agent_app/worker/management_reporter.py    |  4 ++
 .../tests/integration/test_a_line_postgres.py      |  2 +
 apps/agent/tests/test_a_line_persistence.py        | 40 ++++++++++++
 apps/agent/tests/test_management_bridge.py         |  7 +++
 apps/agent/tests/test_management_config.py         | 18 ++++++
 apps/agent/tests/unit/test_agent_fast_search.py    | 20 +++---
 apps/agent/tests/unit/test_task_runs.py            | 23 ++++++-
 apps/agent/tests/unit/test_worker_takeover.py      | 14 +++--
 apps/backend/.env.example                          |  4 ++
 apps/backend/app/api/admin_console.py              | 12 +++-
 apps/backend/app/api/agent_config_management.py    |  5 ++
 apps/backend/app/api/agent_management.py           |  1 +
 apps/backend/app/api/agent_management_phase2.py    | 34 +++++++++-
 apps/backend/app/core/admin_auth.py                | 37 ++++++++++-
 apps/backend/app/integrations/agent_management.py  |  2 +
 .../app/services/agent_config_management.py        | 45 ++++++++++++++
 apps/backend/app/services/agent_gateway/v2.py      |  7 ++-
 .../backend/app/services/agent_management_audit.py |  2 +-
 docs/admin/agent-management-phase3.2-readiness.md  |  2 +
 docs/engineering/architecture-confirmation.md      |  2 +-
 docs/engineering/deployment.md                     | 12 ++--
 infra/docker/env/agent.env.example                 |  2 +
 infra/docker/env/backend.env.example               |  3 +
 .../src/agent_contracts/management.py              |  6 ++
 .../src/agent_contracts/management_config.py       |  8 +++
 .../src/agent_contracts/management_phase2.py       | 18 +++++-
 46 files changed, 727 insertions(+), 161 deletions(-)
```

已跟踪变更 46 项，新增文件 25 项。

### 已跟踪变更

- `M	apps/admin/Dockerfile`
- `M	apps/admin/README.md`
- `D	apps/admin/src/features/CapabilitiesPage.tsx`
- `M	apps/admin/src/features/agent/AgentConfigCenter.tsx`
- `M	apps/admin/src/features/agent/AgentDiagnostics.tsx`
- `M	apps/admin/src/features/agent/AgentManagement.tsx`
- `M	apps/admin/src/main.tsx`
- `M	apps/admin/tests/agent-management-smoke.mjs`
- `M	apps/agent/.env.example`
- `M	apps/agent/src/agent_app/api/config_management.py`
- `M	apps/agent/src/agent_app/api/management.py`
- `M	apps/agent/src/agent_app/api/v2.py`
- `M	apps/agent/src/agent_app/config_deployment.py`
- `M	apps/agent/src/agent_app/control/repository.py`
- `M	apps/agent/src/agent_app/infrastructure/management_models.py`
- `M	apps/agent/src/agent_app/main.py`
- `M	apps/agent/src/agent_app/management_catalog.py`
- `M	apps/agent/src/agent_app/management_checks.py`
- `M	apps/agent/src/agent_app/management_observations.py`
- `M	apps/agent/src/agent_app/management_workers.py`
- `M	apps/agent/src/agent_app/worker/management_reporter.py`
- `M	apps/agent/tests/integration/test_a_line_postgres.py`
- `M	apps/agent/tests/test_a_line_persistence.py`
- `M	apps/agent/tests/test_management_bridge.py`
- `M	apps/agent/tests/test_management_config.py`
- `M	apps/agent/tests/unit/test_agent_fast_search.py`
- `M	apps/agent/tests/unit/test_task_runs.py`
- `M	apps/agent/tests/unit/test_worker_takeover.py`
- `M	apps/backend/.env.example`
- `M	apps/backend/app/api/admin_console.py`
- `M	apps/backend/app/api/agent_config_management.py`
- `M	apps/backend/app/api/agent_management.py`
- `M	apps/backend/app/api/agent_management_phase2.py`
- `M	apps/backend/app/core/admin_auth.py`
- `M	apps/backend/app/integrations/agent_management.py`
- `M	apps/backend/app/services/agent_config_management.py`
- `M	apps/backend/app/services/agent_gateway/v2.py`
- `M	apps/backend/app/services/agent_management_audit.py`
- `M	docs/admin/agent-management-phase3.2-readiness.md`
- `M	docs/engineering/architecture-confirmation.md`
- `M	docs/engineering/deployment.md`
- `M	infra/docker/env/agent.env.example`
- `M	infra/docker/env/backend.env.example`
- `M	packages/agent-contracts/src/agent_contracts/management.py`
- `M	packages/agent-contracts/src/agent_contracts/management_config.py`
- `M	packages/agent-contracts/src/agent_contracts/management_phase2.py`

### 新增文件

- `.github/workflows/agent-management.yml`
- `apps/admin/src/features/agent/AgentConfigForm.tsx`
- `apps/admin/src/features/agent/AgentHealthSummary.tsx`
- `apps/admin/src/features/agent/AgentOperations.tsx`
- `apps/admin/src/features/agent/AgentOperationsOverview.tsx`
- `apps/admin/src/features/agent/agent-api.ts`
- `apps/agent/migrations/versions/0008_management_operations.py`
- `apps/agent/scripts/sign_config_approval.py`
- `apps/agent/src/agent_app/config_approval.py`
- `apps/agent/src/agent_app/management_operations.py`
- `apps/agent/tests/integration/phase4-sshd.Dockerfile`
- `apps/agent/tests/integration/phase4_container_acceptance.py`
- `apps/agent/tests/integration/test_management_operations_postgres.py`
- `apps/agent/tests/test_management_operations.py`
- `apps/backend/app/services/agent_health_summary.py`
- `apps/backend/app/services/agent_management_operations.py`
- `apps/backend/tests/test_admin_tunnel.py`
- `docs/admin/agent-management-console.md`
- `docs/dev/records/agent/phase4-implementation-20261126.md`
- `infra/docker/ADMIN.md`
- `infra/docker/compose.admin.yml`
- `infra/docker/nginx/admin.conf.template`
- `infra/docker/nginx/public-admin-deny.conf`
- `infra/docker/nginx/start-admin.sh`
- `packages/agent-contracts/src/agent_contracts/management_operations.py`
