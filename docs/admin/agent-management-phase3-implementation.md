# ShenZhi Agent Management Phase 3 实施与隔离验收

Phase 3 已交付配置修订、发布协调、执行约束、兼容领取与接管、独立审计和 Admin 管理入口。隔离 PostgreSQL 已验证核心行为。完整生产验收仍有缺口，生产配置写入和强制兼容调度继续关闭。

## 1. 基线与工作区

- 工作分支 `chore/docker-compose-infra`，HEAD `f04e01ac11f95e75f5c29bdfa0e6d4025c94dbc3`，包含原审查基线 `60188121277bdeb738f19e6e414d82e386533b6c`。以包含 Phase 1、Phase 2 未提交成果的现有工作区实施。
- 保留原 Admin 管理路径、页面和套餐事务。权益、Permit、结算及历史迁移的源文件无需改写。没有切换分支、提交、推送、修改本机或生产环境配置，也没有连接生产数据库、使用生产凭据或调用生产 Provider。
- 验证使用独立回环 PostgreSQL 和单独 Compose 项目。Compose 的环境、端口改动和挂载覆盖仅存在于测试副本。测试服务已停止。

## 2. 不可变配置版本

`agent_contracts/management_config.py` 的 `ConfigSpec` 按标识排序规范化，覆盖 Provider、Model、默认用途、Tool/Skill 摘要及 Build、Runtime。以 Schema v1 和 SHA-256 标识正文，版本号单调分配。 `config_deployment.mutate` 用新 ID 写入版本，保留基准、操作人、时间及原因；同 ID 请求内容不同返回冲突。按版本读取完整定义和基准差异。

已持久化的状态包括 draft、validated、blocked、deploying、partially_deployed、pending_reconcile、active、rollback_pending、rolled_back、paused。审批随开始发布时的操作与审批引用保存。静态和隔离验证通过回执关联，未单独持久化 validating 或 approved 阶段。请求结果不明通过 Backend 的独立审计标记 unknown。

## 3. Provider 与 Model

可创建和编辑候选 Provider、关联 Model、声明能力与默认用途、启停、比较历史、验证、发布及回滚。Provider ID、内部 Model ID、上游 Model ID、Brand 分开保存。现阶段协议为现有 Registry 支持的 OpenAI Chat Completions，客户端沿用现有连接设置。管理页面接受结构化 JSON，支持下载不可变部署清单。

`execution/config_profile.py` 校验 HTTPS origin、受控 Secret Reference、明确 Build 和摘要。路由身份包括 Provider ID、协议和 base URL，Model 身份同时按实际模型能力计算。更换 Secret Reference 不会单独改变路由身份；旧 Worker 仍需保留旧凭据，实际轮换与撤销由部署系统完成。老的 `AGENT_MODEL_ROUTE_REVISION` 产生的能力版本可能与新身份不同，必须通过只读兼容检查，必要时走现有套餐发布和迁移。

## 4. Tool 与 Skill

- Tool 候选引用已登记实现。Worker 同时校验实际 Tool 能力摘要与当前实现、依赖锁的摘要。旧 Registry Schema、注册条件和 Run 激活证据仍可查。
- Skill 候选引用 `<artifact root>/<digest>/<slug>` 目录。加载时复核完整资源摘要及路径边界，证明和 Worker 上报绑定实际 Skill 身份。配置指定的候选只启用静态资源。现有默认 Skill 的受控运行规则继续使用。Phase 2 的文件预览和依赖诊断继续提供。
- 配置中心支持登记引用和比较摘要；已有历史制品的可用性由部署侧保留。管理界面没有历史 Skill 文件浏览或跨构建 Tool Schema 对比。

## 5. Policy、Grant 和 Worker 兼容性

Backend `agent_config_management.impact` 只读比较已发布 Policy、启用 Owner、未关闭 Grant 的 Capability ID 和精确版本。扫描超限、未知快照或连接失败返回 unknown。变更关联 Policy 需要回到原有套餐流程，受影响且尚未关闭的 Grant 需要排空。

Agent 统计排队、运行、未交付 Outbox、需要旧 Worker 或排空的 Task/Run，以及当前 Manifest 与目标证明的匹配情况。首次启用要求原 Task 排空及 Outbox 交付；并行发布要求既有约束 Task 继续具备相同旧 Manifest 的 Worker。检查仅基于实际证据，超过有界扫描范围时暂停。兼容性回执包含 blocker、影响 Policy、Owner、Grant 及 Worker 和版本对比线索。

## 6. Task 执行约束

`config_scheduling.admission` 在 Task 提交事务内固定当前正式修订、配置摘要、Build、Runtime、能力 Manifest 摘要和 Grant 精确允许的能力。相同提交先使用已有幂等结果。Grant 签名和 Permit 的验证继续走原路径。未固定的历史 Task 在强制模式中保留等待并显示诊断；通过排空处理历史版本未知问题。

## 7. Worker 领取及 Lease 接管

`control/repository.py::claim_run` 在既有 Task→Run 锁序和 `FOR UPDATE SKIP LOCKED` 选择上前置版本条件。Agent 用 Worker ID、实例 ID、独立凭据和最新健康 Manifest 核验资格，领取与过期 Lease 接管使用同一条件。Worker 执行前再次比对本地能力。没有合适 Worker 时保留任务，Task 详情标注版本和等待原因。执行尝试和前一 Lease 的历史密封由既有事务处理。

## 8. Shadow Mode

`AGENT_CONFIG_SCHEDULING` 支持 `off`、`shadow`、`enforce`，默认 off。Shadow 对原路径选出的存量 Task 记录兼容判定，同时继续原领取行为。已经有不可变约束的 Task 在关闭或切回 shadow 后会保留等待，防止绕过已启用的保护。生产入口切换前需从 shadow 验证真实任务分布。

## 9. 配置发布

1. 创建候选并下载制品清单。
2. 部署侧在隔离运行时挂入清单、制品、受控凭据与 Validator 签名密钥。验证 Agent 本地 Registry、Skill 资源与实际构建。一组候选最多执行 12 个模型探测，共用 45 秒上限，单模型使用 Phase 2 的有界检查、专用诊断凭据、allowlist 和 DNS 防护。仅静态验证不能进入正式发布。
3. 提交签名证明，Backend 查询权益影响，Agent 验证版本与证明有效期。
4. 提交审批引用、原因、预期正式修订与目标 Worker 批次。数据库 CAS 保持正式指针，先变更 desired。
5. 运维分批投放同一不可变清单。每个 Worker 用实际 Manifest 上报 effective；在发布详情执行核验。达到全部目标确认且存量兼容、证据仍有效时才切换 active。
6. 观察 Task、旧 Worker、Lease、Outbox 与审计。可以使用暂停操作保留原正式指针。当前实现由运维挂载及重启 Worker，执行器保持部署系统边界。

## 10. 回滚

为目标历史修订重新取得签名证明，带当前 active 的 CAS 和审批引用创建回滚，先更新 desired。在线且精确匹配的目标 Worker 到齐、旧任务路径仍可执行时才确认 rolled_back。离线或超时保持 partial/pending；原操作 ID 支持查询及幂等重放。暂停和回滚保持历史 Task、Run、Grant、Ledger。制品、依赖或凭据遗失时必须恢复后重新验证。

## 11. Admin 页面

Agent 管理内新增配置中心、修订和发布详情，Provider、Model、Tool、Skill 入口可进入中心。页面显示当前及期望版本、差异、目标 Worker、实际确认、兼容性、发布历史、审批与操作原因。关键写入复用同源 Cookie、`X-Admin-Request`、后端写权限和确认弹窗。两端开关关闭时禁用配置写入口。Task 详情显示版本及等待原因，Worker 页保留加载证据。

## 12. API

- Backend 同源前缀 `/api/v1/admin-console/agent/config`。GET `/revisions`、`/revisions/{revision}`、`/operations/{id}`；POST `/revisions`、`/revisions/{revision}/{validate,activate,rollback}`、`/deployments/{id}/{reconcile,pause}`、`/admission`。
- Agent 内部前缀 `/internal/v2/management/config`，对应读写由独立角色凭据保护。额外 GET `/validations/{id}`、`/deployments/{id}/proof`；POST `/attest` 仅在候选环境运行。Agent Gateway 的 `/internal/v2/config-admission` 支持 Backend 在生成新授权数据前作只读准入检查。
- Agent `/internal/v1/config` 维持响应形状，强制模式下用正式版本投影 Model、默认项及 Skill。Agent API 与 Worker 的制品和环境凭据须按部署角色挂载。

## 13. 模型和迁移

Agent 新增 `agent_config_revisions`、`agent_config_control`、`agent_config_operations`、`agent_task_execution_constraints`。新增 `0005_config_management`，以前一份 Phase 2 并行验收迁移 `0004_agent_management` 为父版本。Backend 复用其现有 Phase 2 `029_agent_management` 审计表。没有跨服务外键。在线 downgrade 发现正式/期望版本或 Task 约束时拒绝移除本阶段表。数据回滚应优先执行应用级配置回滚。

## 14. 独立管理审计

`services/agent_management_audit.py` 继续以 HMAC 封存管理操作。配置创建、校验、启用、对账、暂停、准入变更和回滚记录操作人、ID、请求摘要、目标、审批、原因和阶段。Backend 首先记录请求，Agent 持久化操作回执，超时可查询同一操作的原始回执；普通 GET 显示最新部署状态。Agent 版本协调和 Backend 审计各有本地事务。权益操作审计的表、查询范围和响应保持原职责。

## 15. 凭据和边界

Backend `ADMIN_AGENT_CONFIG_WRITE_ENABLED` 与 Agent `AGENT_CONFIG_WRITE_ENABLED` 默认 false。Backend `AGENT_CONFIG_ADMISSION_PREFLIGHT` 默认 false。配置角色、Worker reporter、现有 service/worker/gateway/fact-reader/control 角色分开。证明签名密钥需独立。浏览器只接收 Secret Reference、摘要和代理响应。候选角色拒绝正式提交、领取和接管；运维还需将候选运行时接入独立数据库、工作区和网络。常规 Compose 的 Worker、Usage 和迁移容器清空管理凭据。

## 16. Phase 3 文件清单

| 位置 | 内容 |
| --- | --- |
| `apps/admin/src/features/agent/AgentConfigCenter.tsx`、`AgentManagement.tsx`、`apps/admin/src/useResource.ts` | 配置页面和导航、历史详情、Task 兼容状态 |
| `apps/backend/app/api/agent_config_management.py`、`services/agent_config_management.py` | 管理 API、权益影响、Agent 对账 |
| Backend `main.py`、`services/agent_management_audit.py`、`integrations/agent_management.py`、`services/agent_gateway/v2.py` | 路由、审计事件、独立角色、可选准入预检 |
| Agent `api/config_management.py`、`config_deployment.py`、`config_scheduling.py`、`execution/config_profile.py` | 版本协调、运行约束和执行配置加载 |
| Agent `control/repository.py`、`api/v2.py`、`api/routes.py`、`worker/host.py`、`worker/management_reporter.py`、`worker_main.py`、`main.py`、`management_observations.py`、`management_workers.py` | Task、Lease、Worker 证据、运行配置和 Task 诊断 |
| Agent `application/composition.py`、`execution/metering.py`、`execution/runtime.py`、`extensions/skills.py`、`integrations/llm/resolver.py` | 受控制品、能力身份和 Registry 适配 |
| Agent `infrastructure/config_management_models.py` 和 `migrations/versions/0005_config_management.py`、`migrations/env.py` | 新表与迁移 |
| `packages/agent-contracts/src/agent_contracts/management_config.py`、`management.py`、`management_phase2.py` | 独立发布契约和可选证据字段 |
| Agent `tests/test_management_config.py`、`tests/test_management_phase2.py`、`apps/admin/tests/agent-management-smoke.mjs` | PG、桥接与 Chromium 验收 |
| Agent、Backend 本地与 Docker 环境示例，`infra/docker/compose.yml` | 默认关闭及隔离角色 |

## 17. 测试与实际结果

| 命令或检查 | 结果 |
| --- | --- |
| Admin `pnpm run build` | TypeScript 和 Vite 构建通过 |
| Agent `uv run --no-sync pytest -q tests/test_management.py tests/test_management_bridge.py tests/test_management_phase2.py tests/test_management_config.py`，设置本地 Chromium | 28 通过，含两次 Chromium smoke 和 Phase 3 登录/同源 API 验证 |
| 同一 Agent 的 Phase 3 测试，提供 `SHENZHI_PHASE3_AGENT_TEST_DSN` 指向独立 `phase3accept` | PostgreSQL 上 5 通过，包括并发领取 |
| Backend `uv run --locked --with pytest --with aiosqlite python -m pytest -q tests/test_admin_console.py tests/test_admin_audit_accounts.py tests/test_agent_entitlements.py` | 19 通过 |
| Agent `alembic upgrade head`、`downgrade 0004_agent_management`、`upgrade head` | 独立 PG 成功，Phase 2 Worker 与旧 Task 行摘要在额外迁移往返前后相同 |
| Backend `alembic upgrade head` | 独立 PG 成功，达到 Phase 2 `029_agent_management` |
| `ruff check --select F401,F821`（新 Phase 3 Python 模块）与 `git diff --check` | 通过 |
| WSL Docker Compose `config --quiet`，随后使用缓存镜像挂载工作区源码副本 | 独立 PostgreSQL、三项迁移、Backend、Admin、Agent API、Worker、Usage Worker 启动。容器回环内验证 Admin 登录、配置 GET、独立角色及 Backend/Agent 默认写入拒绝 |
| 从本次源码重建 Compose 镜像 | Docker Hub 匿名鉴权连接 EOF，备用验证使用缓存镜像及本次源码挂载。没有把备用结果计为新镜像验收 |

## 18. 故障注入

已覆盖非法配置、缺 Secret、防泄漏、规范化、过期证明、拒绝候选执行、不可变修改、CAS 冲突、重复与冲突操作 ID、静态证明阻断、Grant 影响阻断、Worker 证据过期、错误实例/凭据、双 Worker 并发领取、错版本领取/接管、原 Lease 到期后的正确版本接管、前 Execution 密封、部分发布、确认超时、回滚 Worker 缺席后恢复、历史 Task 排空阻断，以及 Shadow 继续原路径。当前超时验证使用时钟数据调整；完整跨容器故障注入、实际 Provider 和 Worker 进程重启/断网仍需单独验证。

## 19. 原 Admin、Phase 1 与 Phase 2 回归

- Python + Chromium 已覆盖 Phase 1 的总览、Provider/Model、Tool、Skill、Task/Run、文件预览、查询安全；Phase 2 的 Worker 证据、探测、诊断、审计、HMAC 和操作预算。
- 原有 Admin 测试验证登录、接口权限、审计返回及权益规则。原 Agent 权益与存量运行回归结果为 69 通过、35 个子用例通过、2 条历史失败。 `test_dynamic_missing_profile_or_input_room_fails_before_reservation` 仍返回 `QUOTA_EXHAUSTED`，预期 `MODEL_INPUT_BUDGET_EXHAUSTED`；`test_sync_settlement_requires_backend_ack_and_keeps_original_outbox` 未产生预期 `GateDenied`。本次保持相关权益逻辑。
- 配置桥接在独立库执行两次配置发布和一次回滚，逐表比较 Policy、Release、Owner、Grant、Usage Ledger、Usage Projection 与权益审计，前后相同。12 条配置操作记录进入独立管理审计。带真实计量与结算的跨容器完整回归尚待验收。

## 20. 生产开放门槛

**生产配置写入不可开放。** 当前已有独立 PostgreSQL 上的 Task 版本、兼容领取、接管、回滚与等待保护证据，以及缓存镜像的隔离 Compose 启动/默认拒绝证据。仍需用本次可复现构建完成真实镜像部署，验证真实诊断凭据、真实 Provider、凭据轮换、多 Worker 并行投放、跨容器故障恢复、结算与 Outbox 连续性、管理审计端到端和原 Admin 全量回归。两条已知基线回归失败需独立结论。生产变量维持默认关闭。

## 21. 限制及后续

- 配置发布由当前协调器和部署系统配合。现阶段没有通用自动部署适配器、独立的多阶段审批工作流或全量 fleet 历史浏览。新旧 Worker 需使用各自的不可变清单、制品和凭据。
- 只读权益影响和正式版本由两个数据库持有。多次核验采用保守阻断；跨服务切换缺少分布式原子快照，需要在首次上线演练使用准入暂停、写入协调和对账。排空不强制关闭任何 Grant。现阶段暂停覆盖整个新任务准入。
- Provider 新协议、连接参数编辑、历史 Tool Schema 比较、Skill 文件的版本化预览以及新制品受控脚本运行尚未完成。现有 Web UI 支持静态登记和发布，不接收可执行源码。隔离测试使用专用测试数据和可控假证据，真实 Provider 与生产环境的诊断未执行。
