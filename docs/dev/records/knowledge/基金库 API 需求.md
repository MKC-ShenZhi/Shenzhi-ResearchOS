# 项目基金库 · 知识底座 API 需求

评审稿 · 2026-11-12

「项目基金库」默认展示国自然项目。用户打开页面即可分页浏览，能按批准号、项目名、研究关键词、负责人或依托单位查找项目，点进详情查看摘要、人员和成果论文，并能点详情里的研究关键词返回目录筛选。

现有 `GET /api/retrieval/fundings/search`（搜索基金候选）和 `GET /api/retrieval/search/by-funding`（按基金查关联论文）本期保持原样，继续服务「基金与关联论文」页签。待新项目能力完善、现有调用迁移后，两个旧接口将废弃。

## 首期数据与接口

建议首期导入「国自然图谱汇总_共617」。本地 617 份原始 JSON 与 ShenZhi 联调快照逐条一致，包含 617 个不同批准号，批准年份为 2013–2024 年。图中共有 4,208 条 `PRODUCES_PAPER` 边，其中 9 个项目没有成果论文记录，单项目最多 71 篇。首期覆盖这批国自然结项样本，线上总数按实际发布的数据计算。

| 接口 | 用途 | 200 响应 |
| --- | --- | --- |
| `GET /api/retrieval/projects` | 浏览、搜索及关键词筛选共用 | `{ "items": [...], "total": 617 }` |
| `GET /api/retrieval/projects/{award_number}` | 按批准号取单项目详情及成果 | `{ "graph": { "nodes": [...], "edges": [...] } }` |

底座以 `projects` 作为通用项目资源，首批数据来自国自然。首期实现目录查询与单项目图查询，沿用本地样本 API 的响应结构。后续接入其他基金时沿用这两个路径，通过可选的 `funding` 查询参数指定基金来源，参数值使用稳定的来源标识，例如 `nsfc`。届时目录按来源过滤，详情按「基金来源 + 批准号」精确定位，避免不同来源的同号项目冲突。建议两个接口省略 `funding` 时都默认查国自然，保持现有调用的语义。首期只需支持国自然数据，暂不要求实现该参数。

## 目录查询

| 参数 | 规则 |
| --- | --- |
| `q` | 可选字符串，最长 200 字符，空值或纯空白等同于浏览。去除首尾空白，按空白拆词并忽略大小写。每个词都须在项目的批准号、标题、摘要、研究关键词、人员姓名或依托单位中命中子串，允许不同词命中不同字段。人员姓名索引包含负责人和参与人员。 |
| `keyword` | 可选字符串，最长 200 字符。去除首尾空白后，忽略大小写，与 `research_topics` 的一个完整条目匹配。空值不筛选。与 `q` 同时提供时取交集。 |
| `limit` | 整数，默认 20，范围 1–50。 |
| `offset` | 非负整数，默认 0。 |

首期在国自然数据内以规范化后的 `award_number` 为唯一键。先过滤并按批准号去重，再按 `award_year` 降序、`award_number` 字符串降序分页。同一数据版本内翻页顺序应稳定。`total` 为过滤、去重后且分页前的总数。无命中返回 `{"items":[],"total":0}`。偏移超出范围时 `items` 为空，`total` 仍返回筛选后的总数。非法参数建议沿用 FastAPI 的 422 响应。

每条 `items` 使用导出图中 `Project.properties` 的字段名，可只返回下列字段。数组无记录时用 `[]`，可选文本无记录时用空字符串或 `null`。`output_papers` 的空数组和缺省含义单独约定如下。

| 字段 | 类型与用途 |
| --- | --- |
| `award_number` | 非空字符串。项目在所属基金来源内的批准号。首期国自然数据保留前导零，字母统一大写。详情路径与项目节点 ID 使用同一值。 |
| `name`、`award_year`、`project_status` | 非空标题、整数批准年份、项目状态字符串。状态缺失时返回空字符串。 |
| `host_institutions` | `[{ "name": "示例大学" }]`，依托单位。 |
| `program_id` | 可选字符串，沿用导出中的项目类型值，如 `program:面上项目`。当前页面去掉 `program:` 前缀后展示。 |
| `summary`、`research_topics` | 摘要字符串与研究关键词字符串数组，供目录展示、检索和详情关键词回跳。 |
| `principal_investigators` | `[{ "name": "示例姓名", "role": "PI" }]`。目录只展示 `PI`，详情也展示其他人员，保留样本中的 `Co-PI` 角色。 |
| `output_papers` | 该项目的成果论文节点 ID 数组，与详情中有效 `PRODUCES_PAPER` 边的去重目标一致。目录按 ID 去重计数。已知无记录用 `[]`，底座无法确定时可省略或用 `null`，目录隐藏该计数。 |

`GET /api/retrieval/projects?q=示例大学&keyword=机器学习&limit=20&offset=0` 的示例响应如下。实际请求对中文做 URL 编码，示例 ID 和字段值仅用于说明结构。

```json
{
  "items": [
    {
      "award_number": "00000001",
      "name": "示例研究项目",
      "award_year": 2024,
      "project_status": "结题",
      "program_id": "program:面上项目",
      "host_institutions": [{ "name": "示例大学" }],
      "principal_investigators": [{ "name": "示例姓名", "role": "PI" }],
      "summary": "示例摘要",
      "research_topics": ["机器学习"],
      "output_papers": ["paper:example-001"]
    }
  ],
  "total": 1
}
```

## 项目详情

首期在国自然数据内按批准号精确查找，接受 1–24 位 ASCII 字母或数字。入库和查询使用相同的大小写归一规则。格式合法但不存在的批准号返回 HTTP 404。存在但没有成果论文的项目仍返回 HTTP 200。

- `graph.nodes` 中须有一个 ID 为 `project:{award_number}`、`label` 为 `Project` 的主节点。其 `properties` 提供目录同名字段，并可提供 `start_date`、`end_date`（已知日期用 `YYYY-MM-DD`）和项目级 `source_url`。其中 `principal_investigators` 始终返回数组。
- 每条成果边的 `source` 为主项目节点 ID，`type` 为 `PRODUCES_PAPER`，`target` 必须存在于同一响应并指向 `Paper` 节点。论文节点提供非空 `properties.title`，可提供 `properties.source_url`。以目标节点 ID 去重，同一项目详情只展示一条同 ID 论文。首期返回该项目已收录的全部成果。
- 详情保留原始导出的节点 `id/label/properties` 和边 `source/target/type`。可随图返回机构、人员、项目类别等节点与关系。当前页面从项目属性读取人员与依托单位，从直接产出边读取论文，详情请求无需额外查询作者。
- 来源链接提供可打开的项目或论文级 HTTPS URL。缺失时省略、返回空字符串或 `null`。原始导出中的共用入口不作为具体项目的详情链接。

```json
{
  "graph": {
    "nodes": [
      {
        "id": "project:00000001",
        "label": "Project",
        "properties": {
          "award_number": "00000001",
          "name": "示例研究项目",
          "award_year": 2024,
          "project_status": "结题",
          "program_id": "program:面上项目",
          "host_institutions": [{ "name": "示例大学" }],
          "principal_investigators": [
            { "name": "示例姓名", "role": "PI" },
            { "name": "示例成员", "role": "Co-PI" }
          ],
          "summary": "示例摘要",
          "research_topics": ["机器学习"],
          "output_papers": ["paper:example-001"],
          "start_date": "2024-01-01",
          "end_date": "2024-12-31",
          "source_url": null
        }
      },
      {
        "id": "paper:example-001",
        "label": "Paper",
        "properties": { "title": "示例成果论文", "source_url": null }
      }
    ],
    "edges": [
      {
        "source": "project:00000001",
        "target": "paper:example-001",
        "type": "PRODUCES_PAPER"
      }
    ]
  }
}
```

## 底座实现与联调验收

导入时按批准号建立项目唯一索引，从项目属性生成目录检索字段及关键词索引。从有效的 `PRODUCES_PAPER` 边生成目录的 `output_papers`，让目录与详情共享同一关系来源。上线前检查空主键、重复项目、悬空成果边和缺标题论文，并确认首期发布的数据范围。

1. 使用完整的 617 条样本联调时，无条件查询总数应为 617。默认每页 20 条，最后一页 17 条，`offset=620` 返回空页且总数仍为 617。遍历目录时，同一批准号只出现一次。
2. 用批准号、项目名片段、负责人姓名和依托单位分别查找同一项目。用项目详情的一项关键词查询，应能找到原项目。仅有子串匹配的关键词不会通过 `keyword`，`q` 与 `keyword` 的组合结果应满足两项条件。
3. 用目录中的批准号打开详情，核对负责人、参与人员、机构、关键词、摘要和成果。对每个样本比较目录去重后的 `output_papers` 与详情有效成果边的去重目标。确认无成果的项目详情返回 200，未知批准号返回 404。
4. 底座提供两个接口的联调地址、鉴权方式和样例批准号后，ShenZhi 将 FastAPI 上游适配器的请求路径映射到 `/api/retrieval/projects`，配置远端数据源，再验证目录、详情、关键词回跳及错误提示。
