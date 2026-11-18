# Agent Platform 与产品接入

Web 的 `/agents` 和论文问答继续访问 Backend 产品 API。Backend 校验 BFF 与 owner，保存 Session / Turn，解析附件，并通过 `app/services/agent_gateway/` 向独立 Agent API 提交任务。匿名身份和认领沿用 [认证架构](../auth/ARCHITECTURE.md#anonymous-identity-and-claim)。

## 执行边界

- `apps/agent/src/agent_app/api/` 提供受服务凭据保护的内部 API。`control/repository.py` 在 Agent PostgreSQL 中维护 Task、Run、事件、控制和 Outbox。
- `worker/host.py` 领取任务、续租、接收取消和 steer，并调用 `application/composition.py` 装配 Runtime。`execution/` 负责模型、工具、上下文与预算，`extensions/` 管理 Skills 和 Workspace。
- `packages/agent-contracts` 定义 Backend、Agent API 与 Worker 交互所用的契约。Task 对应一次提交，Run 对应一次执行尝试。会话关联的 Task 带 Session 和 Turn ID。见 [共享契约](contracts.md)、[生命周期](lifecycle.md) 和 [用户级调度目标](scheduling.md)。
- Knowledge Tool 通过 `integrations/backend/knowledge.py` 调用 Backend 内部 Knowledge API，再由 Backend 调用知识底座。公共网页、论文来源和模型传输位于 Agent 的 `integrations/`。

## 产品接口

- `/api/v1/agent/sessions` 提供会话管理。`POST /sessions/{id}/run` 使用 Backend 保存的历史启动执行，`GET /sessions/{id}/run/stream` 提供续接。Backend 将 Agent 持久事件投影为产品 SSE 和 Turn。见 [会话持久化](session-persistence.md)。
- `POST /api/v1/agent/run` 支持论文问答等无产品 Session 的兼容调用。配置、附件、工作区、文件、导出、steer 和 stop 继续由 Backend 对 Web 提供。
- 第一方 `deep-research` Skill 位于 `apps/agent/skills/deep-research/`。在 `/agents` 选择该 Skill 或输入 `/research <主题>` 可加载指引。Worker 根据本次 Run 的工具事件定位最后一次成功写入或编辑的 Markdown，在提交 `ExecutionReport` 前从会话 Workspace 读取文件并回填报告种类、完整正文和相对路径。没有符合条件的操作时，运行结果保持原样。Agent Control 持久化结果，Backend 将结果投影为产品 SSE，Web 继续消费 `result.output.report`。独立 `/agents/deep-research` 页面见 [产品说明](../deep-research/README.md)。
- Worker 装配 Runtime 时禁用任意 shell 执行。Agent API 与 Worker 共享持久化 Workspace，Backend 通过 Gateway 请求文件。SSE 缓冲依然属于 Backend 进程，跨进程恢复通过 Agent 持久事件实现，重连与租约接管需要集成验证。

## 配置与验证

独立 API 和 Worker 的配置、启动入口及迁移方式见 [Agent 服务说明](../../apps/agent/README.md)；Backend 与 Web 入口见 [部署与运行环境](../engineering/deployment.md)。模型 Provider 配置见 [LLM API Foundation](../engineering/llm-api-foundation.md)。

Agent Runtime、Skills、Workspace 和模型测试位于 `apps/agent/tests/unit/`。产品 API、Gateway、Session 投影、附件与匿名认领测试位于 `apps/backend/tests/`。进程内替身测试和真实双库联调分别提供各自的验证证据。
