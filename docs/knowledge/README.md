# 知识底座接入说明

本文说明 ShenZhi Knowledge V1（论文、学者、主题、Funding 候选/关联检索与论文关系图谱）的
工程边界、运行配置和稳定契约。科研组 Knowledge Base 是外部 Capability：
ShenZhi 只调用、隔离并适配，不修改其内部实现。

## 调用链

```text
Browser
  ↓ same-origin
Next.js /api/v1/*（BFF）
  ↓ server-side forwarding + Better Auth/BFF credential
FastAPI /api/v1/knowledge/*
  ↓
services/knowledge/service.py
  ↓
integrations/knowledge（client / schemas / adapter / exceptions）
  ↓
External Knowledge Base
```

浏览器只能访问同源 Next.js BFF，不能直接请求 FastAPI 或外部知识库。
外部知识库地址只允许存在 Backend 服务端配置中。

## 代码边界

### Web

| 路径 | 职责 |
|---|---|
| `apps/web/clients/knowledge/types.ts` | Paper / Scholar / Related Search / Graph / Error 的前端 wire type |
| `apps/web/clients/knowledge/client.ts` | `KnowledgeClient` 与 `KnowledgeClientError` |
| `apps/web/clients/knowledge/bff.ts` | 调用同源 `/api/v1/knowledge/*`，解析正式错误契约 |
| `apps/web/clients/knowledge/mock.ts` | 显式开发、测试和 demo fixture 使用的 Mock Client |
| `apps/web/clients/knowledge/index.ts` | Client 工厂；默认 BFF，显式 `source=mock` 才启用 Mock |
| `apps/web/features/knowledge/retry.ts` | Knowledge 查询的局部 retry predicate |
| `apps/web/features/knowledge/{search,paper,graph,scholars,topics,funding}` | 页面、交互和展示逻辑 |
| `apps/web/features/knowledge/components/knowledge-dashboard.tsx`、`lib/overview-cache.ts` | `/knowledge` 总览、混合检索入口及按身份复用的概览请求缓存 |
| `apps/web/features/knowledge/papers` | 我的文献（收藏、文件夹、阅读历史、点赞与收藏面板）；共用论文卡片版式 `components/paper-card-layout.tsx` 与 `paper-card-model.ts` |
| `apps/web/features/knowledge/interactions` | 收藏人数、论文点赞、主题关注的批量读取、写入 hook 与按钮 |
| `apps/web/features/knowledge/{institutions,patents}` | 兼容路由使用的原型页面，不进入正式导航 |
| `apps/web/features/papers/[id]` | 统一论文详情、PDF 阅读器与论文助手 |

### Backend

| 路径 | 职责 |
|---|---|
| `apps/backend/app/api/knowledge.py` | `/api/v1/knowledge/*` HTTP 边界、鉴权和错误状态 |
| `apps/backend/app/api/paper_resource.py` | 仅按可信 `paperId` 提供同源 PDF Range 字节流 |
| `apps/backend/app/services/knowledge/service.py` | Knowledge 业务服务边界 |
| `apps/backend/app/services/knowledge/cache.py` | 论文详情的进程内 TTL 缓存（10 分钟，最多 1024 条），供详情、批量论文与推荐特征共用 |
| `apps/backend/app/services/topics/` | OpenAlex 目录缓存和校验（`openalex.py`），以及历史主题/创作者元数据（`catalog.py`、`registry.py`） |
| `apps/backend/app/services/library/` | 收藏、阅读历史、私有论文、点赞、主题关注、会议关注等账号级数据 |
| `apps/backend/app/services/paper_resource/service.py` | PDF Provider 选择与资源用例编排 |
| `apps/backend/app/integrations/paper_resource/` | OpenReview URL 适配及外部 HTTP 校验与读取 |
| `apps/backend/app/schemas/paper_resource.py` | 浏览器可消费的 PDF 资源状态契约 |
| `apps/backend/app/integrations/knowledge/client.py` | 外部 HTTP、timeout 和外部异常映射 |
| `apps/backend/app/integrations/knowledge/schemas.py` | 外部 Knowledge Base transport schema |
| `apps/backend/app/integrations/knowledge/adapter.py` | 外部 snake_case/异构字段到 ShenZhi 契约的适配与 normalization |
| `apps/backend/app/integrations/knowledge/exceptions.py` | 集成异常与正式错误类别 |

Backend 不提供自动 Mock fallback。未配置或不可用的外部 Knowledge Base
会返回真实的 `UPSTREAM_UNAVAILABLE` / `TIMEOUT` 等错误。

## 配置

Web（`apps/web/.env.example`）：

```dotenv
# 默认/正式运行使用 BFF；仅显式开发、测试或 demo 时使用 mock。
NEXT_PUBLIC_KNOWLEDGE_SOURCE=bff
```

`NEXT_PUBLIC_KNOWLEDGE_SOURCE=mock` 才启用 `MockKnowledgeClient`；未配置或
其他值都使用 BFF。BFF 请求失败时不会切换到 Mock。

Backend（`apps/backend/.env.example`）：

```dotenv
KNOWLEDGE_BASE_API_URL=
KNOWLEDGE_BASE_TIMEOUT_SEC=30
# 上游检索接口接受的最大结果窗口
KNOWLEDGE_BASE_SEARCH_MAX_TOP_K=100
PAPER_RESOURCE_TIMEOUT=30
PAPER_MAX_SIZE_MB=150
# OpenReview PDF Provider；账号可选
OPENREVIEW_API_BASE_URL=https://api2.openreview.net
OPENREVIEW_USERNAME=
OPENREVIEW_PASSWORD=
```

`KNOWLEDGE_BASE_API_URL` 和 Backend 的 BFF secret 只能注入服务端环境，不能
使用 `NEXT_PUBLIC_` 前缀，也不能出现在浏览器 Network 请求中。

## HTTP API

| 能力 | ShenZhi API | 外部 API |
|---|---|---|
| 论文检索 | `POST /api/v1/knowledge/search` | `POST /api/retrieval/search` |
| 知识库总览 | `GET /api/v1/knowledge/overview` | `GET /api/knowledge/papers/summary`、`GET /api/knowledge/research-assets/summary`，并聚合学者、Subject、Funding 检索 |
| 个人概览 | `GET /api/v1/knowledge/personal-overview` | 无（读取 ShenZhi 收藏文件夹与最近阅读；匿名返回 `authRequired`） |
| 混合检索 | `POST /api/v1/knowledge/overview/search` | 并发调用论文、学者、Subject、Funding 检索；`project`、`patent`、`graph` 标为不支持 |
| 会议目录 | `GET /api/v1/knowledge/conferences` | `GET /api/papers/venues` |
| 按会议和年份浏览论文 | `GET /api/v1/knowledge/papers?conference=...&year=...&limit=20&offset=0` | `GET /api/papers` |
| 论文详情 | `GET /api/v1/knowledge/paper?paperId=...` | `GET /api/kg/paper?paperId=...` |
| 论文图谱 | `GET /api/v1/knowledge/graph?paperId=...&depth=1\|2` | `GET /api/kg/graph?paperId=...&depth=1\|2` |
| 学者搜索 | `GET /api/v1/knowledge/scholars/search?q=...&limit=20&offset=0` | `GET /api/retrieval/scholars/search?q=...&limit=20&offset=0` |
| 学者详情 | `GET /api/v1/knowledge/scholars/{scholarId}` | `GET /api/retrieval/scholars/{scholar_id}` |
| Topic 目录 / 详情 / 关联论文 | `GET /api/v1/knowledge/topics`、`GET /api/v1/knowledge/topics/{topicId}`、`GET /api/v1/knowledge/topics/{topicId}/papers` | 默认 `/api/v1/topics/tree`、`/api/v1/topics/{topicId}`、`/api/v1/topics/{topicId}/papers` |
| 历史创作者资料 | `GET /api/v1/knowledge/creators/{creatorId}` | 后端历史目录 `topic_catalog.json` |
| 论文主题词检索 | `GET /api/v1/knowledge/subjects/search?subject=...&offset=0&limit=10` | `GET /api/retrieval/search/by-subject?subject=...&offset=0&limit=10` |
| Funding 候选检索 | `GET /api/v1/knowledge/fundings/search?q=...&limit=20&offset=0` | `GET /api/retrieval/fundings/search?q=...&limit=20&offset=0` |
| Funding 关联论文 | `GET /api/v1/knowledge/funding/search?funding=...&topK=10` | `GET /api/retrieval/search/by-funding?funding=...&top_k=10` |
| 批量论文摘要 | `POST /api/v1/papers/batch`（`paper_ids` 1–100） | 逐篇 `GET /api/kg/paper`（经详情缓存），未找到的论文跳过 |
| PDF 字节流 | `GET /api/v1/paper-resource/pdf?paperId=...` | `pdf_url` 对应资源 |

Scholar 公共契约统一使用 `id`、`paperCount`，不向 Web 暴露上游
`scholar_id`、`paper_count`。详情当前只映射上游明确提供的 `years`、
`conferences`、`topics`、`funding`、`institutions`、`coauthors` 和 `papers`；
不提供 h-index、引用数、履历、角色、邮箱或个人主页。

Subject 关联检索和旧 Funding 关联检索上游返回的都是 Paper Results；Funding 候选
检索返回独立的 `FundingSummary`，只包含 `id`、`name`、`paperCount` 和统一
`provenance`。Funding 当前没有 Detail API，因此不能定义或推断 grant number、PI、
金额、周期、项目状态、专利状态等实体字段，也不提供 `total` 或 `hasMore`。上游返回的 `source_scores`、
`retrieval_mode` 等诊断字段不进入公共契约。搜索结果真实的 `image_id` 映射为可空的
`imageId`，供 Web 同源图片资源路由使用；不解析论文 ID，不推断详情接口的图片。
部署、路径和开关说明见 [论文图片接入](PAPER-IMAGES.md)。

论文详情中的 `pdf_url` 只由 Knowledge Integration 读取和映射，公共 Detail Contract
仅保留 `pdfUrl`。`GET /api/v1/knowledge/paper` 不调用 `paper_resource` Service，也不访问
PDF 源站；因此 PDF 的超时、404 或格式异常不会阻塞详情与摘要。

用户首次打开 Paper 视图时，PDF.js 才请求 ShenZhi 同源的
`GET /api/v1/paper-resource/pdf?paperId=...` 端点。该端点通过 `paperId` 再取可信详情，
随后使用 `PaperResourceService` 按 Provider 解析与打开资源：OpenReview Provider 负责来源
识别和论坛链接转换，HTTP Provider 负责超时、Content-Type、大小限制及流式读取。
端点不接受任意 URL，并透传合法的单段 Range。Backend 不保存或缓存 PDF，
也不创建下载任务。

PDF 响应使用可信论文标题生成文件名，替换非法字符、限制 UTF-8 字节长度，
空标题回退为论文 ID。默认返回 `inline`；下载按钮使用同一端点的
`download=true` 参数获取 `attachment`。两种模式均覆盖上游文件名，提供 ASCII
`filename` 回退和 UTF-8 `filename*`，预览和 Range 行为保持一致。

Search 请求使用 `query`、`topK`、`offset`、`yearFrom`、`yearTo`、`venue`、
`author`、`keyword`、`subject`。论文检索页固定 `topK=20`，并按
`offset=(page-1)*20` 请求；响应通过 `hasMore` 表示是否存在下一页。当前外部
接口接受较大的 `top_k`，但会忽略 `offset` 且不返回总数，因此 Backend adapter
为显式携带 `offset` 的论文检索请求读取至目标页后一条、在服务端截取目标页并
计算 `hasMore`。未携带 `offset` 的请求（如 Agent 知识库工具 `services/agent/knowledge_tools.py`）仍保持原有 `top_k` 行为。
其余筛选字段只在 adapter 边界映射为外部 API 所需字段（例如 `year_gte`、
`conference`）。

论文搜索页的查询词、页码及筛选条件由 URL 恢复。进入论文详情或关系图谱前，
结果区复用统一搜索恢复的认证身份，按完整搜索条件在 `sessionStorage` 保存滚动位置，
支持标题、详情/图谱链接及整卡鼠标或键盘打开；返回后等待实际结果
渲染，再恢复一次并清除记录。记录最多保留 30 分钟；用户开始滚动、重新搜索、
修改筛选、翻页或主动清空会取消来源与目标条件的旧位置恢复；查询词、筛选及页码
继续由统一 URL 导航恢复机制管理。禁用存储时正常导航，继续使用安全 `returnTo`
返回来源，不改变详情与图谱的返回策略。

图谱 `depth` 只支持 `1 | 2`，默认值为 `1`。Backend 可以返回异构节点和边；
前端保持 `kind`、`relation` 为开放字符串，未知值使用默认展示。

## 稳定契约

- `id`、`paperId`、`rootId` 都是 opaque string，禁止按 `paper:`、`AAAI:` 等
  内部格式解析。
- `Search result id === Detail request paperId === Graph request paperId === Graph.rootId`。
- `abstract`、`venue`、`year` 可为 `null`；`authors`、`keywords`、`subjects`、`topics`
  缺省为空数组。
- 论文列表与详情中的 `topics` 保留底座 Topic 的完整 `id`、`nameZh`（可为 `null`）、`nameEn`，按 ID 去重并保留原顺序。共用论文卡片只展示该字段的前五项，优先用中文名，并按完整 ID 跳转。未启用或找不到的主题进入现有详情不可用状态。
- `citationCount`、`referenceCount` 为 `null` 表示外部未提供，不能静默转成 `0`。
- 外部数字字段允许 number 或 numeric string：`"2021" → 2021`、`"42" → 42`、
  `"0.87" → 0.87`；空字符串变为 `null`，非法数字、非有限值和非法 integer
  变为 `CONTRACT_VIOLATION`。
- Graph `CITES` 统一表示 `sourceId` 引用了 `targetId`：
  `sourceId === rootId` 是 References，`targetId === rootId` 是 Citations。
- Graph 顶层保留 `provenance`；节点和边的 `kind` / `relation` 不因未知值抛错。

### Error Contract

Knowledge API 错误响应使用字符串 code，不使用历史数字错误码：

```json
{
  "code": "NOT_FOUND",
  "message": "safe user-facing message",
  "retryable": false,
  "requestId": "request-id-or-null"
}
```

允许的 code 为 `NOT_FOUND`、`INVALID_ARGUMENT`、`RATE_LIMITED`、
`UPSTREAM_UNAVAILABLE`、`TIMEOUT`、`CONTRACT_VIOLATION`、`UNKNOWN`。
`message` 必须是安全的用户可见信息，不得包含外部 URL、traceback 或 secret。

Knowledge 查询最多自动重试一次；`TIMEOUT`、`RATE_LIMITED`、
`UPSTREAM_UNAVAILABLE` 只有在 `retryable=true` 时重试。`NOT_FOUND`、
`INVALID_ARGUMENT`、`CONTRACT_VIOLATION` 在正式契约中不可重试；`UNKNOWN`
也必须遵守 `retryable` 和最多一次的上限，不能无限重试。

## 页面范围

Topic Catalog、分页上限、错误重试、数据核对与本地验收见
[Topic V2 稳定性与维护约定](TOPIC-V2-STABILITY.md)。

| 路由 | 行为 |
|---|---|
| `/knowledge` | 知识库总览（`KnowledgeDashboard`）：真实统计、混合检索入口与个人概览 |
| `/knowledge/search` | 会议/年份浏览及原有关键词检索；通过 URL 隔离查询模式 |
| `/knowledge/search/conferences` | 完整会议目录、名称搜索、实际年份筛选、排序与本地分页 |
| `/knowledge/papers` | 我的文献、收藏、文件夹和阅读历史 |
| `/knowledge/scholars` | 真实 Scholar Search；仅按姓名搜索 |
| `/knowledge/scholars/[scholarId]` | 真实 Scholar Detail；空 optional section 隐藏 |
| `/knowledge/scholars/graph` | 学者合作关系原型；上游尚无学者关系图谱 Contract，不进入产品导航 |
| `/knowledge/topics` | Topic 广场：完整目录、精选与分类、关键词搜索 |
| `/knowledge/topics/[topicId]` | Topic 详情：目录信息、关注按钮及按 OpenAlex Topic ID 分页查询的关联论文；支持安全 `returnTo` |
| `/knowledge/funding` | 项目基金库：浏览 Funding 候选；选择 Funding 后按名称查询关联论文；使用 `q` 与 opaque `funding` URL 参数恢复页面状态 |
| `/knowledge/graph` | 侧栏「关系图谱」入口；页面使用静态示例数据（`features/knowledge/data-knowledge-graph.ts`）；真实论文图谱见 `/papers/[id]/graph` |
| `/papers/[id]` | 统一论文详情与 PDF 阅读器；通过 Knowledge Client 加载真实详情 |
| `/papers/[id]/graph` | fullGraph（保留异构节点/边）、References/Citations 筛选、节点详情 |
| `/knowledge/search/[paperId]` | 旧链接兼容跳转到 `/papers/[id]`，保留合法 `returnTo` |
| `/knowledge/search/[paperId]/graph` | 旧图谱链接兼容跳转到 `/papers/[id]/graph`，保留合法 `returnTo` |
| `/search`、`/scholars`、`/scholars/[id]` | 旧入口兼容跳转：分别到 `/knowledge/search`（保留 `q`）、`/knowledge/scholars`、`/knowledge/scholars/[scholarId]` |

当前 Knowledge MVP 打通 Search → 统一 Paper Detail → Graph；Agent 通过
`services/agent/knowledge_tools.py` 以工具形式复用同一 Knowledge Service。论文详情页的
Assistant 运行在 Agent Runtime 上：`features/papers/[id]/use-paper-agent.ts` 经
`streamAgentRun` 调用 `POST /api/v1/agent/run`，提示词显式绑定当前 `paperId` 与标题，
涉及正文内容时要求调用 `read_paper` 工具。`apps/backend/app/services/agent/read_paper.py`
经知识库详情的 `pdf_url`（及 arXiv / OpenReview / DOI 候选）读取 PDF 分页文本并保留页号，
单次返回有长度上限并显式标记截断；PDF 不可达时退回网页正文并标明不是全文。
页面在工具执行期间显示“正在阅读论文 PDF…”。该流程不使用全局 Search 猜测“这篇论文”，
也不创建 Agent 产品会话。

`/knowledge/patents` 与 `/knowledge/institutions` 兼容路由继续保留，但不进入正式
产品导航；专利兼容路由只显示不可用状态。当前知识底座没有正式
Patent、Project 实体 Search/Detail，也没有 Funding Detail。产品中的
`/projects/[id]` 属于用户科研项目能力，不是 Knowledge Base Project。仍暂不包含
multistep、ID resolver、Deep Research 或 Auto Research。

论文库会议浏览的接口、缓存、数据边界和验收说明见
[Paper Library V2](PAPER-LIBRARY-V2.md)。

## Mock 规则

Mock 只由 `NEXT_PUBLIC_KNOWLEDGE_SOURCE=mock` 显式启用，适用于 unit test、
component test 和 demo fixture。真实 BFF 请求失败、Backend 未配置 upstream
或 upstream 不可用时，都保持真实错误状态，不自动返回 Mock 数据。

## 收藏人数、点赞与主题关注

用户级收藏/点赞/关注、平台级每日统计快照与知识底座只读接口见
[收藏人数、论文点赞与主题关注](INTERACTIONS-AND-STATS.md)。

## 学者库 V2 产品接口接入

`feat/scholars-v2` 的 V2 页面现默认使用产品学者 API，经同一 ShenZhi BFF / FastAPI / Knowledge 集成边界接入。旧 retrieval Scholar API 继续供总览与混合搜索使用；上述旧接口表不代表 V2 画像契约。实现、真实 GET 证据、测试、配置及底座需求见 [学者库 V2 真实接入与联调](scholars-v2-integration.md)。V2 无词访问为搜索初始态，不能据此宣称全量目录已上线。
