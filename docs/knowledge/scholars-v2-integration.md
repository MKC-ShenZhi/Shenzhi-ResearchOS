# 学者库 V2 接入说明

## 当前接入约定

打开 `/knowledge/scholars` 时，真实模式通过同源 BFF 调用 FastAPI。没有关键词时读取底座的产品学者目录，有关键词时调用产品学者搜索。列表每批读取 8 位，滚动接近末尾时根据 `has_more` 继续加载。默认浏览隐藏计数，搜索结果仅展示命中总数。清空搜索返回浏览目录，详情和关联论文沿用列表的稳定 `scholar_id`。

| ShenZhi API | 知识底座 API |
| --- | --- |
| `GET /api/v1/knowledge/scholar-profiles?limit=8&offset=0` | `GET /api/v1/scholars` |
| `GET /api/v1/knowledge/scholar-profiles/search?q=...&limit=8&offset=0` | `GET /api/v1/scholars/search` |
| `GET /api/v1/knowledge/scholar-profiles/{encodedId}` | `GET /api/v1/scholars/{encodedId}` |
| `GET /api/v1/knowledge/scholar-profile-papers?scholarId=...&limit=20&offset=0` | `GET /api/v1/scholars/{encodedId}/papers` |
| `GET /api/v1/knowledge/scholar-avatar?path=...` | 底座画像返回的 `/images/scholars_…/` 目录内图片 |

真实卡片展示关联机构、前三项主题、来源作品数、总引用和 h／i10 指数。详情展示已有简介、主题、任职、年度引用和平台关联论文。「收录作品」对应 `metrics.source_work_count`，平台关联论文使用论文接口的 `total`。相对头像路径由 FastAPI 适配为同源地址，仅转发指定学者头像目录下的 JPEG、PNG 和 WebP。

学者关联论文与论文检索复用论文卡片。论文响应沿用已有主题字段，并可附带底座提供的 `imageId`，缩略图使用现有论文图片规则。卡片保留 DOI 和 PDF 来源，内部详情入口由 `platform_detail` 控制。

删除 `NEXT_PUBLIC_SCHOLAR_PREVIEW` 或设为 `0` 后重启 Web 开发进程。生产模式需要重新构建 Web。FastAPI 使用 `KNOWLEDGE_BASE_API_URL`，Web 服务端使用 `BUSINESS_BACKEND_URL` 及现有 BFF 凭据。设置 `NEXT_PUBLIC_SCHOLAR_PREVIEW=1` 可继续使用本地快照和公共精选论文。

联调记录：[2026-10-20 初次接入](../dev/records/knowledge/SCHOLAR-V2-INITIAL-INTEGRATION-2026-10-20.md)、[2026-11-12 底座接口复测](../dev/records/knowledge/SCHOLAR-API-VALIDATION-2026-11-12.md)。
