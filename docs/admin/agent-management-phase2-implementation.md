# ShenZhi Agent Management Phase 2 实施与验收

## 1. Phase 1 最终验收

**代码验收通过。** 保持当前检出分支 `chore/docker-compose-infra`，HEAD 为 `f04e01ac11f95e75f5c29bdfa0e6d4025c94dbc3`。该提交包含设计基线 `60188121277bdeb738f19e6e414d82e386533b6c`。Phase 1 功能来自工作区中的未提交改动，验收时完整保留。[设计文档](agent-management-design.md) 和 [Phase 1 实施报告](agent-management-phase1-implementation.md) 均未改写。

Phase 1 重新通过 TypeScript、Vite 构建、9 项新增测试（含 Chromium 和跨服务联调）、Backend Admin 14 项及权益 5 项。Agent 已有正式套餐、持久化及 Registry 回归再次得到 69 通过、2 失败及 35 子测试通过。两条失败已在未修改的 HEAD 解包副本复现。

## 2. Phase 1 逐文件 Diff 审查

| 路径 | 检查结果 |
|---|---|
| `apps/admin/src/main.tsx` | 只增加 Agent 导航和独立 hash 分支，既有五个管理入口保留。 |
| `apps/admin/src/features/agent/AgentManagement.tsx` | 五个模块使用已认证的同源 Admin Client。Skill 文档纯文本展示，任务投影只显示 DTO。 |
| `apps/admin/src/features/agent/agent.css` | 样式限定在 Agent 管理区。 |
| `apps/admin/tests/agent-management-smoke.mjs` | 实际 Chromium 请求核对同源、GET 边界和无 Authorization 头。 |
| `apps/agent/src/agent_app/main.py` | 新增管理路由注册，原执行路由保留。 |
| `apps/agent/src/agent_app/api/management.py` | Phase 1 路径均为 GET，管理角色与传统 Worker/Gateway 分离，分页和响应有界。 |
| `apps/agent/src/agent_app/management_catalog.py` | 仅构造工具定义，Skill 从登记资源读取。Provider 只暴露脱敏 origin 和凭据存在状态。 |
| `apps/agent/src/agent_app/management_observations.py` | 查询使用既有运行表，只执行 SELECT；报告和事件体不输出。 |
| `apps/backend/app/main.py` | 管理 router 独立注册，原认证错误和 no-store 范围保留。 |
| `apps/backend/app/api/agent_management.py` | 每条路由依赖管理员会话，与旧 Admin 路径无冲突。 |
| `apps/backend/app/integrations/agent_management.py` | 管理密钥只在 Backend 到 Agent 的 HTTP 请求发送，固定 Agent 路径、错误白名单及响应体上限。 |
| `apps/backend/app/services/agent_management.py` | 只读获取 Policy、核对绑定和汇总结算；无业务写入。 |
| `packages/agent-contracts/src/agent_contracts/management.py` | 独立 DTO，对已有协议无覆盖。 |
| `apps/agent/tests/test_management.py`、`test_management_bridge.py` | 断言 GET 只执行 SELECT。PostgreSQL 试跑发现 SQLite 夹具未显式按 FK 顺序 flush，已修复夹具并在隔离 PostgreSQL 重跑通过。 |
| `apps/agent/.env.example`、`apps/backend/.env.example`、`infra/docker/env/agent.env.example`、`infra/docker/env/backend.env.example` | 只放示例字段，未引入实际服务凭据。 |
| `infra/docker/compose.yml` | Worker、Usage Worker 及迁移进程显式清空管理凭据。Admin 容器无该凭据环境注入。 |
| `docs/admin/agent-management-design.md`、`agent-management-phase1-implementation.md` | 原设计、已知限制和回归记录保留。 |

原有套餐发布、用户查询、分配/停用/恢复、历史迁移、Grant/Permit、Usage Ledger 及权益审计的业务文件和表未发生改动。

## 3. Docker 与 PostgreSQL 验收

- **隔离 PostgreSQL 18 通过。** 使用 WSL 中独立临时集群、随机临时测试凭据、仅 loopback 监听和分离的 Agent/Backend 数据库。Phase 1 的异库联调实测管理认证、目录和 Task/Run 查询、只读 SQL 及 Backend 用量摘要。
- **Phase 2 真实 TCP 联调通过。** 使用真实 Backend、Agent API 和独立空闲 Worker，检验 Admin 登录、API/DB 总览、Provider/Model/Tool/Skill 目录、Worker 注册及清单、主动静态检查、审计关联、受控诊断和原套餐列表。Worker 进程环境只传上报和执行凭据。未调用生产 Provider。
- **Docker Compose 实跑未完成。** Windows 和 WSL 无 Docker/Podman CLI。已静态解析本机 Compose 文件并断言 Admin 共享 Backend 网络、loopback 端口、生产 PostgreSQL 无端口映射，以及各角色凭据清空规则。实际容器互通和注入效果仍需部署环境确认。保留宿主现有服务及 Docker volumes。

## 4. Phase 2 功能交付

| 模块 | 已实现 |
|---|---|
| Worker 心跳与 Manifest | Worker 启动创建独立上报协程。每次进程运行生成实例 ID。周期上报、失败重试、退出时尽力上报离线。服务端收到时间判断在线/陈旧/离线，缺证据保持未知。支持列表、详情、历史及两个 Worker 清单差异。 |
| Provider / Model 健康检查 | 静态检查、指定 Provider 连通/认证、模型登记检查、最小实际请求、Streaming、仅验证 Tool Calling 的返回。每次由管理员主动触发，显示结果、来源、耗时、预算、版本、过期时间及历史。 |
| Tool 健康检查 | 已登记 Schema 校验，Workspace 读依赖及第一方 Backend 健康入口探测。无安全独立检查的 Tool 返回 unsupported，外部上游未能证明时返回 unknown。保留 Phase 1 真实调用观测。 |
| Skill 健康检查 | Frontmatter 与受控资源路径、资源摘要、可选引用和脚本声明、Python 包元数据依赖及在线 Worker 版本对比。展示 Worker 分布及版本。检查不执行 Skill 工厂和脚本。 |
| 独立管理审计 | 健康检查、Worker 和运行故障诊断，以及访问受限诊断的审计单独入库。按操作者、操作、目标、结果、时间筛选并可从结果跳转审计。 |
| 敏感诊断 | 通过独立开关和 Admin 写保护开启。只输出允许列表内的时间、证据来源、稳定分类、关联 Worker、Run/Call ID 和已核实的构建/配置修订，界面提供对应排查方向。发起及查看分别记录。 |

## 5. Worker 证据

每个 Worker 配置独立上报令牌，Agent API 的目录按 Worker ID 绑定该令牌的 SHA-256。上报令牌与已有执行角色和管理角色隔离。重复同一序列和请求返回原接收时间；冲突内容、回退序列和被替换的实例拒绝。默认每 15 秒上报，45 秒陈旧、90 秒离线，数据保留 7 天。数据库应答同时确认是否需要重发 Manifest。

清单区分该 Worker 能载入的 Model/Skill、编排基础 Tool、需运行上下文的 Tool，以及当前 Run 已启用工具的独立观察。当前 Run 的 Tool 信息来自已构造的 ToolRegistry，缺少采样时保持未知。心跳数据完全独立于任务领取和租约，失联不会触发本模块的调度动作。

## 6. Provider / Model 健康边界

只允许配置中登记的 Provider 和 Model，管理员不能传目标 URL、prompt、工具参数或密钥。探测使用专用 Provider 凭据，拒绝与 Registry 的运行凭据相同。公网 HTTPS 入口固定解析后验证地址、固定连接地址保留 TLS SNI/Host，禁用重定向和环境代理。最多 128 KiB 响应，Provider 网络探测 4 秒上游时限，整个 Agent 检查 7 秒有界。Backend 对在线检查独立串行衔接、每目标 60 秒限频和每日 4,096 Token 预留预算；每次发生成模型调用预留 1,024，固定监测输入受字节上限约束，输出请求上限 32 Token。上游真实计费受独立诊断凭据的服务商配额限制，应用内预留不代替上游账单。结果只保存摘要，未知响应不重放同一个已受理操作 ID。

Provider 网络探测使用 OpenAI-compatible `/models`。不支持该入口或不承诺正确 Token 限制的供应商需要专门批准的兼容方案。真实代码路径已用 MockTransport 验证请求构造、模型响应校验和失败分类；隔离部署只做静态检查，生产 Provider 未验证。

## 7. Tool / Skill 检查边界

Workspace 只检查根目录存在及可读状态。知识工具检查凭据存在和 Backend liveness，下游知识系统仍可能未知。没有独立安全处理器的工具不执行原工具。Skill 查验的可选声明为 `references`、`scripts` 相对文件名列表，以及 `dependencies` Python distribution 名称列表，路径限制在已登记目录内。缺少声明时显示未知。第三方外部依赖没有通用联网检查，不加载任意代码，不发起外部任务。

## 8. 审计与诊断安全

审计保存稳定管理员身份、请求与操作 ID、目标、状态、原因、检查结果及 Worker/修订证据。不落用户请求体。目标未被 Agent 证据确认时使用指纹。对行内容使用独立 Backend 密钥生成 HMAC，读取时校验，错误时失败关闭。该设计能检测行内容更改；外部归档仍是防止整个数据集被删除或重放的生产保障。审计保留 90 天，Worker 记录在上报时清理过期项；两者均为写入触发清理。常规脱敏 GET 继续无业务写入，重要的受限诊断读取必须通过独立 POST 并留下审计。原 `agent_entitlement_audit` 未读写扩展。

## 9. 新增接口

| 服务和前缀 | 新增路径 | 权限 |
|---|---|---|
| Agent `/internal/v2/worker-reports` | PUT `/{worker_id}` | 每 Worker 专用上报凭据 |
| Agent `/internal/v2/management` | GET `/worker-evidence`、`/worker-evidence/{worker_id}`、`/worker-evidence/{worker_id}/manifests`、`/capability-evidence`；POST `/checks`、`/diagnostics` | Backend 服务管理凭据 |
| Backend `/api/v1/admin-console/agent` | GET `/worker-evidence`、`/worker-evidence/{worker_id}`、`/worker-evidence/{worker_id}/manifests`、`/capability-evidence`、`/audit`、`/audit/{audit_id}` | 管理员会话 |
| 同一 Backend 前缀 | POST `/checks` | 管理员会话 + 既有 Admin 写门禁 |
| 同一 Backend 前缀 | POST `/diagnostics`、`/diagnostics/{audit_id}/view` | 写门禁 + Backend 敏感诊断开关 |

## 10. 新表、迁移及部署

Agent 新表 `agent_management_worker_instances`、`agent_management_worker_manifests`，增量迁移 `0004_agent_management`。Backend 新表 `agent_management_audit`（同时保存脱敏检查历史），增量迁移 `029_agent_management`。两条迁移均用独立 PostgreSQL 完成 upgrade → downgrade → upgrade。未对任何生产库执行迁移。

| 配置项 | 注入方式 |
|---|---|
| `AGENT_MANAGEMENT_TOKEN` | Backend 与 Agent API 同值，区分现有其他服务凭据 |
| `AGENT_WORKER_REPORT_IDENTITIES` | Agent API 的 JSON 对象，键是稳定 Worker ID，值是该 Worker 随机令牌的 SHA-256 |
| `AGENT_WORKER_ID`、`AGENT_WORKER_REPORT_TOKEN` | 每个 Worker 单独注入；多副本必须配不同 ID 和独立令牌 |
| `AGENT_WORKER_REPORT_INTERVAL_SECONDS`、`AGENT_WORKER_STALE_SECONDS`、`AGENT_WORKER_OFFLINE_SECONDS`、`AGENT_WORKER_REPORT_RETENTION_DAYS` | 观察时效与清理配置 |
| `AGENT_CONFIG_REVISION`、`AGENT_BUILD_REVISION` | 部署标识，未设置时对应字段未知或显示已有路由修订 |
| `AGENT_HEALTHCHECK_PROVIDER_KEYS` | Agent API 专用，Provider ID 到独立诊断凭据的 JSON 映射 |
| `ADMIN_AGENT_AUDIT_SECRET` | Backend 独立 HMAC 密钥，至少 32 字符。轮换前应保留现存记录验证能力 |
| `ADMIN_AGENT_DIAGNOSTICS` | Backend 开关，默认关闭 |

## 11. Phase 2 文件变更

- **Admin**：`apps/admin/src/features/agent/AgentDiagnostics.tsx`、`AgentManagement.tsx`、`apps/admin/tests/agent-management-smoke.mjs`。
- **Agent**：`apps/agent/src/agent_app/main.py`、`api/management.py`、`infrastructure/management_models.py`、`management_workers.py`、`management_checks.py`、`management_diagnostics.py`、`worker/management_reporter.py`、`worker/host.py`、`worker_main.py`、`apps/agent/migrations/env.py` 和 `versions/0004_agent_management.py`。
- **Backend**：`apps/backend/app/main.py`、`api/agent_management_phase2.py`、`integrations/agent_management.py`、`models/agent_management.py`、`services/agent_management_audit.py`、`apps/backend/migrations/env.py` 和 `versions/029_agent_management.py`。
- **契约及测试**：`packages/agent-contracts/src/agent_contracts/management_phase2.py`、`apps/agent/tests/test_management_phase2.py`，以及 Phase 1 夹具 `test_management.py`、`test_management_bridge.py`。
- **部署与交付**：`apps/agent/.env.example`、`apps/backend/.env.example`、`infra/docker/compose.yml`、`infra/docker/env/agent.env.example`、`infra/docker/env/backend.env.example`、本文。

## 12. 测试及回归结果

| 命令或验证 | 最终结果 |
|---|---|
| `apps/admin: pnpm typecheck`、`pnpm build` | 通过 |
| `apps/agent: uv run --no-sync pytest -q tests/test_management.py tests/test_management_bridge.py tests/test_management_phase2.py`，设置 `SHENZHI_TEST_CHROME` | 22 通过，含 Phase 1 和 Phase 2 Chromium 验收 |
| `apps/backend: uv run --no-sync python -m unittest discover -s tests -p 'test_admin*.py'` | 14 通过 |
| `apps/backend: uv run --no-sync python -m unittest discover -s tests -p test_agent_entitlements.py` | 5 通过 |
| `apps/agent: uv run --no-sync pytest -q tests/test_formal_plans.py tests/test_a_line_persistence.py tests/unit/test_llm_config_api.py tests/unit/test_export_capabilities.py tests/unit/test_llm_registry.py` | 69 通过、2 条基线失败、35 子测试通过 |
| `uvx ruff check --select E9,F63,F7,F82,F401,F811` 对管理及相关 Python 文件 | 通过。两份旧迁移 env 文件保留既有模型注册导入，按语法及关键错误项检查 |
| `git diff --check` 与真实 Compose YAML 静态断言 | 通过 |
| Agent/Backend 隔离 PostgreSQL `alembic upgrade head`、回退到前一版本后重新升级 | 通过 |
| PostgreSQL 隔离 TCP 与后台 Worker 验收 | 通过 |

旧失败为 `test_dynamic_missing_profile_or_input_room_fails_before_reservation`（旧测试期待 `MODEL_INPUT_BUDGET_EXHAUSTED`，当前返回 `QUOTA_EXHAUSTED`）和 `test_sync_settlement_requires_backend_ack_and_keeps_original_outbox`（旧测试期待 `GateDenied`）。未修改相关断言或权益代码。Admin 登录、用户查询、能力页、套餐预览/发布、分配/批量分配、停用/恢复、迁移预览、原审计和既有 Grant/Permit/结算获得专项回归覆盖；结算中的上述两条失败继续跟踪。

## 13. 限制与最终验收

- Phase 1 **通过代码验收与隔离 PostgreSQL 验收**，Docker **仅完成静态核验**。Phase 2 六模块的代码、浏览器与隔离联调通过。
- Worker 在线状态有真实心跳证据。主动检查执行受控检查逻辑，网络鉴权、模型协议、预算和错误路径通过替身测试；生产凭据、真实 Provider 能力和容器部署未验收。
- 独立审计与受控诊断均不写原权益审计。未发现测试范围内新增的凭据泄漏或越权，生产安全还需部署验证、凭据交接、网络策略和审计归档验证。
- 可进入 Phase 3 的技术开发和评审。开放生产配置写入之前仍需完成真实 Compose 验收、生产 Provider 检查口径、部署回滚和按版本的 Worker 兼容领取/接管验证。现有领取、Lease、套餐发布及结算保持原流程。
