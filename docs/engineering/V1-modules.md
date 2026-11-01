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
- 投稿 · 会议截稿 `/submit` 由 `features/submit` 经 `clients/backend/conferences` 调用 FastAPI `conferences` API；时区换算、当届选择、排序与筛选在 `app/services/conferences.py`，数据为 `scripts/publish_conference_deadlines.py` 生成的打包快照，详见 [会议截稿](../conferences/README.md)。
- 首页论文发现由 `features/search` 的单一无限流经 `clients/backend/discovery`（登录用户为 `clients/backend/recommendations`）调用 FastAPI。Feed 由多个数据源组成：`daily`（候选池离线生成的每日候选）、`trending`（平台热度）、`personal`（个人推荐）、`fallback`（随包快照，只在实时数据源不足时追加）。所有数据源经 `app/services/home_feed/rules.py` 统一准入，由 `app/services/home_feed/composer.py` 按每屏配额组装；新增数据源只需产出候选论文并登记配额。候选池同步与每日候选生成由 API 进程内的调度器负责（`HOME_FEED_SCHEDULER_ENABLED`），首页请求时不访问知识底座。详见 [后端 README · 首页论文数据源](../../apps/backend/README.md#首页论文数据源)。
- 论文卡片：首页 `PaperCard`（`features/search`）与检索类列表的 `KnowledgeResultCard`（检索、会议、基金、Topic、相关论文、阅读历史）共用 `features/knowledge/papers/components/paper-card-layout.tsx` 版式，年份、作者、会议配色与 Topic 选取规则集中在 `features/knowledge/papers/paper-card-model.ts`；数据转换、埋点与底部操作由各自卡片提供。新增论文卡片列表优先复用该版式，不另写一套。

具体 Chat 协议、临时存储边界、配置与迁移取舍见 [Chat 维护指南](../chat/README.md) 和 [迁移记录](../chat/MIGRATION.md)。
