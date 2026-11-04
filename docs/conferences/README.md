# 会议截稿（会议DDL `/submit`）

`/submit` 展示 CCF / CORE / TH-CPL 分级会议的投稿截止时间与实时倒计时。需求参考 ccfddl 的 DDL 页面，数据来自
[ccf-deadlines](https://github.com/ccfddl/ccf-deadlines) 的版本化 YAML 快照；实现按 ShenZhi 分层重写，不沿用原 Vue 代码。

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
conference_snapshots（数据库当前快照；打包 JSON 兜底）
```

页面请求不访问上游服务；后台任务更新数据库当前快照。账号数据为「关注截稿」（`conference_follows` 表）。

## 数据更新

后端优先读取数据库 `conference_snapshots` 当前快照，数据库无可用资料时使用随后端打包的快照。运行时请求不访问 GitHub；缓存每 5 分钟检查数据库版本，变化后重新加载，数据库异常时保留最近一次已校验目录。活动页面每 5 分钟重新请求会议、分类及关注数据；仅设置 staleTime 不等同于定时刷新。

长驻后端设置 `CONFERENCE_SYNC_ENABLED=true` 后复用现有 `HomeFeedScheduler`，每 10 分钟检查是否到期；成功检查距今满 23 小时才获取上游最新提交。SHA 未变只更新检查时间；有变化则从 `ccfddl/ccf-deadlines` 下载该 SHA 的压缩包，读取 `conference/types.yml` 和 `conference/*/*.yml`，校验后原子替换当前快照。失败保留旧数据，至少 1 小时后重试。首页调度开关与会议开关独立。

上线前先运行迁移（021 关注 ID 迁移 + 022 快照表），再启用任务。生产服务器必须能访问 `api.github.com` 和 `codeload.github.com`。进程内调度不适用于无法保证持续运行的 Serverless 实例。共享 IP 限流时可选配置仅后端使用的 `CONFERENCE_GITHUB_TOKEN`。

```bash
cd apps/backend
uv run --locked --env-file .env alembic upgrade head
# dry-run 只检查，不更新快照和检查时间；--force 忽略时间间隔，不绕过保护规则
uv run --locked --env-file .env python -m app.services.conferences_cli sync --dry-run --force
uv run --locked --env-file .env python -m app.services.conferences_cli sync --force
# 离线发布：上游目录为干净 Git checkout，自动记录其提交 SHA / 提交日期
uv run --locked python -m app.services.conferences_cli publish --source /path/to/ccf-deadlines
uv run --locked python -m app.services.conferences_cli publish --source /path/to/ccf-deadlines --check
# 解压目录则显式提供 --revision <40位SHA> --commit-date YYYY-MM-DD
```

共用清洗模块为 `app/services/conferences_source.py`；不新增依赖。TBD / 空串归一为未公布，等级 N / 空值归一为 null，修正 abstract deadline 键名，显式忽略 rebuttal_deadline / decision_deadline，其他未知时间轴字段拒绝。快照保存官方当地时间和时区，不在采集阶段换算 UTC。

保护规则：完整 schema 和目录校验；会议数量不得比当前资料减少超过 10%；不能丢失用户已关注的会议 ID。失败记录日志且不替换 payload。下载与解压声明大小均受限，不解压至磁盘。数据库只保留当前一份，避免历史快照无限增长；已知分类变化由 021 迁移保住关注，后续变化需核查。

`data_as_of` 是上游提交日期，`source.revision` 标识精确来源版本，并不意味着逐条官网核验日期。页面显示资料日期及来源。[设计与验证说明](AUTO-SYNC-DESIGN.md)。

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
- 侧边栏一级入口「会议DDL」显示关注会议中 7 天内截止的数量，用户在站内任意页面都能看到。
- 「导出日历」是次要入口：Google / Outlook 网页日历通过预填链接新建下一个截稿节点的事件；`.ics` 面向 Apple 日历、飞书等本地日历
  （每个未来里程碑一个事件，提前 1 天提醒）。所有导出事件都带 `/submit?focus=<id>` 链接，打开后自动定位并高亮该会议。
- 尚无通知投递渠道（邮件 / 站内信），提醒只在用户访问站点时可见。

## 已知边界

- 数据无 Rebuttal / 录用通知 / 定稿时间，原型中的这些标签页未实现。
- `/submit/journals`（期刊）仍为静态原型，保持“功能暂未上线”。
- closed 且最后截稿超过 365 天的会议显示“待更新”，通过新增 needs_update 字段表示，不改变原状态和筛选规则。
- 资料量随上游变化，默认只请求未截止的会议；数据规模显著增长时再引入分页。
  前端按 20 张一批渲染、滚动接近底部再追加；只有首批卡片参与布局补位动画；秒级倒计时只重渲染倒计时本身，卡片按分钟更新。

## 并发发布与审查

发布快照和新增关注使用配套的短时事务锁；发布事务重新检查关注，关注写入依据数据库当前快照校验 ID，避免缓存滞后导致失效关注。下载不持有发布短锁。压缩包实际解压字节（含 PAX/GNU 元数据）受上限约束。完整目录校验在线程中执行。

详见 [2026-11-04 审查与修复](REVIEW-2026-11-04.md)。

## Vercel 定时同步

后端提供密钥保护的同步入口。主触发由 `.github/workflows/conference-sync.yml` 每小时调用，Vercel每日Cron仅作备用；后端到期前只做轻量数据库检查，约每天才访问上游。失败后满1小时，在后续触发中自动重试；保留旧快照。需完成数据库迁移、后端配置和仓库Actions密钥/开关配置；schedule只在默认分支生效，功能分支上传本身不会启用线上任务。完整步骤见 [自动同步设计](AUTO-SYNC-DESIGN.md#每小时外部触发与失败自动重试)。
