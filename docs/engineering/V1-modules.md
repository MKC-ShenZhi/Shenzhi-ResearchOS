# V1 模块边界

- `apps/web/app`：URL 和薄页面入口。保留 `/agents`、`/agents/ask`、`/agents/deep-research`、`/agents/auto-research`、`/agents/deep-search`。
- `features/chat`、`features/deep-research`、`features/auto-research`：各自业务。旧 deep-search 是静态搜索结果原型，归 `features/search`。
- `clients/backend`：HTTP、SSE 和 Next BFF 转发；不在 `lib/api` / `services/backend` 保留重复实现。
- `components/common`：跨 Feature 布局/图谱/静态引用；`components/ui`：基础组件。
- `apps/backend/app/api`：校验、身份边界与响应；`schemas`：输入约束；`services`：实际业务；`core`：配置/身份/错误；`main.py`：应用、路由、生命周期。
- 外部 Research Capability 原则上统一由 ShenZhi FastAPI 按 `api → services → integrations/<capability> → 上游科研组 API` 接入，前端领域 Client 只依赖 ShenZhi Backend Contract，不直接连接科研组服务。
- Knowledge Base 是当前已经落地的实例，按 `api → services → integrations/knowledge → 上游知识底座科研组 API` 调用；`client`、上游 `schemas`、`adapter`、`exceptions` 各自保持边界。Deep Research、Auto Research 尚未建立对应 Integration，后续仅在真实职责出现时按同一规则接入。
- 不为形式建立空 `models`、`clients/ai` 或其他无独立职责的客户端层；有明确职责的科研接口放入对应 `integrations/<capability>`。
- Auth 保持 `apps/web/lib/auth` + Better Auth + PostgreSQL，不迁入 B 的账号实现。

具体 Chat 协议、临时存储边界、配置与迁移取舍见 [Chat 维护指南](../chat/README.md) 和 [迁移记录](../chat/MIGRATION.md)。
