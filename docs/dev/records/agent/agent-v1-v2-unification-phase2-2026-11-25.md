# Agent V1 → V2 通信归并（共享能力切换）

日期：2026-11-25。分支：`feat/agent-V2-merge`。本记录仅跟踪通信层改动；未提交、未推送。

## 边界

- Backend 与 Agent 的新增通信统一使用 `/internal/v2/*`。Web 继续使用现有 Backend `/api/v1/agent/*` 产品入口。
- 将 config、Workspace 创建/文件写入、Session 文件读取、匿名 Workspace 认领及 Admin 能力目录切换到 V2 URL。
- V2 Service 能力继续使用独立 `AGENT_SERVICE_TOKEN`；不把 Service 凭据交给 Gateway、Worker 或 Fact Reader 角色。
- 不改 Runtime、Provider、Tools、Skills、附件解析、权益/计量策略、产品请求与 SSE 格式、数据库模型或数据。
- V1 Task/Run 查询、事件读取、Stop/Steer 回落及 V1 Worker 暂时保留，供已有 V1 任务排空；没有数据库/部署证据证明存量已清空，故本阶段不删除这些兼容路径。

## 改动

- `apps/agent/src/agent_app/api/v2.py` 暴露共享能力的 V2 Service 路由，直接复用现有 handler，保持原有业务实现。
- `apps/backend/app/services/agent_gateway/v2.py` 通过独立 Service Gateway 凭据访问上述 V2 路由；不再把 V2 Gateway 请求转发到 V1。
- `apps/backend/app/api/agent.py` 与 `services/identity/anonymous_claim.py` 将产品配置、文件、Workspace 和认领调用改为 V2。
- Admin 能力目录及 Agent 健康检查切换到 V2 路径；更新对应维护文档和 M1 启动健康检查 URL。

## 仍待完成

- V1 内部执行端点和 Worker 仍服务历史 Task/Run。需要部署 V2、停止 V1 新准入、排空 Worker，并核对数据库 Task/Run、未完成 Turn、事件与产物访问后，才可删除。
- M1 演示 Worker 仍是隔离的 V1 Mock Worker，不是生产 V2 通信验收证据。
- 尚未执行本地自动化测试、真实双库、独立进程或服务凭据验收；当前改动未被视为通过运行验收。
