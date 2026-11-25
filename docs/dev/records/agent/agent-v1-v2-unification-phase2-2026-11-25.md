# Agent V1 → V2 通信归并（共享能力切换）

日期：2026-11-25。分支：`feat/agent-V2-merge`。本记录仅跟踪通信层改动；未提交、未推送。

## 边界

- Backend 与 Agent 的新增通信统一使用 `/internal/v2/*`。Web 继续使用现有 Backend `/api/v1/agent/*` 产品入口。
- 将 config、Workspace 创建/文件写入、Session 文件读取、匿名 Workspace 认领及 Admin 能力目录切换到 V2 URL。
- V2 Service 能力继续使用独立 `AGENT_SERVICE_TOKEN`；不把 Service 凭据交给 Gateway、Worker 或 Fact Reader 角色。
- 不改 Runtime、Provider、Tools、Skills、附件解析、权益/计量策略、产品请求与 SSE 格式、数据库模型或数据。
- V1 Task/Run 查询、事件读取、Stop/Steer 回落及 V1 Worker 暂时保留，供已有 V1 任务排空；没有数据库/部署证据证明存量已清空，故本阶段不删除这些兼容路径。

## 改动

- `apps/agent/src/agent_app/api/shared.py` 收口协议无关的 config、Workspace、认领、文件及 Task 序列化处理；V1 与 V2 路由复用同一实现，V2 路由不再依赖 V1 路由模块。
- `apps/backend/app/services/agent_gateway/client.py` 的 V1 适配器只保留历史 Task/Run 查询、事件和控制；抽出不含协议路径的 `AgentHttpClient`，V2 Gateway 不再继承 V1 操作。
- `apps/backend/app/services/agent_gateway/v2.py` 通过独立 Service Gateway 凭据访问上述 V2 路由，不再把 V2 Gateway 请求转发到 V1。
- `apps/backend/app/api/agent.py` 与 `services/identity/anonymous_claim.py` 将产品配置、文件、Workspace 和认领调用改为 V2。
- Admin 能力目录及 Agent 健康检查切换到 V2 路径；更新对应维护文档和 M1 启动健康检查 URL。

## 仍待完成

- V1 内部执行端点和 Worker 仍服务历史 Task/Run。需要部署 V2、停止 V1 新准入、排空 Worker，并核对数据库 Task/Run、未完成 Turn、事件与产物访问后，才可删除。
- M1 演示 Worker 仍是隔离的 V1 Mock Worker，不是生产 V2 通信验收证据。
- Backend 通信/API/Session/Admin 定向测试 57 项通过；Agent V2 配置与 Service 角色路由测试 5 项通过；Python 语法检查及 `git diff --check` 通过。
- 后续共享处理器抽取后，Agent V2/V1 路由与 Workspace 定向测试 31 项及 22 个子测试通过；Backend Gateway 传输定向测试 5 项通过。
- 新增 `scripts/agent_v1_drain_audit.py` 只读核对两库中的 V1 活跃 Task/Run、活跃 Session Turn 与历史 Task 引用；缺少 DSN 时安全失败且不回显连接详情。数据库不可用期间仅验证了脚本语法与缺配置路径。
- 尚未执行真实双库、独立进程、重启恢复或部署凭据验收；当前改动未被视为通过生产运行验收。
