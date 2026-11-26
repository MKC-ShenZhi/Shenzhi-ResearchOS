# ShenZhi Agent Management Phase 1 实施与验收

## 1. 版本与范围

设计基线为 dev 的 `60188121277bdeb738f19e6e414d82e386533b6c`，实施基于当前 `chore/docker-compose-infra` 的 `f04e01ac11f95e75f5c29bdfa0e6d4025c94dbc3`。开发前通过祖先检查确认当前提交包含设计基线。当前分支已有 Docker 入口、Provider 配置和权益相关差异，实施按当前代码适配。工作区原有的 [详细设计](agent-management-design.md) 保留。未切换分支、执行迁移、连接生产数据库、提交或推送。

| 模块 | 已交付 |
|---|---|
| Overview | API 往返耗时、观测时间及 API 声明构建修订，Agent/Backend DB 只读探测，Workspace 根目录元数据，Run/Execution、Worker 有效或过期租约、时间窗统计和近期失败。子系统失败可部分展示。 |
| Provider / Model | 真实 Provider ID 和模型关联、仅保留 origin 的端点、凭据存在、配置启用、默认用途、模型能力与身份版本；详情可查看近期模型被动观测。Policy 明确指定版本后提供能力匹配状态。 |
| Tools | API 本地无执行的 ToolSpec 组装、条件与 Schema、能力版本、有限历史补充和最近已开始调用。显示 Worker 已加载、latent、Run 可调用及健康的证据缺失。 |
| Skills | 基于已登记 Skill 的来源、资源摘要、references/scripts 清单、静态完整性和同版本历史激活证据；使用登记名和摘要获取限长 SKILL.md，按纯文本渲染。 |
| Task / Run | 时间和 ID/状态筛选、排序及分页。模型与工具过滤依据已开始的调用，单独展示请求模型。Task 详情显示观测和核验/入账用量；Run 显示 Execution 历史、Event 元数据、Model/Tool/Skill 调用和脱敏错误。 |

## 2. 文件变更

| 文件 | 职责 |
|---|---|
| `apps/admin/src/main.tsx` | 增加独立一级导航和 hash 分派 |
| `apps/admin/src/features/agent/AgentManagement.tsx`、`agent.css` | 管理页面、同源加载、分页、证据状态、筛选、详情与模块样式 |
| `apps/admin/tests/agent-management-smoke.mjs` | Chromium 页面、同源请求、凭据和 GET 边界验收 |
| `apps/agent/src/agent_app/main.py` | 挂载独立 Agent 管理路由 |
| `apps/agent/src/agent_app/api/management.py` | 管理角色、版本化接口、有界分页、错误与 no-store |
| `apps/agent/src/agent_app/management_catalog.py` | Registry、ToolSpec、SkillStore 及受控文档投影 |
| `apps/agent/src/agent_app/management_observations.py` | 仅 SELECT 的任务、执行、观测及健康投影 |
| `apps/backend/app/main.py` | 挂载独立 Admin Agent 路由 |
| `apps/backend/app/api/agent_management.py` | Admin 认证、GET 路由、参数处理与响应 |
| `apps/backend/app/integrations/agent_management.py` | 服务端凭据、超时、响应大小和 DTO 校验 |
| `apps/backend/app/services/agent_management.py` | 部分可用总览、已绑定任务的只读用量和 Policy 证据 |
| `packages/agent-contracts/src/agent_contracts/management.py` | 共享 Management Schema 和状态 |
| `apps/agent/tests/test_management.py`、`test_management_bridge.py` | Agent 独立 SQL 测试、Backend 与 Agent 联调、旧计划和迁移预览回归、浏览器夹具 |
| `apps/agent/.env.example`、`apps/backend/.env.example`、`infra/docker/env/agent.env.example`、`infra/docker/env/backend.env.example` | 声明可选专用管理凭据 |
| `infra/docker/compose.yml` | Worker、Usage Worker 及迁移容器清空该管理凭据 |
| `docs/admin/agent-management-phase1-implementation.md` | 实施及验收记录 |

## 3. API 清单

Backend 前缀为 `/api/v1/admin-console/agent`，Agent 前缀为 `/internal/v2/management`，两个前缀提供相同的 18 个 GET 路径。

| 模块 | GET 路径 |
|---|---|
| Overview | `/overview`、`/workers`、`/workers/{worker_id}` |
| Provider / Model | `/providers`、`/providers/{provider_id}`、`/models`、`/models/{model_id}` |
| Tools | `/tools`、`/tools/{tool_id}` |
| Skills | `/skills`、`/skills/{skill_name}`、`/skills/{skill_name}/document` |
| Task / Run | `/tasks`、`/tasks/{task_id}`、`/tasks/{task_id}/runs`、`/runs/{run_id}`、`/runs/{run_id}/events`、`/runs/{run_id}/calls` |

Model ID 支持 Registry 的 provider/model 路径样式。列表为默认 20、最多 100 项，带绑定查询和资源的 offset 游标，偏移上限 10,000。运行数据变化时分页没有快照一致性保证。Task 和 Overview 时间参数为 `from_at`、`to_at`，带时区，默认近 24 小时、最多 31 天。目录支持 ID 搜索和排序。Backend 可选 `policy_revision` 为 Model、Tool 和 Skill 增加只读授权匹配。Skill 文档需传对应 `resource_digest`。

## 4. 数据来源

| 页面 | 数据来源与含义 |
|---|---|
| Overview / Worker | Agent API 响应及 `AGENT_BUILD_REVISION` 声明值，独立 `SELECT 1`，Workspace 根目录只读元数据，`agent_tasks`、`agent_runs`、`agent_executions` |
| Provider / Model | Agent API 进程的 `load_registry`、`ProviderSpec`、`ModelSpec`、`agent_usage_observations`，可选 Backend 已批准 Policy |
| Tools | 已知无执行 Tool 工厂的 ToolSpec；`agent_calls` 补充最多 200 个已观测 ID，详情出现最近已开始调用；可选 Backend 已批准 Policy |
| Skills | Agent API 进程的 `default_store`、登记的资源根目录及同版本 Skill Call；可选 Backend 已批准 Policy |
| Task / Run | `agent_tasks`、`agent_runs`、`agent_run_events`、`agent_executions`、`agent_calls`、`agent_usage_observations`；Backend 按 Task 和 Owner 核对 `agent_metering_profiles`，校验绑定回执后关联 Projection、Grant、Allocation 和 Ledger |

## 5. 安全与部署

保留同源 Admin Cookie 和本机入口。单独设置 `AGENT_MANAGEMENT_TOKEN`，在 **Agent API 和 Backend** 配置相同值，且须与现有 Agent 执行及服务角色凭据不同。使用现有部署的 `AGENT_INTERNAL_URL`。在 Docker 各自的服务环境文件中配置，迁移和 Worker 容器显式清空该值。令牌缺失时管理目录失败关闭，总览仍可展示 Backend DB 状态。Admin 前端环境不需要该凭据。

Agent 路由按独立内部角色授权，Backend 对响应做类型及字段投影。管理 GET 不调用执行、审批或权益修改路径。Run 事件只含类型、序列与时间等元数据。运行错误映射至允许列表分类。Skill 预览校验登记、文件边界及摘要，前端用 React 文本节点显示 Markdown 源文，浏览器不会加载正文中的远程资源。无数据库表、迁移、套餐 Policy、Grant、权益或原审计变更。

## 6. 实际验证

| 命令或检查 | 结果 |
|---|---|
| `apps/admin: pnpm install --frozen-lockfile` | 通过，锁文件未改 |
| `apps/admin: pnpm typecheck`、`pnpm build` | 通过 |
| `apps/agent: uv run --no-sync pytest -q tests/test_management.py tests/test_management_bridge.py`，设置测试用 Chromium 路径 | 9 通过。包含隔离 SQLite 双服务联调及实际 Chromium 页面验收 |
| `apps/backend: uv run --no-sync python -m unittest discover -s tests -p 'test_admin*.py'` | 14 通过 |
| `apps/backend: uv run --no-sync python -m unittest discover -s tests -p test_agent_entitlements.py` | 5 通过 |
| `apps/agent: uv run --no-sync pytest -q tests/test_formal_plans.py tests/test_a_line_persistence.py tests/unit/test_llm_config_api.py tests/unit/test_export_capabilities.py tests/unit/test_llm_registry.py` | 69 通过、2 失败、35 子测试通过。两条失败均从未修改的当前 HEAD Git 对象解包，在隔离目录中复现 |
| `uvx ruff check --select E9,F63,F7,F82,F401,F811` 对新增 Python 文件，及 `git diff --check` | 通过 |

基线失败为 `test_dynamic_missing_profile_or_input_room_fails_before_reservation`，期待 `MODEL_INPUT_BUDGET_EXHAUSTED`，实际为 `QUOTA_EXHAUSTED`；以及 `test_sync_settlement_requires_backend_ack_and_keeps_original_outbox`，期待 `GateDenied` 但未发生。首次混合了不同 Python 版本的依赖目录导致测试收集失败，修正为项目现有环境后执行上述结果。Agent 业务数据库集成为内存 SQLite 测试，未执行 PostgreSQL 专用集成或生产部署验证。

## 7. 原有 Admin 回归

| 功能 | 验证结果 |
|---|---|
| 登录、退出、会话和写操作门禁 | Backend 原有认证及管理 API 测试通过，Chromium 经实际登录后进入页面 |
| 用户查询、原能力管理 | 原有路由测试通过，包含用户查询投影委派、能力返回和错误。真实 PostgreSQL 用户查询未运行 |
| 套餐预览、发布 | 保留原有路由。隔离联调返回 Basic/Pro/Research，既有 Policy 发布不可变与审批相关用例通过 |
| 单用户及批量分配、停用、恢复 | 原有正式套餐用例覆盖成功、部分失败、重放与存量保护，相关用例通过 |
| 历史账号迁移 | 既有 API 写保护通过，隔离联调预览只返回截止时间前未分配账号；已分配停用账号保留，正式套餐测试覆盖初始化保护 |
| Token、Grant、Permit、用量结算 | 大部分相关用例通过，两条基线失败如第 6 节。已有业务代码保持原样 |
| 权益审计 | Backend 原有读测试及正式套餐/对账相关测试通过，新增管理 GET 无权益审计写入 |

## 8. 已知限制及 Phase 2

Phase 1 无独立 Worker 上报，不能统计所有、在线或空闲 Worker，也不能验证每个 Worker 的 Build、配置及部署清单。API Build 是实例声明。Workspace 只验证元数据和读取条件。主动连通性、凭据有效性、模型健康、Tool Calling 验证和 Skill 依赖执行健康保留未知。Skill 工厂产出的 Tool 只在已存在调用事实或本地安全组装可确认时展示。无 Workspace 根目录时不会为 file Tool 补造组装环境。无计量事实的老任务保留未知。

Phase 2 需要独立 Worker 心跳和 Manifest、主动且有预算的探测、敏感诊断与独立审计。配置信息修改、发布回滚、兼容 Worker 领取和旧任务排空继续属于 Phase 3。建议进入 Phase 2 开发，生产验收仍需专用 PostgreSQL 集成及部署入口验证，另外保留两条基线失败的跟踪。

## 9. 最终验收结论

五个模块均交付只读列表及适用的详情路由，Backend、Agent 和已构建 Admin 页面在隔离环境完成联调。新增功能测试及 Chromium 验收通过。原有 Admin 已执行专项回归，结果及未验证边界如上。没有执行生产写入和迁移。
