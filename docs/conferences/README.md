# 会议截稿（投稿 · 会议 `/submit`）

`/submit` 展示 CCF / CORE / TH-CPL 分级会议的投稿截止时间与实时倒计时。需求参考 ccfddl 的 DDL 页面，数据来自
[ccf-deadlines](https://github.com/ccfddl/ccf-deadlines) 的导出快照；实现按 ShenZhi 分层重写，不沿用原 Vue 代码。

## 调用链

```text
features/submit（ConferenceBrowser / ConferenceCard，共享一个时钟）
  ↓
clients/backend/conferences.ts
  ↓ same-origin
Next.js /api/v1/*（BFF 透传）
  ↓
FastAPI /api/v1/conferences*（app/api/conferences.py）
  ↓
app/services/conferences.py（时区换算、当届选择、排序、筛选）
  ↓
app/data/conference_deadlines_snapshot.json（随后端打包的版本化快照）
```

运行时不访问任何外部服务；与首页发现流一样由快照驱动。

## 数据更新

1. 将新的 ccf-deadlines 导出（`categories` + `conferences`，含 `exported_at`）放到 `data/conferences/`。
2. 运行 `python3 scripts/publish_conference_deadlines.py --source <导出文件>` 生成快照；`--check` 校验已发布快照与源一致。
3. 运行后端测试 `uv run python -m unittest tests.test_conferences`。

发布脚本只做结构清洗并拒绝未知格式：丢弃旧管理后台录入的 `source: manual` 测试记录；`TBD` / 空串归一为未公布；
修正 `abstract deadline` 键名；`N` / 空等级归一为 `null`。会议 ID 为 `<方向>-<简称>`（如 `se-fse` 与 `sc-fse` 是不同会议，
`cg-dcc` 与 `ds-dcc` 是同一会议在两个方向下的不同等级记录）。截稿时间在快照中保留官方本地时间 + 时区，便于与上游比对。

当前快照为 2026-10-29 从旧 ccfddl 后端导出，**上游已较久未维护**，页面明确展示快照日期并提示以官网为准。

## 业务规则（`app/services/conferences.py`）

- **时区**：`AoE` = UTC-12；`UTC` / `UTC±N` 为固定偏移；`PT` 按 `America/Los_Angeles` 计算夏令时。其他标签视为快照错误。
  响应中的 `at` 为 UTC 绝对时刻，前端按浏览者本地时区显示，同时展示 `local` 官方时间。
- **当届选择**：任一届存在未来里程碑 → 取下一个里程碑最近的那届，`open`；否则最新一届含未公布日期 → `tbd`；否则最新一届 → `closed`。
  里程碑包含摘要截止与全文截稿，截止时刻本身视为已截止。
- **排序**：`open` 按下一个里程碑升序 → `tbd` → `closed` 按最后截止时间倒序（最近截止的下一届最近）。
- **筛选**：`category`、`ccf`、`core`、`thcpl`、`status` 均可重复传参；同一等级体系内为“或”，跨体系为“且”；`N` 表示未被该体系收录；
  `q` 匹配简称、全称与 dblp key。未知方向返回 422。

前端只负责展示相关的时间计算：每秒走动的倒计时、紧急程度（24 小时 / 7 天 / 30 天）、页面停留期间从摘要截止滚动到全文截稿，
以及生成 `.ics` 日历文件（每个未来里程碑一个事件，提前 1 天提醒）。

## 已知边界

- 数据无 Rebuttal / 录用通知 / 定稿时间，原型中的这些标签页未实现。
- `/submit/journals`（期刊）仍为静态原型，保持“功能暂未上线”。
- 全量响应约 200KB（353 个会议），默认只请求未截止的会议；数据规模显著增长时再引入分页。
