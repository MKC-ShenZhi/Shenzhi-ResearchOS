# 国自然项目接入

主题库的「浏览国自然项目」入口通过 Next.js BFF、FastAPI Knowledge Service 和 NSFC Adapter 请求底座。批准号是项目主键，详情将单项目图谱投影为依托单位、人员和成果论文。

## 数据源

- `NSFC_PROJECTS_API_URL` 留空时，Adapter 通过 HTTPX ASGI transport 请求同进程的独立样本 API。数据位于 `apps/backend/app/data/nsfc-projects.jsonl`，每行对应原始导出的一份项目图谱，共 617 条。页面会标注样本数据。
- 正式底座按下述契约提供接口时，将 FastAPI 环境变量 `NSFC_PROJECTS_API_URL` 设为 `<KNOWLEDGE_BASE_API_URL>` 并重启即可切换。若正式契约有差异，在 `apps/backend/app/integrations/knowledge/nsfc_projects.py` 映射。配置远端后，其失败通过现有 Knowledge 错误契约返回。

## 预设底座契约

| 请求 | 成功响应 |
| --- | --- |
| `GET /api/retrieval/nsfc-projects?q=&limit=20&offset=0` | `{ "items": [...], "total": 617 }`。`total` 是过滤后的总数；`items` 每项是项目属性，需含 `award_number`、`name`、`award_year`、`project_status`、`host_institutions`（元素含 `name`），可含 `program_id`、`research_topics`。空查询返回分页目录，`limit` 为 1–50。 |
| `GET /api/retrieval/nsfc-projects/{award_number}` | `{ "graph": { "nodes": [...], "edges": [...] } }`。保留导出的 `id/label/properties` 和 `source/target/type` 结构。项目节点 ID 是 `project:{award_number}`，项目属性另含 `principal_investigators`（元素含 `name/role`），可含 `summary`、`start_date`、`end_date`、`source_url`。项目的 `PRODUCES_PAPER` 边指向 `Paper` 节点，论文属性含 `title`，可含 `source_url`。未知批准号返回 404。 |

样本的重复项目来源链接由样本 API 隐藏。详情以项目属性中的 `PI` 角色展示负责人，成果链接来自论文节点的 HTTPS 地址。
