# Agent V1 → V2 通信归并（共享能力切换）

日期：2026-11-25。分支：`feat/agent-V2-merge`。本记录仅跟踪通信层改动；未提交、未推送。

## 退役首版验收结论

- 代码现状已统一为 V2：Backend 产品入口 `/api/v2/agent/*`，Backend↔Agent 执行与共享能力通信 `/internal/v2/*`。
- Agent V1 router、Backend V1 Gateway adapter/回落逻辑、Worker V1 协议选择、V1 admission 配置及 V1 Mock 演示脚本已移除；生产/演示环境设置旧协议变量不会恢复 V1 路径。
- Backend 新 Turn 固定记录 V2 并带安全恢复快照；旧终态 Turn 仅重放 Backend 已有投影，旧运行不再调用 Agent，过期旧运行由 Backend 标记失败。保留历史数据库数据，不主动清理 Task/Run/Turn/Event。
- 继续保留 `AGENT_SERVICE_TOKEN` 作为 V2 Service 角色凭据；Gateway、Worker、Fact Reader 等角色凭据仍隔离。
- V2 Worker 的 heartbeat/control 可读取取消意图；模型调用启动仍按默认策略拒绝取消中的 Task。
- 变更未包含生产部署、双库历史数据处理、真实模型能力改造或远端 Git 操作。

## 改动

- `apps/agent/src/agent_app/api/shared.py` 收口协议无关的 config、Workspace、认领、文件及 Task 序列化处理；V2 路由直接复用共享处理器，不依赖 V1 路由模块。后续首版退役又从 V1 路由移除了不再使用的 config、Workspace、认领和文件服务端点。
- `apps/backend/app/services/agent_gateway/client.py` 的 V1 适配器只保留历史 Task/Run 查询、事件和控制；抽出不含协议路径的 `AgentHttpClient`，V2 Gateway 不再继承 V1 操作。
- `apps/backend/app/services/agent_gateway/v2.py` 通过独立 Service Gateway 凭据访问上述 V2 路由，不再把 V2 Gateway 请求转发到 V1。
- `apps/backend/app/api/agent.py` 与 `services/identity/anonymous_claim.py` 将产品配置、文件、Workspace 和认领调用改为 V2。
- Admin 能力目录及 Agent 健康检查切换到 V2 路径；更新对应维护文档和 M1 启动健康检查 URL。
- Agent `main.py` 只挂载 V2 内部路由；V2 claim 要求 schema 与 execution 身份，并固定使用 Worker token。删除 `agent_app/api/routes.py` 与 V1 Mock launcher/smoke。
- Backend 删除 V1 网关、404 协议回退与 Session V1 执行恢复；新增旧 Turn 本地重放/410 退役回归覆盖。V2 `task_runs` 响应继续通过共享 wire model 校验。
- Docker/native 环境模板、Compose 配置和当前部署文档清除 V1 admission/Worker protocol 选择；`prepare-env.py` 会从旧 Docker env 中剔除这两个退役变量。

## 验收结果与运行环境限制

- Agent 全量测试：281 passed、59 skipped、129 子测试通过；Backend 全量测试：536 passed、79 skipped；Docker prepare-env：19 passed；退役相关 Agent/Backend 定向测试通过；`git diff --check` 通过。
- M1 V1 Mock launcher 已退役；当前仓库没有运行中的 V2 Mock admission fixture，`docs/agent/local-demo.md` 已说明此状态。
- 新增 `scripts/agent_v1_drain_audit.py` 只读核对两库中的 V1 活跃 Task/Run、活跃 Session Turn 与历史 Task 引用；缺少 DSN 时安全失败且不回显连接详情。数据库不可用期间仅验证了脚本语法与缺配置路径。
- **未通过/未验证的生产门槛：** 尚未在只读真实双库运行 drain audit；未取得入口/Backend/Agent 访问日志证明外部旧调用方为零；未在部署环境停止旧实例；未完成真实双 PostgreSQL、独立进程、重启恢复与角色凭据验收。源代码 V1 已退役，不等于生产集群已完成切换。
- 当前分支 `feat/agent-V2-merge`；变更未提交、未推送、未合并到 main。
