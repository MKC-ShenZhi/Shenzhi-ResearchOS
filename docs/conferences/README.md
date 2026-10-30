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

运行时不访问任何外部服务；与首页发现流一样由快照驱动。唯一的账号数据是「关注截稿」（`conference_follows` 表）。

## 数据更新

1. 将新的 ccf-deadlines 导出（`categories` + `conferences`，含 `exported_at`）放到 `data/conferences/`。
2. 运行 `python3 scripts/publish_conference_deadlines.py --source <导出文件>` 生成快照；`--check` 校验已发布快照与源一致。
3. 运行后端测试 `uv run python -m unittest tests.test_conferences`。

发布脚本只做结构清洗并拒绝未知格式：丢弃旧管理后台录入的 `source: manual` 测试记录；`TBD` / 空串归一为未公布；
修正 `abstract deadline` 键名；`N` / 空等级归一为 `null`。会议 ID 为 `<方向>-<简称>`（如 `se-fse` 与 `sc-fse` 是不同会议，
`cg-dcc` 与 `ds-dcc` 是同一会议在两个方向下的不同等级记录）。截稿时间在快照中保留官方本地时间 + 时区，便于与上游比对。

当前快照为 2026-10-29 从旧 ccfddl 后端导出，上游最后维护时间未知。接口仍返回 `data_as_of` 与 `source_url`，页面暂不展示。

## 业务规则（`app/services/conferences.py`）

- **时区**：`AoE` = UTC-12；`UTC` / `UTC±N` 为固定偏移；`PT` 按 `America/Los_Angeles` 计算夏令时。其他标签视为快照错误。
  响应中的 `at` 为 UTC 绝对时刻，前端按浏览者本地时区显示，同时展示 `local` 官方时间。
- **当届选择**：任一届存在未来里程碑 → 取下一个里程碑最近的那届，`open`；否则最新一届含未公布日期 → `tbd`；否则最新一届 → `closed`。
  里程碑包含摘要截止与全文截稿，截止时刻本身视为已截止。
- **排序**：`open` 按下一个里程碑升序 → `tbd` → `closed` 按最后截止时间倒序（最近截止的下一届最近）。
- **筛选**：`category`、`ccf`、`core`、`thcpl`、`status` 均可重复传参；同一等级体系内为“或”，跨体系为“且”；`N` 表示未被该体系收录；
  `q` 匹配简称、全称与 dblp key。未知方向返回 422。

前端只负责展示相关的时间计算：每秒走动的倒计时、紧急程度（24 小时 / 7 天 / 30 天）、页面停留期间从摘要截止滚动到全文截稿。

## 关注截稿（站内跟踪）

卡片主操作是「关注截稿」，目的是让用户留在站内跟踪截稿，而不是把提醒交给第三方日历：

- 接口（均需登录，经 BFF 透传可信身份）：`PUT` / `DELETE /api/v1/conferences/{id}/follow` 幂等写入；
  `GET /api/v1/conferences?followed=true` 在原有筛选之上只返回本人关注的会议。关注时校验 ID 存在于快照，取消关注不校验，
  快照下架的会议也能释放。数据表 `conference_follows`（迁移 `017_conference_follows`），注销账号时一并删除。
- 投稿页顶部「我关注的会议」显示剩余时间，点击定位到卡片；工具栏「只看关注」切换列表。
- 侧边栏「投稿」显示关注会议中 7 天内截止的数量，用户在站内任意页面都能看到。
- 「导出日历」是次要入口：Google / Outlook 网页日历通过预填链接新建下一个截稿节点的事件；`.ics` 面向 Apple 日历、飞书等本地日历
  （每个未来里程碑一个事件，提前 1 天提醒）。所有导出事件都带 `/submit?focus=<id>` 链接，打开后自动定位并高亮该会议。
- 尚无通知投递渠道（邮件 / 站内信），提醒只在用户访问站点时可见。

## 已知边界

- 数据无 Rebuttal / 录用通知 / 定稿时间，原型中的这些标签页未实现。
- `/submit/journals`（期刊）仍为静态原型，保持“功能暂未上线”。
- 全量响应约 200KB（353 个会议），默认只请求未截止的会议；数据规模显著增长时再引入分页。
