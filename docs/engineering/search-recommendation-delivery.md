# 搜索推荐集成验收报告

验收日期：2026-10-30（Asia/Tokyo）。验收对象：本地 `integration/search-recommendation`。
结论：**可以提交 PR 合入 dev，等待人工审查**。本轮未 Push、未创建 PR、未合并 dev；
未操作生产库或日常开发库，未修改 `vercel.json`、`uv.lock`、`pnpm-lock.yaml`，未集成 `feat/idempotency-v1`。

## 1. Git 集成方式

- 开始时主工作区位于 `dev` 且干净，不是独立 Worktree；本轮新建独立 Worktree
  `../shenzhi-search-rec`，执行 `git fetch origin` 后以 `origin/dev = 24e92337ace27c300ee8169e8ec0cb916cccf9bb`
  为基线创建 `integration/search-recommendation`，并取消其上游跟踪，避免误推 dev。
- 实际核对：`feat/search-recommendation = 140557b` 相对 dev 领先 2、落后 8，merge-base 为
  `e0ba015`（原始互动基础层）。推荐独有提交只有两个，按时间顺序 `cherry-pick -x`：

| 原始提交 | 集成后 | 说明 |
|---|---|---|
| `cd1f846` factor：简单构建搜索推荐算法，准备引入向量模型 | `7b7028c` | 6 处冲突，按语义解决（见下） |
| `140557b` fix:阅读记录去重、刷新用户画像策略、用户活跃阅读统计 | `6af95e0` | 无冲突 |
| — | `b5ddaee` fix: 修复推荐分页降级、召回隔离与事件归因并对齐互动基础层 | 本轮修复与测试 |
| — | 本报告 `docs:` 提交 | 最终哈希见 `git log` |

冲突处理（均以保留阶段 2 修复为前提）：

- `services/library/collections.py`：dev 已用 `collection_user_states` 账号级行锁 `_lock_membership(session, user_id)`
  串行化替换/移动/移除/删除；推荐分支新增了同名的 `(user, paper)` advisory lock 静态方法。若机械合并，
  后定义的方法会**覆盖**账号锁并使空集合替换失去串行化。处理：保留账号锁，删除分支版锁及
  `delete_folder` 的逐论文加锁循环，仅保留收藏/取消收藏事件与 `_has_paper` 判定。
- `use-paper-like.ts`、`use-topic-follow.ts`、`interactions.test.ts`：保留 dev 的 owner/generation 防护与
  `refresh*Queries` 统一失效；分支新增的 `home-feed` 失效不并入（理由见 §3）。
- `main.py`：合并 `conferences` 与 `behavior/recommendations/maintenance` 路由。
- `paper-card.tsx`：仅 import 冲突，合并双方。
- `vercel.json`：原提交新增 Cron，按要求恢复为 dev 版本。

## 2. 已有实现与本轮新增

原分支已有并保留：行为事件表/画像表/快照表（`015`）；服务端在点赞、收藏、关注及撤销事务内追加显式事件；
详情访问 10 分钟去重与 advisory 锁；首次已读才记 `paper_read`；浏览器隐式事件白名单、每批 20、每分钟 120、
UUID 幂等；`content-v1` 长/短期主题与关键词画像、强信号即时刷新/弱信号 10 分钟 TTL；四路知识召回 + 48 篇全局发现；
可解释加权排序、多样性、已赞/已藏过滤；一小时私有分页快照；曝光（≥50% 可见 1 秒）、点击、搜索 `query_id`
关联、摘要展开、前台累计 30 秒有效阅读；注销清理；维护 CLI；离线评估工具与 1 个临时标注样本。

本轮新增修复见下表；其余原实现经审查后未改动。

## 3. 主要问题与修复位置

| 问题 | 位置 | 修复与验证 |
|---|---|---|
| **P0** 推荐后续页任一异常都被吞掉并返回全局发现第一页，导致重复、跳页、列表重新开始 | `features/search/services/discovery-feed.ts` | 仅 `cursor === null` 时允许降级（异常或空结果），整份列表改走 `discovery:` 游标；后续页异常一律抛出，由 useInfiniteQuery 保留已加载页并重试同一游标。8 个新前端回归（含真实 `InfiniteQueryObserver`）+ 浏览器验收 |
| 快照过期/被清理时返回 400，前端无法区分“可重试”和“需重建” | `services/recommendation/recommendations.py`、`feed-list.tsx` | 快照不存在、过期、属于他人统一 `20001/409`（沿用统计快照游标约定，且不泄露他人 request_id 是否存在）；格式错误仍 400。前端抛 `RecommendationFeedExpiredError`，不自动重试，显示“刷新推荐”并 `resetQueries` 从第一页重建 |
| 召回只捕获 `KnowledgeServiceError/TimeoutError`，适配层其他异常或发现快照异常会拖垮整个推荐 | `recommendations.py`、`features.py`、`config.py` | 每路召回、全局发现、单篇元数据均隔离非预期异常；超时、数量上限、并发集中到 `config`（召回 5s/路、12 篇/路、≤4 路，发现 48 篇，元数据 4s/篇、整批 6s、并发 4）；日志只记录错误类型，不记录可能是私人搜索词的召回值 |
| 浏览器可在非推荐事件上携带任意 `request_id`，服务端不校验即入库 | `schemas/behavior.py` | 仅 `recommendation_*` 事件可带 `request_id`，且仍需匹配本人未过期快照的论文与名次 |
| 行为上报、推荐请求没有阶段 2 的账号前置条件，旧标签页可把事件归到新登录账号 | `clients/backend/behavior.ts`、`recommendations.ts` 及调用方 | 统一附带 `x-shenzhi-expected-user-id`（只拒绝、不指定身份）；无用户时不上报 |
| 账号切换后旧用户的推荐页仍留在内存缓存 | `features/knowledge/interactions/cache.ts` | `home-feed` 纳入 `clearOtherInteractionIdentities` |
| 点赞/收藏/阅读后整表失效 `home-feed`，以及窗口聚焦重取，都会生成新快照并替换正在浏览的列表 | `feed-list.tsx`、`collection-picker.tsx`、`PaperDetailPage.tsx` | 移除互动后的整表失效；推荐 Feed 关闭 focus/reconnect 重取，staleTime 恢复 10 分钟。新兴趣在下次进入首页或“刷新推荐”时生效（画像本身已即时重建） |
| `vercel.json` Cron 与 README/环境变量说明 | `README.md`、`.env.example` | 不注册 Cron；保留 CLI 与需 `CRON_SECRET` 的维护接口（未配置返回 503；BFF 不转发 Authorization，浏览器无法经 BFF 触发） |
| `test_interaction_migrations` 断言 014 为 head，引入 015 后必然失败 | `tests/test_interaction_migrations.py` | 改为显式升级到 `014_platform_snapshots`，保持 011–014 契约；单 Head 校验移到新测试 |
| 原分支改 `mark_read` 为 `scalar(... RETURNING)`，dev 既有单测替身缺少 `scalar` 而报错 | `tests/test_paper_read_status.py` | 补充替身并断言 `ON CONFLICT ... WHERE read_at IS NULL`。行为变化：重复完成阅读保留首次 `read_at`（仅用于已读状态与画像，无其他消费者） |

## 4. 数据库迁移

- 迁移链（最新 dev + 本分支）：`011_agent_uploads → 012_topic_follows → 013_paper_likes → 014_platform_snapshots → 015_recommendation_foundation`；
  `alembic heads` 只有 `015_recommendation_foundation (head)`；历史中无 `request_idempotency`；012–014 文件未改动。
- 本轮新建 PostgreSQL 16.15 临时集群：数据目录 `/private/tmp/shenzhi-rec-pg-20261030`，仅监听 `127.0.0.1:55441`，
  `trust` 本地账号 `shenzhi_test`，无真实凭据；未读取或连接 `apps/backend/.env` 指向的开发库与任何生产库。
- `shenzhi_rec_test`：从空库 `alembic upgrade head` 执行 001→015，当前版本 `015_recommendation_foundation`。
- 迁移回归（各用新建空库，拒绝非本机、非 `_migration_test`、非空库）：
  - `test_interaction_migrations`：`011 → 014 → 013 → 012 → 011 → 014`，原有约束/哨兵数据校验通过。
  - 新增 `test_recommendation_migrations`：单 Head；`014 → 015 → 014 → 015`；三表主键
    （`event_id` / `user_id` / `request_id`）、`idx_behavior_events_user_time/user_entity/received`、
    `idx_recommendation_snapshots_user_expiry/expiry` 存在；重复 `event_id` 的 `ON CONFLICT DO NOTHING` 写入 1/0；
    回滚后表集合恢复为 014，014 中的点赞哨兵数据在回滚与重升后保留。
- 外键：三表均无外键——用户 ID 来自另一数据库的 Better Auth，与 012–014 一致，由注销服务显式删除（已测试）。
- 回滚会删除推荐三表数据，只在隔离空库演练；真实环境执行前需人工核对版本与备份。未在任何共享库运行迁移。

## 5. 测试结果

数据库测试均在上述隔离库运行；表中“跳过”均为实际数字，没有以 Skip 计 Pass。

| 分类 | 通过 | 失败 | 跳过 | 说明 |
|---|---:|---:|---:|---|
| 推荐 + 阅读历史（PostgreSQL） | 45 | 0 | 0 | `test_recommendation` 38（新增 13）+ `test_reading_history` 7 |
| 互动/快照/注销持久化（PostgreSQL） | 18 | 0 | 0 | 阶段 2 完整回归 |
| 互动/统计/文库/身份/注销/主题/已读/发现 API 与单元 | 48 | 0 | 0 | |
| 迁移回归（各自空库） | 2 | 0 | 0 | 011–014 与 014↔015 |
| Backend 全部 59 个模块，无数据库 | 548 | 0 | 63 | 63 项为需 `CHAT_DATABASE_URL`/迁移库的用例，已在上面各组实际运行 |
| Backend 全部 59 个模块，设置隔离库 | 600 | 9 | 2 | 9 项失败在**未修改的 origin/dev** 上同环境复现完全相同（agent asset、agent session、anonymous claim、`acceptance_2a` 环境检查，源于这些测试在启用 Postgres 仓储时的跨事件循环/替身假设），与本轮无关；2 项跳过为两条迁移测试，已单独运行 |
| Frontend 全套 `pnpm test` | 465 | 0 | 0 | 基线 457，新增 8；推荐/互动/缓存/发现相关 34 项 |
| TypeScript `pnpm typecheck` | 通过 | | | |
| ESLint `pnpm lint` | 0 错误 | | | 2 个既有警告（`use-chat-session.ts:472`、`use-popover-placement.ts:37`），与本轮无关 |
| 生产构建（隔离环境） | 通过 | | | 31/31 静态页 |
| `compileall`、`git diff --check` | 通过 | | | |

新增回归覆盖：后续页失败保留已加载页并从同一游标恢复、30 条无重复无断档；过期 409 不回退、显式重置后从第一页重建；
账号切换前置条件 409 不被当作过期；首屏空推荐整表降级；账号切换清理 `home-feed`；事件只带前置条件不带 owner；
召回非预期异常/超时隔离且日志不含查询词；查询数上限与跨来源去重；元数据异常不伪造特征；
快照全量遍历无重复、同游标重读一致、仅一次召回；过期/他人/缺失/格式错误游标；反馈必须匹配快照论文与名次；
多文件夹收藏、移动、删除文件夹只产生真实状态转换；并发收藏到不同文件夹只记 1 次；容量失败事件回滚；注销清理三表且不影响他人。

环境说明：`uv lock --check` 通过；在新 Worktree 用 `uv sync --locked` 与 `pnpm install --frozen-lockfile`
建立独立环境，未改依赖锁文件。此前记录的“lockfile needs to be updated”在当前 uv 0.12.2 / Python 3.12.13 下未复现。

实际命令（`apps/backend`，UV 缓存置于 `/private/tmp/shenzhi-uv-cache`）：

```bash
CHAT_DATABASE_URL=postgresql://shenzhi_test@127.0.0.1:55441/shenzhi_rec_test \
  uv run --locked --no-sync python -m unittest tests.test_recommendation tests.test_reading_history
CHAT_DATABASE_URL=postgresql://shenzhi_test@127.0.0.1:55441/shenzhi_rec_test \
  uv run --locked --no-sync python -m unittest tests.test_interactions_persistence tests.test_stats_snapshot tests.test_account_deletion_persistence
SHENZHI_MIGRATION_TEST_URL=postgresql://shenzhi_test@127.0.0.1:55441/shenzhi_rec_migration_test \
  uv run --locked --no-sync python -m unittest tests.test_interaction_migrations
SHENZHI_MIGRATION_TEST_URL=postgresql://shenzhi_test@127.0.0.1:55441/shenzhi_rec2_migration_test \
  uv run --locked --no-sync python -m unittest tests.test_recommendation_migrations
uv run --locked --no-sync python -m compileall -q app tests
# apps/web
pnpm test && pnpm typecheck && pnpm lint
```

## 6. 真实链路验收

环境：生产构建的 Next（`127.0.0.1:53041`）+ 真实 Better Auth + 真实 BFF + 真实 FastAPI（`127.0.0.1:58041`）
+ 隔离 PostgreSQL。Web 环境变量由临时脚本显式覆盖，Worktree 无 `.env*`；账号为本轮在隔离库创建的合成账号
`rec-user-a/b`。启动脚本只替换 Knowledge 上游（见 §7），并可通过标志文件注入推荐 503。脚本、日志位于本次会话临时目录，未提交。

BFF/HTTP 9 个场景全部通过：

1. 匿名：全局发现 200（12 条）；推荐接口 401。
2. A 冷启动：48 条/4 页，单一 request_id，理由“来自论文发现”（无历史保持发现顺序）。
3. A 点赞、两文件夹收藏 + 移动、关注 `reinforcement-learning`、搜索提交 + 结果点击、两次详情、标记已读、有效阅读，
   数据库各写入 1 条：`paper_like/paper_collect/topic_follow/search_submit/search_result_click/paper_detail_view/paper_read/active_read`；
   结果点击 `query_id` 与搜索一致；重复 `event_id` 新增 0。
4. 伪造 `user_id` 422；非推荐事件带 `request_id` 422；B 冒用 A 的 request_id 400；A 本人推荐点击 200；前置条件不符 409。
5. 画像重建：`long_topics = {reinforcement learning: 1, robotics: 0.64, deep learning: 0.07}`；推荐 72 条/6 页无重复无断档，
   首屏 12/12 带个性化理由（首条“与你关注的主题相匹配”），已赞/已藏论文被过滤。
6. 取消点赞与关注后画像立即刷新，`explicit_subjects = []`。
7. B：`has_history=false`，独立快照，使用 A 的游标 409。
8. 注入推荐 503 时全局发现仍 200。
9. 过期快照游标 409。

浏览器（应用内浏览器，生产构建页面）：

- 匿名首页 12 张发现卡片、无推荐理由。
- A 登录后首屏显示“与你的研究主题相关”等理由。
- **中途分页失败**：注入后续页 503 后滚动，游标 `…:12` 请求 503（自动重试 1 次），12 张已加载卡片保持不变，
  显示“后续论文加载失败，已加载内容不受影响”和“重试加载”，无任何 discovery 请求；解除故障点击重试后从 `…:12` 继续，
  持续滚动至“已浏览完全部 78 篇论文”，78 张全部唯一，游标 12→72 依次递增、同一 request_id。
- 数据库：A 的 17 条推荐曝光与 1 条推荐点击全部匹配对应快照中的论文与名次。
- **快照过期**：数据库将当前快照设为过期后滚动，`…:12` 返回 409 一次（不自动重试），显示“推荐列表已过期”与“刷新推荐”，
  无 discovery 请求；点击后重新请求第一页。
- **首屏故障降级**：注入首屏 503 并刷新，推荐请求 1 次后显示全局发现；继续滚动按发现游标分页，24 张唯一，不再请求推荐。
- **账号切换**：退出 A、登录 B 后首页仅有冷启动理由“来自论文发现”，不出现 A 的个性化结果。
- **论文详情**：B 从推荐卡片进入详情，写入 `recommendation_click(rank=1, 带 request_id)` 与 `paper_detail_view`。
- 后端日志中唯一错误为 5 条注入的 503；私有搜索词未出现在 Backend 或 Web 日志中。

未在浏览器验证：PDF 前台有效阅读。Mock 论文没有 PDF 链接，阅读器正确显示“暂无可用 PDF”且不产生 `active_read`；
该能力本轮由 BFF 真实写入（场景 3）与 `ActiveReadTracker` 单测覆盖，需在真实知识底座环境补做浏览器验收。
应用内浏览器面板隐藏时 IntersectionObserver 需截图触发渲染，导致 B 的曝光未产生，`evaluation` 的聚合输出中
`clicks_with_impression=0` 属验收环境产物，不代表埋点缺陷（A 的浏览器曝光已正常写入）。

## 7. Mock Knowledge 与真实科研服务的边界

- **Mock**：`KnowledgeService.get_paper / search / search_by_subject` 在验收启动脚本中替换为确定性实现，语料为仓库打包的
  300 篇发现快照；`subjects/keywords` 由标题规则生成（快照本身 0/300 有主题与关键词）。推荐召回、画像所用元数据、
  论文详情均来自该 Mock，故 §6 中画像数值与推荐命中只证明**产品链路与个性化逻辑正确**，不代表真实知识底座的召回质量。
- **真实**：Better Auth、BFF、FastAPI 路由与 Service、PostgreSQL、迁移、事件、画像、快照、分页、前端 Feed 均为仓库真实实现。
- **未做**：真实科研知识底座在线联调、真实 PDF 资源、字段覆盖率与接口限流确认。

## 8. 遗留问题

### P0（合入前必须解决）

无本轮范围内已知阻塞项。

### P1（建议后续处理）

- 真实知识底座联调：确认 `subjects/keywords` 覆盖率、`search_by_subject` 匹配规则、限流与延迟；首屏推荐最坏耗时约为
  画像元数据 6s + 召回 5s，需在真实环境测量并决定是否异步预计算画像。
- 浏览器 PDF 有效阅读需在真实 PDF 环境复验。
- 线上清理调度：维护 CLI/接口已就绪，但未注册任何 Cron；部署负责人需选择调度方式并配置 `CRON_SECRET`（若使用接口）。
- 首页搜索框（`search-hero`）记录的 `search_submit` 与跳转后的结果点击没有共享 `query_id`（仅知识搜索页内提交有关联），
  评估中会计入“点击无 query_id”。
- 原始搜索词按设计存于 `behavior_events.entity_id` 90 天并进入画像短期关键词；普通日志不记录，但数据库访问权限与保留策略属隐私边界。
- 9 个既有 agent/claim 测试在设置 `CHAT_DATABASE_URL` 时失败（dev 同样复现），应由对应模块负责人修复测试隔离。

### P2（可以暂缓）

- 注销与进行中的首屏推荐请求并发时，可能在注销后写入一条 1 小时内过期的快照或画像行；由过期与维护清理兜底。
- 速率限制把重复 `event_id` 也计入每分钟 120 条预算。
- 全局发现候选没有主题/关键词，有历史用户中只能以 ≤0.15 分数补位。
- `content-v1` 权重为未经实验验证的基线；离线评估仅 1 个查询、13 个候选、单人临时标注（本轮复算指标与已存文件一致），
  不能作为算法有效性证据。未做 Embedding、训练或 A/B 平台。

## 9. 合并判断

**可以提交 PR 合入 dev（待人工审查）。**

推荐功能以原始两个提交按序集成，阶段 2 的账号级锁、事务一致性、容量限制、缓存隔离与前置条件均被保留并通过完整回归；
首页分页降级缺陷已修复并经单元、真实 TanStack Observer、BFF 与浏览器验证；迁移链单一 Head 且回滚验证通过；
未改动部署配置与依赖锁文件。审查重点建议：`discovery-feed.ts` 降级语义、`409` 游标契约、`collections.py` 冲突处理。

## 10. 本地提交与变更清单

当前分支：`integration/search-recommendation`（Worktree `../shenzhi-search-rec`，无上游跟踪），
相对 `origin/dev@24e9233` 领先 4、落后 0（含本报告提交）。

```text
7b7028c factor：简单构建搜索推荐算法，准备引入向量模型（cherry-pick cd1f846，含冲突说明）
6af95e0 fix:阅读记录去重、刷新用户画像策略、用户活跃阅读统计（cherry-pick 140557b）
b5ddaee fix: 修复推荐分页降级、召回隔离与事件归因并对齐互动基础层
<本提交> docs: 补充搜索推荐集成验收报告
```

相对 dev 的完整差异文件（48 个）：

```text
apps/backend/.env.example
apps/backend/README.md
apps/backend/app/api/behavior.py
apps/backend/app/api/maintenance.py
apps/backend/app/api/recommendations.py
apps/backend/app/main.py
apps/backend/app/models/recommendation.py
apps/backend/app/schemas/behavior.py
apps/backend/app/services/library/collections.py
apps/backend/app/services/library/paper_likes.py
apps/backend/app/services/library/reading_history.py
apps/backend/app/services/library/topic_follows.py
apps/backend/app/services/recommendation/behavior.py
apps/backend/app/services/recommendation/config.py
apps/backend/app/services/recommendation/evaluation.py
apps/backend/app/services/recommendation/features.py
apps/backend/app/services/recommendation/maintenance.py
apps/backend/app/services/recommendation/profile.py
apps/backend/app/services/recommendation/recommendations.py
apps/backend/app/services/user/account_deletion.py
apps/backend/evaluation/recommendation-judgments/README.md
apps/backend/evaluation/recommendation-judgments/robot-visuomotor-v0.json
apps/backend/evaluation/recommendation-judgments/robot-visuomotor-v0.metrics.json
apps/backend/migrations/env.py
apps/backend/migrations/versions/015_recommendation_foundation.py
apps/backend/tests/test_interaction_migrations.py
apps/backend/tests/test_paper_read_status.py
apps/backend/tests/test_reading_history.py
apps/backend/tests/test_recommendation.py
apps/backend/tests/test_recommendation_migrations.py
apps/web/clients/backend/behavior.ts
apps/web/clients/backend/recommendations.ts
apps/web/components/common/expandable-abstract.tsx
apps/web/features/knowledge/interactions/cache.ts
apps/web/features/knowledge/search/KnowledgeSearchPage.tsx
apps/web/features/knowledge/search/components/result-card.tsx
apps/web/features/knowledge/search/components/results-section.tsx
apps/web/features/papers/[id]/PaperDetailPage.tsx
apps/web/features/papers/active-read-tracker.ts
apps/web/features/search/components/feed-list.tsx
apps/web/features/search/components/paper-card.tsx
apps/web/features/search/components/search-hero.tsx
apps/web/features/search/services/discovery-feed.ts
apps/web/tests/knowledge/recommendation-feed.test.ts
apps/web/types/index.ts
docs/engineering/search-recommendation-delivery.md
docs/engineering/search-recommendation-implementation.md
docs/knowledge/INTERACTIONS-AND-STATS.md
```

未变更：`apps/backend/vercel.json`、`apps/backend/uv.lock`、`apps/backend/pyproject.toml`、`apps/web/pnpm-lock.yaml`、
`apps/web/package.json`、`012`–`014` 迁移文件。临时 PostgreSQL 集群仍在 `127.0.0.1:55441` 运行，
可用 `pg_ctl -D /private/tmp/shenzhi-rec-pg-20261030 stop` 停止并删除该目录。
