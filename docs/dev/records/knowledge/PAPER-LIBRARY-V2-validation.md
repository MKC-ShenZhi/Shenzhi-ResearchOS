# 论文库 V2 验收记录

> 从 [PAPER-LIBRARY-V2.md](../../../knowledge/PAPER-LIBRARY-V2.md) 拆出的历史记录，只反映记录当时的状态；当前约定以原文档为准。

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

## 搜索状态恢复修复（2026-10-23）

修复目录与关键词检索返回时的旧条件、旧结果和位置错用：目录入口现在读取已保存
筛选；两种论文库模式保存各自最近地址，升级时先迁移已有 v1 关键词地址；完整
清空目录会删除旧记录，清空关键词不会影响会议浏览。目录滚动按路径、查询、年份、
排序和页码隔离，从会议结果返回后等待目录渲染再恢复一次。

本次检查：TypeScript、生产构建通过；前端全量 349 项测试通过；Lint 0 错误，
仍为上述 2 条既有警告。无后端 API、数据库或依赖变更。

生产构建浏览器回归通过：

- `aaai + 2022 + 名称排序` → 会议论文 →「更多会议」恢复原条件和单条匹配结果。
- 清空目录全部条件 → 离开 → 再次进入，显示 121 条记录，不复活旧搜索。
- `graph neural network` 第 2 页 → 会议浏览 → 关键词检索，恢复相同关键词、
  第 2 页及对应 20 篇结果。

本次修改涉及上述文件清单中的导航、搜索 Feature 及测试，另外更新
`apps/web/features/knowledge/search/use-search-scroll-restoration.ts` 和
`docs/engineering/architecture-confirmation.md`。

## 修改文件清单

后续会议轮换新增 `conference-carousel.tsx` 和
`tests/knowledge/conference-carousel.test.ts`；复用原会议元数据缓存和焦点 URL 状态。
自动化覆盖真实分批、末批/循环、15 秒计时、800ms 反馈、交互/后台暂停、鼠标点击
后的恢复、减少动态效果和卸载清理；前端全量 355 项通过，类型检查通过，Lint
无错误（2 条既有警告）。浏览器已验证 121 条记录形成 21 批，末批只有 1 条且
下一批回到首批；实际等待 15 秒后整批切换，当前 INTERSPEECH 2025 保持不变。

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
