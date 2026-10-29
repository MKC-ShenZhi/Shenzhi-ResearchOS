# 收藏人数、论文点赞与主题关注

本文记录 `feat/likes-bookmarks-follows` 落地的账号级互动数据、平台级统计快照与知识底座
只读接口。范围包含两期能力：论文收藏人数与主题关注（一期），以及论文点赞持久化、每日
聚合快照与知识底座只读服务（二期）。

## 一、口径与边界

- **用户级数据**：某个已登录用户收藏了哪些论文、点赞了哪些论文、关注了哪些主题。
  `user_id` 只来自 Better Auth → Next.js BFF → FastAPI 身份链，任何接口都不接受浏览器
  传入的用户 ID。
- **平台级数据**：某个 `paper_id` 被多少**独立用户**收藏/点赞，某个 `topic_id` 被多少
  独立用户关注。平台统计只有聚合数，不向知识底座输出用户 ID、文件夹或行为明细。
- **收藏人数**：`collection_items JOIN collection_folders` 后
  `COUNT(DISTINCT collection_folders.user_id)`。同一用户把一篇论文放进三个文件夹仍计 1；
  在文件夹间移动人数不变；从最后一个文件夹移除才减 1。
- **点赞人数 / 关注人数**：同样按 distinct user 统计，由 `(user_id, paper_id)`、
  `(user_id, topic_id)` 唯一键保证同一用户重复点击不会多计。
- `paper_count`（文件夹内论文数）与 `collector_count`（全平台独立收藏用户数）是不同口径，
  界面不得混用。
- 目录 `topic_catalog.json` 的 `followersCount` 只是历史快照（当前全部为 0），不再是人数
  来源；目录文件本身不改写，真实人数在接口层覆盖。

## 二、数据模型

| 迁移 | 表 | 说明 |
|---|---|---|
| `012_topic_follows` | `topic_follows(user_id, topic_id, created_at)` | 主键 `(user_id, topic_id)`；索引 `(topic_id)`、`(user_id, created_at)` |
| `013_paper_likes` | `paper_likes(user_id, paper_id, created_at)` | 主键 `(user_id, paper_id)`；索引 `(paper_id)`、`(user_id, created_at)` |
| `014_platform_snapshots` | `stats_snapshot_runs`、`paper_stats_daily`、`topic_stats_daily` | 每日聚合发布状态与明细 |

`stats_snapshot_runs.snapshot_date` 为主键；`status in ('completed','failed')`；
`paper_stats_daily`、`topic_stats_daily` 通过外键级联到当日运行记录。

## 三、身份与可见性

| 接口 | 身份 | 匿名 |
|---|---|---|
| `POST /api/v1/papers/interactions` | `request_identity` | 只返回公开人数，`folder_ids` / `liked` 为 `null` |
| `POST /api/v1/topics/interactions` | `request_identity` | 只返回公开人数，`is_following` 为 `null` |
| `PUT/DELETE /api/v1/papers/{paper_id}/like` | `require_user` | 401 |
| `PUT/DELETE /api/v1/topic-follows/{topic_id}` | `require_user` | 401 |
| `GET /api/v1/likes`、`GET /api/v1/topic-follows` | `require_user` | 401 |
| `GET /api/v1/stats/*` | `require_stats_service` | 不接受 BFF/用户身份 |

写操作返回服务端重新统计的人数，前端以此为准，不做本地 +1/-1 推算。

个人列表读取与互动写入携带可选 `x-shenzhi-expected-user-id` 前置条件。BFF 只转发此条件，
仍从 Better Auth 注入真实身份；FastAPI `require_user` 在两者不一致时返回 409，且不调用
业务服务。条件不能指定请求所属账号，仅用于阻止旧页面请求在 Cookie 切换后读写新账号。

BFF 对 JSON 请求体保留可重放文本，空请求不附带流式请求体，以确保 Node fetch 能正常
传递后端 401（不可重放的流式请求体会导致 `expected non-null body source`，被误报成 503）。
二进制上传继续使用原有流式传输。

## 四、批量读接口

```text
POST /api/v1/papers/interactions   {"paper_ids": ["…"]}          ≤ 100 个，自动去重
POST /api/v1/topics/interactions   {"topic_ids": ["…"]}          ≤ 100 个，自动去重
```

响应：

```json
{
  "authenticated": true,
  "user_id": "user-id-or-null",
  "items": [
    {
      "paper_id": "paper:xxxx",
      "collector_count": 3,
      "like_count": 1,
      "folder_ids": [7],
      "liked": true
    }
  ]
}
```

`user_id` 是本次身份的回显，前端用它检测“请求期间账号已切换”，不参与个人数据查询。

## 五、每日平台快照

### 生成与发布

```bash
uv run --env-file .env python -m app.services.stats               # 上海时区当天
```

- 论文行覆盖“当天在收藏或点赞关系中出现过的论文”，无互动论文不产生行，读取方按 0 处理；
  也可用 `paper_id` 精确查询并得到 `missing_paper_ids`。
- 主题行覆盖目录中全部启用主题（当前 293 条），因此知识底座能读到完整集合（含 0）。
- 生成事务采用 PostgreSQL `REPEATABLE READ`，收藏、点赞、关注使用同一个 MVCC 视图。
  首次读取前以 `SHARE ROW EXCLUSIVE` 锁串行化所有快照生成任务；普通统计查询不被该锁阻塞。
- 当日运行记录、当日全部明细行在同一事务内写入并提交；读取方只采纳
  `status='completed'` 的日期，单次分页/精确查询也采用只读 `REPEATABLE READ`，
  使发布元信息、总数和明细始终来自同一版数据。
- 同日重跑会删除当日旧行并整体替换；失败时事务回滚，上一次完整发布继续对外可见，
  `failure_reason` 只记录最近一次尝试的错误类型。
- CLI 只生成运行时上海时区的当天快照。源表只保存当前有效关系，不能用当前人数回填过去日期并称作历史统计。
- 调度不在仓库内实现。部署侧用 cron / systemd timer / 平台调度器每日调用一次 CLI；
  仓库不预设已有 Cron 配置。
- `SNAPSHOT_VERSION` 常量标识计算口径版本，随快照写入并随接口返回。

### 只读服务接口

```text
GET /api/v1/stats/meta                                      发布状态与最新日期
GET /api/v1/stats/papers?date=&limit=&cursor=&paper_id=…     论文收藏/点赞人数
GET /api/v1/stats/topics?date=&limit=&cursor=&topic_id=…     主题关注人数
```

- 鉴权：请求头 `x-shenzhi-stats-token`，值来自 `STATS_SERVICE_TOKEN`。未配置返回 503，
  不匹配返回 401。该凭据与 `BACKEND_BFF_SECRET` 和用户会话完全分离，只打开
  `/api/v1/stats/*`，不能读取 `/api/v1/likes` 等个人数据。
- `date` 省略时使用最近一次完整发布日；`limit` 1–500，默认 100；分页使用不透明游标，
  游标绑定发布日期、资源类型与本次 `computed_at`。不合法或类型不符返回 400；
  同日重建后使用旧游标返回 409，读取方应从第一页重新同步，以免跨页混入不同发布结果。
  原分支仅绑定日期的旧格式游标也需从第一页重新获取。
- `paper_id` / `topic_id` 可直接精确查询（≤100 个），与游标互斥；未命中的 ID 通过
  `missing_paper_ids` / `missing_topic_ids` 显式返回，由调用方按 0 处理。

## 六、前端交互

- 收藏：匿名点击直接调用 `useAuth().openLogin()`；登录成功后只重新打开文件夹选择器，
  仍需用户点击“确认”才写入。
- 点赞与主题关注：匿名点击同样只弹出登录窗口，登录后由用户再次点击；按钮在请求进行中
  禁止重复提交。服务端返回 401（会话失效）时重新走登录窗口。
- 卡片通过 `clients/backend/interactions.ts` 的微批队列读取：同一事件循环内的所有卡片
  合并为一次请求，每批最多 100 个 ID，避免逐卡 N+1。
- 缓存键包含身份（登录用户 ID 或匿名的空串）；账号切换或退出后，其他身份的个人状态
  及个人列表缓存被移除，会话解析期间隐藏个人互动状态，收藏选择草稿按账号/论文重建。
- 写入成功后先取消旧读请求再失效对应 TanStack Query 缓存，统一刷新卡片、详情、点赞/
  收藏/关注列表和文件夹内容。`BroadcastChannel` 只提供失效通知，接收方重新读取服务端，
  不把消息中的个人字段当成真实状态。其他账号/匿名标签页也刷新公开人数，但各自查询自己的关系。
- 收藏选择器在关系读取失败或未完成时禁止确认，避免把未加载的空数组误提交为清空收藏。
- 收藏替换、移动、移除和文件夹删除通过既有 `collection_user_states` 行锁按账号串行化。
  替换为空集合或不同目标文件夹也使用同一锁，避免并发替换错误合并；移动到已满文件夹会
  整体回滚，来源关系保留。
- `stores/user-preferences.ts` 不再保存 `followedTopics`、`likedPapers`、
  `bookmarkedPapers`；持久化版本升到 2，旧浏览器的这三个字段在迁移时直接丢弃，
  不导入账号。

## 七、账号注销

`AccountDeletionService` 在同一事务内额外删除 `paper_likes` 与 `topic_follows`；
下一次查询与下一次快照即反映人数变化。推荐阶段（`015_recommendation_foundation`）集成后，
同一事务还删除该用户的 `behavior_events`、`user_interest_profiles` 与 `recommendation_snapshots`。

点赞/取消点赞、关注/取消关注、收藏状态变化会在原业务事务内追加推荐行为事件（由服务端写入，
浏览器不能提交这些类型）。收藏事件按“用户 × 论文”判定：加入第二个文件夹、文件夹间移动不产生
事件，删除最后一个包含该论文的文件夹或移除最后一处收藏才记 `paper_uncollect`；
沿用本文的账号级行锁与 100 篇容量限制，容量失败时事件随事务回滚。

## 八、已知边界

- **论文 ID 未做归一化**（本期决定）：人数严格按 `paper_id` 字符串统计。现有数据里同时
  存在 `paper:2503.22087v3` 与 `paper:2501.18116`（无版本）等格式，同一 arXiv 论文若以
  不同版本 ID 出现，会被当成两个统计对象。需要知识底座确认 ID 长期稳定、跨来源唯一后，
  再决定是否统一版本号并迁移历史收藏数据。
- 平台快照只覆盖有互动记录的论文，没有全量论文清单可枚举。
- 快照按 `Asia/Shanghai` 自然日切分；跨时区读取方需自行换算。
- `/knowledge/papers` 的“点赞与收藏”面板提供账号的点赞论文、跨文件夹收藏论文和关注主题，
  支持取消关系；论文列表分页、搜索当前页。上游元数据不可用时遵循既有 Knowledge 错误契约。
- 账号注销保留已经发布的匿名历史汇总；实时人数和后续重建/新快照反映关系删除。
- 本阶段不配置线上调度，不集成推荐与请求幂等 Feature；迁移链为
  `011_agent_uploads → 012_topic_follows → 013_paper_likes → 014_platform_snapshots`。
  推荐集成后链尾追加 `015_recommendation_foundation`，见
  [`search-recommendation-delivery.md`](../engineering/search-recommendation-delivery.md)。

## 九、验收对照

| 场景 | 预期 |
|---|---|
| 一用户在 3 个文件夹收藏同一论文 | 收藏人数 +1 |
| 两个账号收藏同一论文 | 显示 2；任一账号移除后显示 1 |
| 匿名点击收藏/点赞/关注 | 只弹出登录窗口，不产生任何写入 |
| 登录后打开收藏选择器 | 仍需确认文件夹才写入 |
| 多卡片列表加载 | 单次批量请求，无逐卡请求 |
| 切换账号 | 个人状态互不串用，公开人数保留 |
| 注销账号 | 收藏、点赞、关注关系清除，人数重新计算 |
| 同日重跑快照 | 无重复行，读取方只看到完整结果 |
| 快照生成失败 | 上一次完整发布仍可读，失败原因被记录 |
| 知识底座凭据 | 只能读 `/api/v1/stats/*`，读不到个人数据 |


## 十、隔离验收

仅将下列变量指向已确认的临时 PostgreSQL 实例，禁止使用生产连接。迁移回滚测试独立使用
`SHENZHI_MIGRATION_TEST_URL`，拒绝非本机、非 `*_migration_test` 或非空数据库；
不会隐式回退到 `CHAT_DATABASE_URL`。

```bash
cd apps/backend
CHAT_DATABASE_URL="$LOCAL_INTERACTION_TEST_URL" uv run --locked alembic upgrade head
CHAT_DATABASE_URL="$LOCAL_INTERACTION_TEST_URL" uv run --locked python -m unittest \
  tests.test_interactions_persistence tests.test_stats_snapshot tests.test_account_deletion_persistence -v
SHENZHI_MIGRATION_TEST_URL="$EMPTY_LOCAL_MIGRATION_TEST_URL" uv run --locked python -m unittest \
  tests.test_interaction_migrations -v
```

数据库测试未配置连接时的 Skip 不代表通过。迁移测试执行后会留下升级至 014 的测试表，
重复验收需另建空库；实际环境回滚会删除互动关系与快照，不能作为无损操作。
