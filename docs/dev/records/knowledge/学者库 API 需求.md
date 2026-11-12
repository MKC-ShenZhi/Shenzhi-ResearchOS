# 学者库首页与详情页 · 知识底座接口提需

评审稿 · 2026-11-12

学者库首页打开即可分页浏览，输入姓名、别名或机构可以搜索，点击任一卡片进入同一学者的详情页。此次提需曾以 364 条静态画像样本为渲染参考。接口的总数应由底座按实际可展示范围计算。

## 接口清单

| 接口 | 本轮需求 |
| --- | --- |
| `GET /api/v1/scholars?limit=20&offset=0` | **新增。** 首页首次打开、清空搜索时调用。分页返回底座已发布、可打开产品详情的学者画像。首批建议用已导入并确认可展示的快照画像作为浏览数据，名单和实际覆盖由底座确认。 |
| `GET /api/v1/scholars/search?q={关键词}&limit=20&offset=0` | **扩展。** 支持中英文姓名、已确认的姓名别名及关联机构。保留现有可检索学者范围，列表项与浏览接口共用卡片契约。 |
| `GET /api/v1/scholars/{scholarId}` | **扩展。** 复用卡片字段，补齐完整主题、双语简介、任职经历、年度引用和数据来源。 |
| `GET /api/v1/scholars/{scholarId}/papers?limit=20&offset=0` | 继续按现有契约提供与该学者匹配的平台论文。详情演示中的公共「论文库精选」沿用独立的论文库数据。 |

## 首页浏览与搜索

- 两个接口都返回 `{ items, total, limit, offset, has_more }`。默认 `limit=20`、`offset=0`，`limit` 为 1–100 的整数，`offset` 为非负整数。浏览的 `total` 为可浏览的去重学者数，搜索的 `total` 为该词命中的去重学者数。越界页返回空数组和原总数，无命中返回空数组及 `total=0`。`has_more = offset + items.length < total`。
- 默认浏览建议沿用快照的姓名顺序。底座按归一化展示姓名排序，同名以 `scholar_id` 打破并列，同一数据版本下翻页结果可复现。前端清空搜索后回到浏览第一页。
- 搜索的 `q` 必填，首尾空白去除后为空或分页非法时返回 400。建议统一做 Unicode NFKC 归一化及英文大小写折叠，支持子串匹配，优先完整姓名和已确认别名，其次姓名或别名部分命中，再按机构命中。并列结果按展示姓名、`scholar_id` 稳定排序。中文别名以已确认的底座记录为准。
- 先按底座稳定 `scholar_id` 去重，再计算总数和分页。同一学者通过浏览、姓名、别名或机构查到时应返回同一 ID。同名的不同学者保留各自 ID。静态快照的 `preview-*` ID 由本地生成，导入时由底座建立与正式学者 ID 的映射。详情接受列表返回的原始 ID 经路径编码后的值，未知 ID 返回 404。

### 卡片字段

| 字段 | 类型与渲染约定 |
| --- | --- |
| `scholar_id` | 非空字符串。底座稳定 ID，用于详情和论文请求。 |
| `name_zh`、`name_en` | 字符串或 `null`，至少提供一个。卡片中文名优先，两者都有时可展示英文副标题。 |
| `avatar_path` | 字符串或 `null`。建议返回浏览器可访问的 HTTPS 资源地址，缺失或加载失败时显示姓名首字母。联调时提供能在 ShenZhi 页面正常加载的头像样本。 |
| `affiliations` | `[{ institution, position }]`，`institution` 为机构显示名，`position` 可空。优先展示的关联机构放第一项，卡片取第一项，详情可展示多项。 |
| `topics` | 按展示优先级排序、去重的主题显示名数组 `string[]`。卡片返回前 3 项，详情返回全部可展示项，主题名称及顺序一致。 |
| `metrics.source_work_count` | 来源学者记录覆盖的作品总数，对应卡片和详情的「收录作品」。 |
| `metrics.citation_count` | 总引用次数。保留现有字段和已约定口径，底座需在联调样本中说明来源和覆盖范围。 |
| `metrics.h_index`、`metrics.i10_index` | 来源学者记录给出的 h 指数、i10 指数。 |
| `metrics.paper_count` | ShenZhi 平台关联论文数，沿用现有定义。已知时与该学者论文接口的 `total` 一致。 |

计数字段使用非负整数或 `null`。确认结果为零时返回 `0`，未知时返回 `null`。各接口对同一学者使用相同统计口径。主题、机构等无数据的数组返回 `[]`。搜索可使用别名索引，卡片响应无需回传别名。

### 卡片响应示例

以下数值用于说明响应结构，ID、数据范围和资源域名均为示例。

```json
{
  "items": [
    {
      "scholar_id": "scholar:example-001",
      "name_zh": null,
      "name_en": "Aayush Mishra",
      "avatar_path": "https://assets.example.com/scholars/example-001.jpg",
      "affiliations": [{ "institution": "The Johns Hopkins University", "position": null }],
      "topics": ["Topic Modeling", "Domain Adaptation and Few-Shot Learning", "Natural Language Processing Techniques"],
      "metrics": {
        "source_work_count": 17,
        "citation_count": 203,
        "h_index": 5,
        "i10_index": 5,
        "paper_count": 0
      }
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

## 学者详情

详情响应为单个学者对象。顶部和右侧统计复用卡片字段与口径，其中 `topics` 扩展为完整列表。其余字段如下。

| 字段 | 类型与渲染约定 |
| --- | --- |
| `bio_zh`、`bio_en` | 双语简介，字符串或 `null`。只有一种语言时可展示已有文本。 |
| `employment` | `[{ organization, role_title, department, start_date, end_date }]`。每项至少提供机构或职位，其他字段可为 `null`。日期保留原精度，接受 `YYYY`、`YYYY-MM`、`YYYY-MM-DD`。结束时间未知用 `null`，页面只展示已知日期。页面按开始时间倒序展示，首屏最多 5 条，可展开更多。 |
| `annual_citations` | `[{ year, count }]`，每年一条，`count` 表示对应年份收到的引用次数，允许 `null`。按页面需求至少提供最近 5 个有统计的年份（资料少于 5 年时返回已有数据）。缺失年份保持缺失，页面保留实际零值，并按年升序绘制最近 5 个有数值的年份。 |
| `citation_meta` | 保留 `{ source, coverage, as_of }`，用于标注引用来源、统计覆盖与截至日期。底座同时说明作品数、h 指数和 i10 指数取自哪份记录。 |
| `updated_at` | 保留现有更新时间，使用有效时间字符串或 `null`。与引用统计截至日期分别提供。 |
| `external_ids.orcid` | 可选。预览详情有 ORCID 入口，身份匹配经确认时返回规范 ID 字符串，缺失用 `null`。 |
| `affiliation_history`、`research_impact` | 保留现有字段供兼容。已有 `research_impact` 可作为对应卡片指标的数据来源，同口径字段取值一致。 |

`employment` 取有职位或机构的履历资料，本轮按「未经验证」展示。已有 `affiliation_history` 描述论文署名中的机构与年份，继续用于说明关联记录。履历资料缺失时返回 `employment: []`。总引用使用来源记录的累计值，年度引用用于趋势图，两者可有不同覆盖时段。

## 联调验收

1. 提供至少两页可浏览学者及若干字段较全的演示画像。首次访问直接显示首页卡片，刷新后顺序一致，连续两页无重复 ID，页尾显示实际总数。输入关键词后清空，可回到浏览第一页。
2. 对同一演示学者，分别用已收录的中文名、英文名、别名和机构检索，确认可召回同一个稳定 ID，并由该 ID 打开详情。提供一个无结果查询和一组同名不同人的样本。
3. 对比同一学者的浏览、搜索、详情三份响应，核对头像、机构、主题顺序和四项展示统计。提供一条含简介、任职、近年引用的详情，以及一条含缺失字段和真实零值的详情。
4. 提供至少一位有平台关联论文的样本，核对 `paper_count` 与论文接口 `total`，并验证另一位有来源作品、暂无平台关联论文的样本。公共精选继续使用独立论文库数据。
5. 底座交付时提供三类接口的真实样例响应，确认首批浏览范围、排序、头像访问和统计来源。ShenZhi 据此经现有 FastAPI Knowledge Client / Adapter 接入，Web 继续调用同源 BFF。
