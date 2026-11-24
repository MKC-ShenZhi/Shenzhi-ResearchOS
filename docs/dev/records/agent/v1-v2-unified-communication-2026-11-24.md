# Agent V1 → V2 执行通信统一（第一阶段代码收口）

日期：2026-11-24。分支：`feat/agent-V2-merge`（从 `dev@6018812` 新建，只本地开发，未提交、未推送）。
依据：`Agent V1 V2迁移规划-详细修订.md` 的“新任务内部通信使用 V2、V1 兼容存量”原则。

## 本次改动

| 文件 | 改动 |
| --- | --- |
| `apps/backend/app/api/agent.py` | 新增 `submission_gateway()`，两个产品新任务入口固定走 V2；删除按 Owner 类型选择协议；无状态 `/run` 在解析短时附件前按请求指纹恢复已存 V2 Submission，避免重试依赖过期上传槽；Stop/Steer 先查 V2，仅 404 回落 V1；Session 产物文件/资源继续通过 V1 共享文件接口和 Service 凭据读取，避免混用 V2 Gateway 角色凭据。 |
| `apps/backend/app/services/agent_sessions/service.py` | V2 提交异常区分“确定拒绝”与“结果不确定”：本地授权/准入拒绝（`EntitlementError`）按现有错误语义结束 Turn，其余（超时、5xx、响应丢失）保持 Turn 运行并按原幂等键恢复，不重复创建 Task。恢复时按持久协议标记选择 Gateway，V2 Run 列表查询不再误走 V1。 |
| `apps/backend/app/services/agent_gateway/v2.py` | 提交后（或恢复查询时）的响应校验失败改为 `BusinessError(20004, 'AGENT_RESPONSE_INVALID', 502)`，避免把“远端可能已建 Task”的不确定结果误判为本地确定拒绝；继承的 V1 共享能力按 `/internal/v1/*` 路径委托 Service Gateway，防止把 Gateway 角色凭据发往仅接受 Service 角色的端点。 |
| `apps/web/clients/backend/agent.ts`、`apps/web/features/papers/[id]/use-paper-agent.ts` | Stateless 论文助手保留未收到终态的原始请求体和幂等键；用户重试相同问题时重放同一操作，收到 Agent 终态后清除待恢复操作；新问题使用新键。产品 URL 与 SSE 格式不变。 |
| 测试 | Backend 的 API/Session/Gateway 测试覆盖 V2 提交、Task/Run/事件/控制路由、共享文件仍由 V1 Service Gateway 凭据访问、协议恢复、明确拒绝与不确定提交、无状态过期附件恢复及同 Key 请求指纹冲突。Agent 测试覆盖 V1/V2 Worker 双向领取隔离、drain-only 阻止新 V1 提交但允许旧 Task 领取，以及 V1 admission 未关闭时 V2 拒绝并在同一幂等键重试时成功。`test_task_runs.py`、`test_worker_takeover.py` 的时钟改为当前租约时长加 1 秒，保证接管测试覆盖真正过期的 90 秒租约。 |
| 调用方清点 | Web `/agents` 通过 `apps/web/clients/backend/agent.ts` 调用现有 `/api/v1/agent/sessions/*`、产品 SSE、stop/steer、config、workspace/file 和 export；论文助手 `apps/web/features/papers/[id]/use-paper-agent.ts` 调用 `/api/v1/agent/run`，首次请求生成幂等键，未收到终态时同问题重试复用同一请求体和键。产品请求仍经 Web `/api/v1/*` BFF。Agent `worker/host.py` 按 `AGENT_WORKER_PROTOCOL` 选择 V1 存量或 V2 Worker 接口；Agent Knowledge Adapter 回调 Backend 的受 Service 凭据保护的 Knowledge 端点；Admin 能力目录仍读 Agent `/internal/v1/config`。M1 smoke 使用产品 API，隔离 M1 Mock Worker 仍走 V1，仅用于演示。Backend 另保留 `/api/v2/agent/*` 权益/控制产品入口（当前未发现 Web 调用），不属于本次产品路径迁移。以上调用方未显示有可安全删除的 V1 公共或内部端点。 |
| 文档 | `docs/agent/README.md`、`docs/agent/development.md` 更新执行链路与新提交协议说明。 |

保持不动（按本次范围）：

- 匿名准入与权益策略、`Idempotency-Key` 的要求本身、`AGENT_V2_ADMISSION` 默认值均未改动；本次只删除新提交的 Owner/协议分流（`product_gateway()`），由统一 `submission_gateway()` 取代。
- V1 内部 API、V1 Worker、`AGENT_V1_ADMISSION`/`AGENT_WORKER_PROTOCOL` 语义保留。
- 配置、Workspace、文件读取和匿名认领继续使用 V1 受信内部接口。
- 共享契约、`schema_version=1`、`wire.py`、Session/Turn/Task 数据模型、Web 产品 API/SSE 未改。

## 行为变化与前置条件

1. 新任务（含匿名）统一经 V2 网关提交；匿名 Owner 没有权益行时按现有 fail-closed 返回 `ENTITLEMENT_UNAVAILABLE`（403），未新增匿名准入旁路。
2. 新提交需要稳定 `Idempotency-Key`：Web 两个入口与 `scripts/agent_m1_smoke.py` 已携带；其它直接调用 `/api/v1/agent/run` 的客户端需补。
3. Backend `AGENT_V2_ADMISSION` 默认仍为 `disabled`；部署新版代码前需完成 V2 准入、角色凭据、Worker（`AGENT_WORKER_PROTOCOL=2`）与用量进程配置，否则新任务会 fail-closed。
4. V2 确定拒绝现在会结束产品 Turn；不确定提交仍保留 Turn 供恢复，与 V1 行为一致。

## 验证

在 `apps/backend` 使用现有虚拟环境执行：

```powershell
uv run --frozen --no-sync python -m unittest tests.test_agent_api tests.test_agent_sessions `
  tests.test_agent_sse_retries tests.test_agent_sse_tail tests.test_agent_contracts `
  tests.test_agent_gateway_transport tests.test_anonymous_claim
```

Backend 相关测试结果：71 tests OK（含本地 V2 Wire 校验拒绝后 Turn 收敛、确定授权拒绝、不确定提交恢复、过期附件恢复、Gateway 路由及共享 V1 Service 凭据隔离覆盖）。

Web `npm test`：446 tests passed（含论文助手失败后同问题复用原幂等键/请求体和 Backend 客户端显式幂等键传递覆盖）；改动文件 ESLint 通过；刷新 Next route types 后 `npm run typecheck` 通过。

Agent 全量 `pytest -q`：261 passed、58 skipped、7 failed。V1/V2 Worker 双向隔离、V2 Worker 端到端提交、V1 drain-only 领取存量 Task、以及 V1 admission 未关闭时 V2 拒绝等新增定向用例通过；此前 V1 Task Run 与 Worker takeover 测试也通过。全量失败仍在未改动的 Agent 生产代码，分类如下：

- 用量结算与配额断言 2 项：`test_sync_settlement_requires_backend_ack_and_keeps_original_outbox`、`test_dynamic_missing_profile_or_input_room_fails_before_reservation`。
- Runtime 预算断言 5 项：`test_agent_fast_search.py` 仍期望 fast 12 次/180 秒、其他模式 900 秒；当前实现分别为 20 次/300 秒和 1800 秒。

显式运行 Agent 的 PostgreSQL A-line / formal-plan 集成测试文件时，54 项均因 `two isolated local A-line PostgreSQL databases not selected` 而跳过；这与当前两个隔离测试库 URL 未配置一致，不计作通过的双库验收。

## 未完成 / 后续

- 部署环境切换（V2 准入、drain_only、双 Worker、Usage Worker）与真实双库验收未执行。双库测试要求显式设置 `AGENT_A_LINE_TEST_DATABASE_URL` 与 `BACKEND_A_LINE_TEST_DATABASE_URL`；当前进程及项目本地配置均没有这两个测试连接（Backend `.env` 仅配置普通 `CHAT_DATABASE_URL`，未复用）。Docker daemon 未运行，此前临时验收 PostgreSQL 使用的 55432 端口当前也没有监听。检测到本机 5432 有 PostgreSQL 监听，但没有将其假定为隔离测试库，也未连接或改动任何数据库。
- 发布切换需要协调 Backend V2 admission 与 Agent `AGENT_V1_ADMISSION=drain_only`：前者过早会遇到 Agent 403，后者过早会让旧 Backend 的 V1 提交收到 409；V1 Worker 继续运行直至存量排空。
- `/api/v2/agent/*` 正式权益产品入口保留原契约，不从 `/api/v1/agent/*` 迁移或删除；Web 当前未调用它。若该入口也要统一客户侧路径，需要另有调用方与产品兼容决策。
- M1 Mock 本地演示 `scripts/agent_m1_demo.py` 仍使用隔离的 V1 Mock Worker；V2 正式路由需要计量/角色凭据，演示脚本没有获批的 V2 Mock 准入路径。本演示不作为统一 V2 通信验收证据，保留其 V1 隔离演示用途。
- V1 执行路由退役需等 V1 新提交关闭、存量排空、历史读取验证后再按调用证据逐项删除。
