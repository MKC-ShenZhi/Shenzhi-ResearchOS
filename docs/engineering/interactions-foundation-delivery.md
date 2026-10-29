# 互动数据基础层集成验收报告

验收日期：2026-10-29（Asia/Tokyo）。验收对象：本地 `integration/likes-foundation`。
结论：**可以合入 dev，等待人工审查**。本轮未 Push、未创建 PR、未执行远程 Merge；
未操作生产数据库、未修改 Vercel 配置、未集成推荐算法或请求幂等 Feature。

## 1. Git 状态

- 开始时工作区干净，当前本地 dev 与更新后的远程基线一致；已实际执行 `git fetch origin`。
- 基线：`origin/dev = 4ef05d95822889b9c3a92e6b150628c8469f97a8`。
- Feature：`e0ba0151a146e9d0cc0224d93b1b87a04e919f2d`，重新检查仍领先 4、落后 0，原始差异 58 文件。
- 使用 `git switch -c integration/likes-foundation origin/dev` 后本地 `merge --no-ff`，保留有效实现与原始历史，无冲突。
- 原始提交（按时间顺序）：
  - `937ef94`：feat/收藏、点赞初步实现
  - `64cf279`：factor：构建”点赞与收藏”页面，呈现用户点赞详情
  - `d110a59`：Merge branch 'dev' into feat/likes-bookmarks-follows
  - `e0ba015`：fatctor：完善“点赞”“收藏”“关注”全局功能
- 本轮本地提交：
  - `893368f`：merge: 集成互动数据基础层原始实现
  - `5e5b913`：fix: 修复互动并发一致性与快照发布隔离
  - `2f6913f`：fix: 统一互动状态同步并修复账号切换与鉴权错误转发
  - 本报告及接口说明以 `docs: 补充互动基础层集成验收报告` 独立提交；最终哈希见交付消息与 `git log`。
- 包含最终文档提交后，相对基线预计领先 8、落后 0，共 66 个差异文件；最终状态由交付时再次核查。
- `pnpm-lock.yaml`、`uv.lock` 均未修改；`015_recommendation_foundation`、`012_request_idempotency` 均未引入。

## 2. 已完成能力

原分支已有并保留：

- 论文收藏人数按 `COUNT(DISTINCT user_id)` 计算；多个文件夹不重复计人。
- 论文点赞和主题关注持久化；复合主键与 `ON CONFLICT DO NOTHING` 保证重复写入安全。
- 主题关注校验启用的 Topic Catalog；已下架主题仍可取消关注。
- Better Auth → BFF → FastAPI 的可信身份、匿名公开人数、登录后个人状态与受限写入。
- 个人点赞/收藏/关注面板、卡片与详情互动组件、批量读取和账号缓存键。
- 平台统计 CLI、每日汇总表、独立服务凭据的只读统计接口、账号清理互动关系。

本轮实际增强：

- 收藏关系变更的并发串行化；文件夹移动容量校验及失败回滚。
- 快照源读取、生成、单次读取与跨页版本一致性。
- 同页面、跨页面、跨标签页和个人文献库的统一缓存失效。
- 账号切换时异步响应隔离、个人列表清理、收藏草稿隔离与保存前读取就绪检查。
- 账号前置条件避免 Cookie 切换后的旧页面请求误读写新账号。
- 修复真实 BFF 对匿名受限写入错误返回 503 的问题。

## 3. 修复的问题

| 问题及原因 | 修改位置 | 修复措施与验证 |
|---|---|---|
| 并发替换到不同收藏夹时只锁目标文件夹，结果可能错误合并；空集合也没有锁 | `services/library/collections.py` | 使用既有 `collection_user_states` 行锁，替换/移动/移除/删除共用账号锁；真实 PostgreSQL 并发替换回归通过 |
| 移动论文绕过目标文件夹 100 篇容量限制 | 同上 | 添加目标容量检查；失败时事务回滚并保留来源关系；容量、移动人数及最后文件夹删除回归通过 |
| 默认 READ COMMITTED 下三类快照统计可能混入注销等并发变更 | `services/stats/snapshot.py` | REPEATABLE READ；首次 MVCC 读取前表锁串行化生成；生成期间注销、并发首次生成及重建均通过 |
| 读取快照元信息、总数、明细时可能跨越重建提交 | `services/stats/service.py` | 单次查询用只读 REPEATABLE READ；读取期间重建回归保持旧版元信息与旧版明细一致 |
| 游标仅绑定日期，同日重建后继续分页可能混入不同结果 | 同上 | 绑定日期、资源类型及 computed_at；类型不符 400，重建旧游标 409；保留“不透明游标”接口契约，旧格式需重新开始分页 |
| 写入只更新部分卡片缓存，点赞/收藏/关注列表及文件夹内容可能保持旧值 | `features/knowledge/interactions/cache.ts`、相关 Hooks、`library-table.tsx`、`interaction-sync.tsx` | 取消旧读后统一失效 TanStack Query；文件夹论文列表复用 Query；广播触发服务端重读；QueryObserver、真实多标签页验证通过 |
| 账号切换只清理单项互动缓存，个人列表、旧回调和草稿仍可能带入旧身份 | `core/identity.py`、Backend Client/BFF、互动 Hooks、收藏选择器、文献库页面 | 捕获 mutation owner/generation，清理全部个人互动缓存；读取期间隐藏个人状态；草稿按账号/论文重建；可选 expected-user 前置条件只拒绝请求、不提供身份；真实 A→退出→B 验证通过 |
| 收藏关系读取失败时默认空数组仍可确认，可能误清空收藏 | `collection-picker.tsx` | 关系读取完成前禁止保存，失效或旧账号结果不得初始化新草稿 |
| Node fetch 对流式请求体遇 401 抛出 `expected non-null body source`，BFF 将其误映射为 503 | `clients/backend/forward.ts` | JSON 请求体可重放、空请求不附带流；二进制继续流传输；新增 3 个回归测试，最终生产构建真实匿名 PUT 返回 401 |
| 测试依赖旧回调代码文本、预存第二篇论文或残留连接池 | 互动前端测试、快照与账号清理测试 | 更新实际回调断言，保留“登录不自动提交”约束；分页自行准备第二篇数据，保留 has_more 断言；按事件循环关闭连接池；未删除或跳过重要断言 |

## 4. 测试结果

以下为最终代码实际结果；数据库测试没有以 Skip 充当 Pass。

| 分类 | 通过 | 失败 | 跳过 | 说明 |
|---|---:|---:|---:|---|
| Backend 单元/API/身份/主题目录 | 33 | 0 | 0 | mock 外部或持久化边界 |
| PostgreSQL 互动/快照/注销集成 | 18 | 0 | 0 | 新建独立本地集群，真实数据库并发 |
| PostgreSQL 迁移回归 | 1 | 0 | 0 | 第二个空库，含逐级回滚与重升 |
| Frontend 全套现有脚本 | 440 | 0 | 0 | 含新增 QueryObserver、账号缓存和 BFF body 回归 |
| 真实 Better Auth/BFF HTTP 验收 | 8 场景 | 0 | 0 | 临时虚构账号 A/B；真实 Web、FastAPI、PostgreSQL |
| 真实统计 HTTP 验收 | 4 场景 | 0 | 0 | 完整发布、最新人数、无用户明细、独立服务身份 |

其他检查：`compileall`、TypeScript、`git diff --check` 通过。
Lint：0 错误、2 个既有警告，位于 `use-chat-session.ts:472` 与 `lib/use-popover-placement.ts:37`；
本轮文件没有新增警告。生产构建通过，31/31 静态页生成完成。

实际命令（工作目录分别为 `apps/backend` 与 `apps/web`）：

```bash
# Backend，无数据库的单元测试
CHAT_DATABASE_URL= UV_CACHE_DIR=/private/tmp/shenzhi-uv-cache uv run --locked --no-sync python -m unittest \
  tests.test_interactions_api tests.test_stats_api tests.test_library_api tests.test_identity \
  tests.test_account_deletion_api tests.test_account_deletion_runtime tests.test_topic_catalog -v
UV_CACHE_DIR=/private/tmp/shenzhi-uv-cache uv run --locked --no-sync python -m compileall -q app tests

# Backend，真实隔离 PostgreSQL
CHAT_DATABASE_URL=postgresql://shenzhi_test@127.0.0.1:55439/shenzhi_interactions_test \
UV_CACHE_DIR=/private/tmp/shenzhi-uv-cache uv run --locked --no-sync python -m unittest \
  tests.test_interactions_persistence tests.test_stats_snapshot tests.test_account_deletion_persistence -v

# 独立空库迁移回归
SHENZHI_MIGRATION_TEST_URL=postgresql://shenzhi_test@127.0.0.1:55439/shenzhi_interactions_migration_test \
UV_CACHE_DIR=/private/tmp/shenzhi-uv-cache uv run --locked --no-sync python -m unittest tests.test_interaction_migrations -v

# Frontend
pnpm test
pnpm typecheck
pnpm lint
python3 /private/tmp/shenzhi-isolated-web.py build  # 内部执行 pnpm build，所有本地 .env 值被屏蔽/覆盖
node /private/tmp/shenzhi-bff-acceptance.mjs

# 既有统计 CLI 在同日执行两次
CHAT_DATABASE_URL=postgresql://shenzhi_test@127.0.0.1:55439/shenzhi_interactions_test \
UV_CACHE_DIR=/private/tmp/shenzhi-uv-cache uv run --locked --no-sync python -m app.services.stats
```

`--no-sync` 使用仓库已有环境，UV 缓存置于临时可写目录；没有升级依赖或改动锁文件。
隔离构建脚本在 `/private/tmp`，不属于产品代码；对 `.env.local` 的每个配置键设置覆盖值，
数据库指向本次本地集群，后端为 `127.0.0.1:58029`，认证使用临时测试值，关闭本地测试 Turnstile，
无部署或 Vercel 操作。CLI 仍使用上海自然日；本次两次发布均为 2026-10-29。

浏览器在最终生产构建本地预览完成：

- 匿名点击点赞打开现有登录弹窗，登录后不自动点赞。
- A 收藏同一论文到 3 个文件夹，公开人数 1；个人汇总仅一行。
- 首页、详情状态一致；详情取消点赞会同步另一个首页标签页。
- 另一标签页点赞可刷新已打开的个人点赞列表。
- 个人面板取消全部收藏，文件夹数与详情公开人数同步归零。
- 退出后个人内容隐藏；B 登录后点赞/收藏/关注不继承 A，仍能看到公开人数。
- 同一主题的两个卡片同步关注；个人关注列表可取消。
- 最终两账号点赞同一论文：详情人数 2，B 的个人列表仅 1 条。

浏览器只替换科研上游论文元数据为仓库静态样本；认证、互动 API、Service、BFF 和 PostgreSQL
都是真实实现。未将这些检查表述为真实科研服务的在线联调。关键页面控制台无错误。
截图和临时测试脚本保留于 `/private/tmp/shenzhi-acceptance-evidence/` 及本次工具输出，未提交。

已处理的中间失败：首轮前端 431/432（旧回调断言）；首轮数据库 9/10（分页依赖预存数据）；
隔离构建初次配置将布尔值置空导致失败，修正临时脚本后通过；首轮 BFF HTTP 匿名写入返回 503，
定位并修复产品转发后 8/8。沙箱中无法写 Git 元数据、创建共享内存或连接本机测试端口的命令，
按用户授权重试本地受限操作；没有将环境失败或中断的构建计为通过。

## 5. 数据库迁移

- 本次临时创建 PostgreSQL 16.15 集群，数据目录 `/private/tmp/shenzhi-interactions-pg-20261029`，
  仅监听 `127.0.0.1:55439`；账号 `shenzhi_test` 无真实凭据。未读取或连接生产库。
- 测试前从空库实际升到 dev 的 `011_agent_uploads`，确认该版本后升至 `014_platform_snapshots`。
- 唯一 Head：`014_platform_snapshots`。
- 迁移链：`011_agent_uploads → 012_topic_follows → 013_paper_likes → 014_platform_snapshots`。
- 第二个空库实际执行 `011 → 014 → 013 → 012 → 011 → 014`；验证复合主键、索引、快照级联外键、
  非负约束存在，回滚后 dev 表集合不变，升级前哨兵数据重升后仍保留。
- 迁移测试不会自动使用普通 `CHAT_DATABASE_URL`；非本机、名称不以 `_migration_test` 结尾或非空库被拒绝。
- 同日 CLI 重跑成功；HTTP 最终读到 `collector_count=0, like_count=2`，已取消主题关注数为 0，
  汇总响应无 user_id、folder_ids、个人时间明细。
- 回滚本身会删除新增互动表的数据，只在隔离空库演练；真实环境应用迁移前仍需人工核对实际版本和备份。
  本轮没有验证真实部署库的迁移历史，也不声称已线上升级。

## 6. 遗留问题与边界

### P0：合入 dev 前必须解决

无本次范围内已知阻塞项；要求人工审查本地提交和接口兼容变化后再发起 PR。

### P1：建议后续优化

- 两处既有 Lint Hook 依赖警告，未进行无关聊天/Popover 修改。
- 快照生成通过整张运行表锁串行化，保证当前阶段一致性；若将来生成频率或数据量显著增长，再评估锁粒度与执行时间。
- 跨账号请求前置条件覆盖本轮互动与个人列表；账号注销的跨 worker 全局任务阻断仍沿用既有系统机制，
  本轮验证关系清理和之后的统计，不把该验证扩展为所有在途业务请求的全局取消保证。

### P2：可以暂时不做

- 论文 ID 按知识底座原始字符串计数，不擅自合并不同版本或来源；等待上游长期 ID 契约。
- 快照仅枚举有互动论文，主题覆盖启用目录；无互动论文由 missing IDs/0 语义表达。
- 真实科研服务在线联调、线上调度、部署、推荐算法、画像及请求幂等分支均不属于本阶段。

## 7. 合并判断

**可以合入 dev（待人工审查后提交 PR）**。

原实现已保留，已修复实际审查与链路验收发现的并发、快照、账号隔离、缓存同步和 401 转发问题。
本阶段所需单元、真实 PostgreSQL、迁移、前端、生产构建及本地浏览器/BFF 验收均通过；
没有引入推荐阶段或幂等分支，没有依赖或部署配置变更。所有提交仅在本地集成分支。

### 完整差异文件

相对上述 dev 基线（含本报告）：

```text
apps/backend/.env.example
apps/backend/app/api/collections.py
apps/backend/app/api/interactions.py
apps/backend/app/api/stats.py
apps/backend/app/core/identity.py
apps/backend/app/main.py
apps/backend/app/models/interactions.py
apps/backend/app/models/stats.py
apps/backend/app/schemas/collections.py
apps/backend/app/schemas/interactions.py
apps/backend/app/schemas/stats.py
apps/backend/app/services/library/collections.py
apps/backend/app/services/library/interactions.py
apps/backend/app/services/library/paper_likes.py
apps/backend/app/services/library/topic_follows.py
apps/backend/app/services/stats/__init__.py
apps/backend/app/services/stats/__main__.py
apps/backend/app/services/stats/service.py
apps/backend/app/services/stats/snapshot.py
apps/backend/app/services/user/account_deletion.py
apps/backend/migrations/env.py
apps/backend/migrations/versions/012_topic_follows.py
apps/backend/migrations/versions/013_paper_likes.py
apps/backend/migrations/versions/014_platform_snapshots.py
apps/backend/tests/test_account_deletion_persistence.py
apps/backend/tests/test_interaction_migrations.py
apps/backend/tests/test_interactions_api.py
apps/backend/tests/test_interactions_persistence.py
apps/backend/tests/test_library_api.py
apps/backend/tests/test_stats_api.py
apps/backend/tests/test_stats_snapshot.py
apps/web/clients/backend/forward.ts
apps/web/clients/backend/http.ts
apps/web/clients/backend/interactions.ts
apps/web/clients/knowledge/types.ts
apps/web/features/knowledge/interactions/cache.ts
apps/web/features/knowledge/interactions/components/paper-collector-count.tsx
apps/web/features/knowledge/interactions/components/paper-like-button.tsx
apps/web/features/knowledge/interactions/components/topic-follow-button.tsx
apps/web/features/knowledge/interactions/components/topic-follower-count.tsx
apps/web/features/knowledge/interactions/use-interaction-identity.ts
apps/web/features/knowledge/interactions/use-paper-interaction.ts
apps/web/features/knowledge/interactions/use-paper-like.ts
apps/web/features/knowledge/interactions/use-refresh-paper-interaction.ts
apps/web/features/knowledge/interactions/use-topic-follow.ts
apps/web/features/knowledge/interactions/use-topic-interaction.ts
apps/web/features/knowledge/papers/KnowledgePapersPage.tsx
apps/web/features/knowledge/papers/components/collection-picker.tsx
apps/web/features/knowledge/papers/components/library-panel.tsx
apps/web/features/knowledge/papers/components/library-table.tsx
apps/web/features/knowledge/papers/components/saved-interactions.tsx
apps/web/features/knowledge/search/components/result-card.tsx
apps/web/features/knowledge/topics/detail/topic-detail-page.tsx
apps/web/features/knowledge/topics/topic-card.tsx
apps/web/features/papers/[id]/PaperDetailPage.tsx
apps/web/features/search/components/paper-card.tsx
apps/web/providers/interaction-sync.tsx
apps/web/providers/query-provider.tsx
apps/web/stores/collections.ts
apps/web/stores/user-preferences.ts
apps/web/tests/chat/bff-body.test.ts
apps/web/tests/knowledge/interaction-cache.test.ts
apps/web/tests/knowledge/interactions.test.ts
docs/engineering/interactions-foundation-delivery.md
docs/knowledge/INTERACTIONS-AND-STATS.md
docs/knowledge/README.md
```
