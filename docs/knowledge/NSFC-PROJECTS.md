# 国自然项目接入

项目基金库（`/knowledge/funding`）默认展示国自然项目目录，经 Next.js BFF、FastAPI Knowledge Service 和 NSFC Adapter 请求底座。批准号是项目主键，详情将单项目图谱投影为依托单位、人员和成果论文。点击详情的研究关键词可按该字段精确筛选。目录每批加载 20 条，滚动接近列表底部时追加。返回基金库时保留搜索词和关键词筛选，并可复用前端缓存中的批次。「基金与关联论文」页签提供基金候选和关联论文查询。

## 数据源

FastAPI 使用后端已有的 `KNOWLEDGE_BASE_API_URL` 请求国自然项目。目录总数以底座返回的 `total` 为准，底座请求失败时沿用 Knowledge 错误契约。

ShenZhi 的目录和详情 API 使用 `/api/v1/knowledge/projects` 和 `/api/v1/knowledge/projects/{award_number}`。旧 `/api/v1/knowledge/nsfc-projects` 路径仍可兼容调用。FastAPI 按每页条数缓存无筛选的首批成功响应，每个进程最多保留 50 项，有效期 5 分钟。前端按搜索词和关键词保存已加载批次，有效期 5 分钟，离开页面后缓存保留 10 分钟。

## 底座 API 契约

| 请求 | 成功响应 |
| --- | --- |
| `GET /api/retrieval/projects?q=&limit=20&offset=0` | `{ "items": [...], "total": 617 }`。`total` 是过滤后的总数；`items` 每项是项目属性，需含 `award_number`、`name`、`award_year`、`project_status`、`host_institutions`（元素含 `name`），可含 `program_id`、`research_topics`、`summary`、`principal_investigators`（元素含 `name/role`）和 `output_papers`（论文 ID 列表，用于目录计数）。空查询返回分页目录，`limit` 为 1–50。可选的 `keyword` 必须匹配 `research_topics` 中的完整关键词，忽略大小写和首尾空格，与 `q` 同时提供时须同时满足两者。 |
| `GET /api/retrieval/projects/{award_number}` | `{ "graph": { "nodes": [...], "edges": [...] } }`。保留导出的 `id/label/properties` 和 `source/target/type` 结构。项目节点 ID 是 `project:{award_number}`，项目属性另含 `principal_investigators`（元素含 `name/role`），可含 `summary`、`start_date`、`end_date`、`source_url`。项目的 `PRODUCES_PAPER` 边指向 `Paper` 节点，论文属性含 `title`，可含 `source_url`。未知批准号返回 404。 |

详情以项目属性中的 `PI` 角色展示负责人。项目和成果链接取对应节点提供的 HTTPS 地址。
