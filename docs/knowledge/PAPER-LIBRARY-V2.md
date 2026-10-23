# 论文库 V2：会议导览

本次迭代沿用 `/knowledge/search` 及现有 Knowledge Client → Next.js BFF →
FastAPI Knowledge Service → Knowledge Integration 链路。`/knowledge/papers`
仍为我的文献，不新增平行业务模块或依赖。

## 产品 API

以下均使用现有成功 envelope `{ code: 0, data: ... }`、BFF 凭证及 Knowledge
错误契约。浏览器不接触科研服务地址、科研服务原始字段或数据库 ID。

### `GET /api/v1/knowledge/conferences`

`data`：

```typescript
{ items: Array<{ name: string; paperCount: number; years: number[]; yearCount: number }> }
```

Integration 调用 `GET /api/papers/venues`（顶层数组），将 `conference/count`
映射为 `name/paperCount`；`years` 去重并降序，`yearCount` 为实际年份数组长度。
不按 `minYear/maxYear` 补齐缺失年份，不暴露 Track，不合并别名或重复会议记录。
空数组是成功空态；缺少必要字段、非法数值或格式错误返回 `CONTRACT_VIOLATION`。

### `GET /api/v1/knowledge/papers`

参数：`conference`（必填非空，最长 500）、`year`（必填整数 1000–9999）、
`limit`（默认 20，范围 1–100）、`offset`（默认 0，范围 0–2147483647）。
无需关键词；无 Track 参数。

`data`：

```typescript
{ results: PaperSearchResult[]; total: number; limit: number; offset: number }
```

Integration 调用 `GET /api/papers` 并直接转发上述参数；不使用关键词搜索的
look-ahead 或结果窗口限制。复用既有论文 Adapter，以 `paper_id` 为 opaque
`id`，缺少 `paper_id` 时返回契约错误，不回退到数字数据库 `id`。
`total/limit/offset` 规范为整数，校验返回分页和请求一致。详情继续使用既有
`GET /api/v1/knowledge/paper?paperId=...`。

## 页面与状态

- 首页默认进入按会议浏览。6 个精选名称由 `FEATURED_CONFERENCES` 明确配置：
  AAAI、CVPR、ICML、ACL、NeurIPS、ICLR。每个配置名称仅精确匹配真实记录；
  未收录或没有可用年份时禁用，不伪造数量。左侧焦点卡展示真实数量和年份数。
  当前接口没有英文全称，暂不展示未经核对的全称。
- 会议模式 URL：`/knowledge/search?mode=conference&conference=AAAI&year=2022&page=2`。
  切换会议默认最新实际年份并重置分页；非法年份回退到该会议最新年份并规范 URL。
  显式未知会议显示未找到提示，不悄悄查询另一个会议。
- 旧 `?q=...` 链接继续进入关键词检索；空白关键词模式通过 `?mode=keyword` 保留。
  搜索与浏览分离组件、查询 key 和参数；模式切换不会把会议条件带进关键词搜索。
- 年份超过 8 个可展开；恢复的已选年份始终可见。论文沿用现有卡片、收藏入口、
  详情和图谱链接、骨架屏、错误重试、分页与滚动恢复。URL 与导航恢复同时包含
  mode/conference/year/page，滚动位置按模式、会议、年份、页码分别保存。
- 「更多会议」通过站内导航进入独立 `/knowledge/search/conferences`，沿用 AppShell。
  名称即时搜索、实际年份筛选、论文数降序/名称 A–Z 排序均在前端执行；每页 21 条，
  桌面 3 列，窄屏 2/1 列。卡片中的实际年份链接直接回到对应论文列表；标题与
  「浏览」链接使用筛选年份或最新可用年份。
- 目录的 `q/year/sort/page` 同步 URL；筛选变动重置为第一页；越界页码按过滤结果
  限定显示范围。目录的 `q` 只搜索会议名，不触发关键词论文查询。
  本地筛选通过 Next.js 原生 History 集成同步，不进行服务端路由导航；连续修改
  始终读取当前 URL，避免快速输入、年份与排序切换互相覆盖。

## 缓存与异常

复用 TanStack Query，无新增中间件或后端缓存体系：

| 数据 | 新鲜期 | 内存保留期 |
| --- | --- | --- |
| 会议元数据（首页、目录共用 key） | 10 分钟 | 30 分钟 |
| 会议论文（完整 conference/year/limit/offset key） | 2 分钟 | 5 分钟 |

元数据不因窗口聚焦反复请求；筛选、排序、分页不请求元数据。刷新浏览器后重取，
不将完整科研数据持久化到本地存储。论文请求消费 Query 的 AbortSignal；切换条件、
模式或卸载取消不再订阅的请求，旧响应不能覆盖新结果。主动取消保留 AbortError。
重试沿用 Knowledge 最多自动重试一次策略；首次失败显示重试入口，后台刷新失败
保留同条件缓存并显示提示，绝不回退为 Mock 或成功空数组。

## 测试与联调

新增后端 `tests/test_paper_browse.py` 覆盖整个 API → Service → Integration：
参数校验、原始数组适配、离散年份、别名保留、真实 ID、详情一致、深分页、空数据、
错误转换及异常分页契约。前端 `tests/knowledge/conferences.test.ts` 覆盖模式隔离、
URL 往返、年份回退、目录过滤排序、BFF 参数及信号、缓存复用、取消及迟到响应、
导航和滚动隔离；更新现有导航恢复回归用例。

2026-10-23 真实上游核对：121 条会议记录全部适配成功；6 个精选会议最新年份的
第一页均返回 20 篇，首篇详情 `id` 与列表 `paper_id` 一致。

| 会议 | 最新实际年份 | 对应年份论文总数 |
| --- | --- | --- |
| AAAI | 2026 | 4839 |
| CVPR | 2026 | 1966 |
| ICML | 2026 | 2080 |
| ACL | 2026 | 3208 |
| NeurIPS | 2025 | 5290 |
| ICLR | 2026 | 3575 |

表格仅为联调记录，产品不读取这些常量；数量、年份始终来自运行时接口。

本地检查：

- `pnpm typecheck`：通过。
- `pnpm lint`：0 错误；2 条既有 Hook 依赖警告，位于
  `features/chat/hooks/use-chat-session.ts` 与 `lib/use-popover-placement.ts`。
- `pnpm test`：342 项通过（清理旧分支的 `.next/test-output` 后执行）。
- `pnpm build`：生产构建通过，包含新增 `/knowledge/search/conferences` 路由。
- `UV_CACHE_DIR=/tmp/shenzhi-uv-cache uv run --no-sync python -m unittest
  tests.test_paper_browse tests.test_knowledge tests.test_knowledge_entities
  tests.test_library_api tests.test_knowledge2chat tests.test_reading_history
  tests.test_paper_read_status`：114 项通过。

构建需要允许 Turbopack 启动本地 CSS 工作进程；沙箱禁止临时端口时会报
`Operation not permitted`，在允许该构建操作的环境中执行通过。无工具链或依赖变更。

浏览器（本地生产构建）已核对：目录 121 条/6 页、名称搜索、离散年份筛选、
快速连续修改筛选与排序、A–Z 排序后第 6 页、零匹配空态；目录进入非精选会议
VLDB 2026（95 篇）、论文第 2 页、详情真实摘要及返回后恢复；原关键词
`graph neural network` 正常返回 20 篇；侧边栏「我的文献」仍进入独立文献库。
首页开发服务另核对 AAAI → CVPR 切换、CVPR 2025 年份及对应 2874 篇结果。

## 数据风险与待验收

- 原始会议名可能包含别名、重复、异常名称；首版保留原名原记录。标题/年份
  依赖上游数据质量，例如当前 CVPR 数据包含 1964 年记录，产品不自行更正。
- 元数据与论文查询是独立上游请求，更新间隙可能出现目录有年份但列表暂无数据；
  前端显示真实空态。元数据最长有 10 分钟新鲜期。
- 论文必须提供能用于详情接口的 `paper_id`。当前精选首篇均核对成功，仍需科研组
  持续保证其他记录一致，不能使用数据库自增 ID 补救。
- 部分论文的既有缩略图资源缺失，沿用原卡片回退图；不影响真实列表和详情。
- 不包含 Track、推荐、主题分类、图谱新增能力或复杂会议清洗。

## 修改文件清单

```text
apps/backend/app/api/knowledge.py
apps/backend/app/integrations/knowledge/adapter.py
apps/backend/app/integrations/knowledge/client.py
apps/backend/app/integrations/knowledge/schemas.py
apps/backend/app/schemas/knowledge.py
apps/backend/app/services/knowledge/service.py
apps/backend/tests/test_paper_browse.py
apps/web/app/knowledge/search/conferences/page.tsx
apps/web/clients/knowledge/bff.ts
apps/web/clients/knowledge/client.ts
apps/web/clients/knowledge/index.ts
apps/web/clients/knowledge/mock.ts
apps/web/clients/knowledge/types.ts
apps/web/features/knowledge/search/KnowledgeSearchPage.tsx
apps/web/features/knowledge/search/conferences/ConferenceDirectoryPage.tsx
apps/web/features/knowledge/search/conferences/conference-browser.tsx
apps/web/features/knowledge/search/conferences/conference-queries.ts
apps/web/features/knowledge/search/conferences/conference-state.ts
apps/web/features/knowledge/search/conferences/conference-states.tsx
apps/web/features/knowledge/search/conferences/library-mode-nav.tsx
apps/web/features/knowledge/search/search-scroll-state.ts
apps/web/lib/navigation/search-restoration.ts
apps/web/tests/knowledge/conferences.test.ts
apps/web/tests/knowledge/search-restoration.test.ts
docs/knowledge/PAPER-LIBRARY-V2.md
docs/knowledge/README.md
```
