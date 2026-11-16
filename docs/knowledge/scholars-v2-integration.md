# 学者库 V2 接入说明

## 当前接入约定

打开 `/knowledge/scholars` 时，通过同源 BFF 调用 FastAPI。默认浏览先显示首批 8 位，有下一页时自动加载第二批。之后和搜索结果一样，滚动接近末尾时根据 `has_more` 继续加载。默认浏览隐藏计数，搜索结果仅展示命中总数。清空搜索返回浏览目录，详情和关联论文沿用列表的稳定 `scholar_id`。

FastAPI 按 `limit` 和 `offset` 缓存成功的目录响应，每个进程最多保留 128 页，有效期为 5 分钟。刷新页面会继续请求 ShenZhi API，命中时直接复用缓存，过期后重新读取知识底座。

| ShenZhi API | 知识底座 API |
| --- | --- |
| `GET /api/v1/knowledge/scholar-profiles?limit=8&offset=0` | `GET /api/v1/scholars` |
| `GET /api/v1/knowledge/scholar-profiles/search?q=...&limit=8&offset=0` | `GET /api/v1/scholars/search` |
| `GET /api/v1/knowledge/scholar-profiles/{encodedId}` | `GET /api/v1/scholars/{encodedId}` |
| `GET /api/v1/knowledge/scholar-profile-papers?scholarId=...&limit=20&offset=0` | `GET /api/v1/scholars/{encodedId}/papers` |
| `GET /api/v1/knowledge/scholar-avatar?path=...` | 底座画像返回的 `/images/scholars_…/` 目录内图片 |

真实卡片展示关联机构、前三项主题、来源作品数、总引用和 h／i10 指数。详情展示已有简介、主题、任职、年度引用和平台关联论文。「收录作品」对应 `metrics.source_work_count`，平台关联论文使用论文接口的 `total`。相对头像路径由 FastAPI 适配为同源地址，仅转发指定学者头像目录下的 JPEG、PNG 和 WebP。

学者关联论文与论文检索复用论文卡片。论文响应沿用已有主题字段，并可附带底座提供的 `imageId`，缩略图使用现有论文图片规则。卡片保留 DOI 和 PDF 来源，内部详情入口由 `platform_detail` 控制。

学者库在开发和生产环境均通过知识底座 API 读取数据。FastAPI 使用 `KNOWLEDGE_BASE_API_URL`，Web 服务端使用 `BUSINESS_BACKEND_URL` 及现有 BFF 凭据。

联调记录：[2026-10-20 初次接入](../dev/records/knowledge/SCHOLAR-V2-INITIAL-INTEGRATION-2026-10-20.md)、[2026-11-12 底座接口复测](../dev/records/knowledge/SCHOLAR-API-VALIDATION-2026-11-12.md)。
