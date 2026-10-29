# 请求幂等集成验收报告

验收日期：2026-10-30（Asia/Tokyo）。验收对象：本地 `integration/idempotency`。
结论：**具备合入 dev 的条件，等待人工审查**。本轮未 Push、未创建 PR、未合并 dev；
未操作生产数据库，未修改 Vercel 配置，未改动或合并推荐算法分支。

## 1. 集成方式

- 已执行 `git fetch origin`。基线 `origin/dev = 24e9233`，Feature `origin/feat/idempotency-v1 = 82067bc`
  （单个提交，基于旧 dev `4ef05d9`，落后互动基础层与会议截稿两次合入）。
- `git switch -c integration/idempotency origin/dev` 后执行 `merge --no-ff`，保留原始提交历史。
  唯一冲突在 `apps/web/clients/backend/forward.ts` 的转发头白名单：合并保留 dev 的
  `x-shenzhi-expected-user-id`，同时加入 Feature 的 `idempotency-key`。
- 本轮本地提交（相对基线领先 7、落后 0，含原始提交 `82067bc`）：

| 提交 | 内容 |
|---|---|
| `334c6a0` | merge: 集成请求幂等原始实现 |
| `8a398c8` | fix: 将请求幂等迁移接续至 014 并为推荐模块保留 015 |
| `e90810f` | fix: 修复多 Worker 下 Chat 停止确认、续接游标与待认领消息恢复 |
| `8d010c8` | fix: 租约心跳容忍瞬时故障并在关闭时释放 Agent 租约 |
| `430854d` | test: 适配幂等重试后的 Agent 运行请求断言 |
| `fb6bfc0` | fix: Agent 重试入口改用状态驱动显示 |
| 本报告 | docs: 补充请求幂等集成验收报告（最终哈希以 `git log` 为准） |

- `uv.lock`、`pnpm-lock.yaml` 均未修改；无新增依赖、无新增基础设施（继续只用 PostgreSQL）。

## 2. 完成能力

原 Feature 已有并保留：

- Chat 首轮创建、续问与 Agent 运行接受 `Idempotency-Key`（可见 ASCII，≤255）。Chat 按
  owner + 范围 + 键、Agent 按 Session + 键隔离；请求指纹为规范化请求体的 SHA-256。
  同键同请求复用原资源，同键不同请求返回 409。
- 键与业务资源在同一事务写入：Chat 首轮 Session 与 Message 原子创建；并发冲突由部分唯一索引兜底后回读原资源。
- Chat 生成由数据库条件更新认领（一个消息只有一个生成者）；Agent 轮次创建时绑定 Worker。
- 进程级 Worker ID + 5 分钟租约 + 30 秒心跳；恢复、续租、终态写入均以状态、Worker 和数据库时钟为条件，
  过期 Worker 不能覆盖恢复后的结果。启动不再无差别失败其他 Worker 的在途任务。
- Agent 同键重试在原进程复用 LiveRun；任务结束后从持久化 Turn 重建终态事件回放。
- Web 为每次发送生成操作键，失败重试复用；BFF 转发 `Idempotency-Key`；Agent 页面提供“重试上次提交”。

## 3. 修复内容

| 问题及原因 | 修改位置 | 修复与验证 |
|---|---|---|
| `012_request_idempotency` 以 `011` 为父，与 dev 的 `012~014` 互动迁移形成双 Head，`upgrade head` 失败 | `migrations/versions/016_request_idempotency.py` | 改为 `016`；推荐模块合入后父为 `015_recommendation_foundation`（见 §5）；单一 Head、`alembic check` 无差异 |
| 迁移给在途消息设置宽限租约，但新认领条件依赖 `lease IS NULL`，与下一项修复冲突 | 同上、`chat/postgres_repository.py` | 迁移把在途 `streaming` 行标记为遗留 Worker 已认领，并保留 10 分钟宽限；宽限期内新版本不会重复生成 |
| 只按租约恢复后，创建了但从未拉流的消息（`lease` 为 NULL）永远是 `streaming`，会话一直“请先停止当前生成” | `chat/postgres_repository.py` | 新建/续接消息带 5 分钟认领截止时间，到期按租约恢复为 failed；HTTP 验收 S7（修复前失败） |
| 停止请求落到非生成 Worker 时直接返回 409；实际上生成 Worker 会因 SSE 断开立即停止，前端却显示“停止请求未确认” | `chat/service.py` | 非所属 Worker 最多等 5 秒，所属 Worker 落库终态即确认成功，超时才 409；HTTP 验收 S4（修复前失败） |
| 非生成 Worker 缓存的消息对象在 `get()` 中覆盖数据库，远端已完成仍显示 streaming；被读取的终态消息还会一直留在缓存中 | 同上 | 只有本 Worker 有生成任务的对象参与覆盖；读取时以数据库刷新原对象，终态不再缓存 |
| 在 A 续接、在 B 拉流时 B 没有事件缓冲，游标大于 0 返回 400 | `api/chat.py` | 没有本地缓冲时游标从头重放：运行中由本 Worker 认领生成，已结束则重放持久化终态 |
| 心跳续租遇到一次瞬时数据库异常就取消正在生成的任务 | `core/worker_lease.py` | 租约到期前继续重试，无法保证在到期前续上时才放弃；新增单元测试 |
| 正常重启后 Agent 的 running Turn 要等满 5 分钟租约才能重新发送（旧版本启动即恢复） | `agent_sessions/postgres_repository.py` | 关闭时只释放本 Worker 的 Turn；HTTP 验收 S9（修复前失败） |
| 关闭/租约丢失统一提示为“任务执行租约已失效”，且可能连发两个 error 事件 | `chat/service.py` | 中断与租约失效分开提示，错误事件在落库结果确定后只发一次 |
| Agent 重试按钮在渲染期间读取 ref（Lint 错误 `react-hooks/refs`），显示状态不随数据更新 | `shenzhi-ai-page.tsx` | 用状态镜像待重试会话；Lint 0 错误 |
| 部分测试直接调用 `generate()`，跳过生产路径的认领；PostgreSQL 模式下终态写入被正确拒绝，导致 11 个测试失败 | 相关测试 | 改为先认领再生成；跨 Worker 的模拟改为真实写入数据库；保留原有断言 |

## 4. 测试结果

以下为最终代码实际结果。跳过项没有计为通过。

| 分类 | 通过 | 失败 | 跳过 | 说明 |
|---|---:|---:|---:|---|
| Backend 全量（无数据库） | 538 | 0 | 71 | 609 个用例；71 个需数据库或迁移库，已在下两行实际运行 |
| Backend PostgreSQL 幂等/持久化相关模块 | 78 | 0 | 0 | `test_persistence`、`Acceptance2a`、`test_chat_api`、`test_knowledge2chat_degradation`、`test_worker_lease` |
| PostgreSQL 迁移往返 | 3 | 0 | 0 | 合入推荐模块后：015↔016、014↔015 往返，以及 011→014 互动迁移回归，均使用独立空库 |
| 多 Worker HTTP 验收（两个 uvicorn 进程 + 同一 PostgreSQL） | 33 | 0 | 0 | 见下文；同一脚本在修复前的合并提交上为 28/33 |
| Frontend `pnpm test` | 454 | 0 | 0 | 另有 `typecheck` 通过；`lint` 0 错误，2 个既有警告 |

以 `CHAT_DATABASE_URL` 运行 Backend 全量 discover 时有 9 个错误，与相同方式运行的 `origin/dev` 完全一致，
不是本轮引入：8 个按 Memory 仓储编写的测试在设置数据库地址后失败（访问 Memory 专有属性，或跨事件循环复用连接池）；
`EnvironmentChecks.test_E01_E02_schema` 仍断言迁移版本为 `004_user_profiles`。

多 Worker HTTP 验收覆盖以下场景（模型和 Agent 运行时使用慢速假实现，租约缩短为 4 秒、心跳 1 秒；
其他均为真实的 FastAPI、Service、Repository 和 PostgreSQL）：

- 两个 Worker 并发 6 次同键创建：同一会话与消息，库中仅 1 个会话；不同请求体返回 409，非法键返回 422。
- 在另一 Worker 重复拉流：返回 409，不启动生成，模型只调用 1 次；完成后在另一 Worker 用旧游标读取得到完整终态重放。
- 同键并发续问只创建 1 条消息；跨 Worker 停止确认成功，并保留生成 Worker 的部分内容。
- 在 A 续接、在 B 拉流：成功完成，两个 Worker 合计只新增 1 次模型调用。
- SIGKILL 生成 Worker：租约有效期内状态仍为 streaming，新追问被拒绝；到期后恢复为 failed，可在存活 Worker 续接完成。
- 从未拉流的消息到期恢复为 failed，会话可以继续。
- Agent 两个 Worker 4 路同键并发：只有 1 个轮次、运行时只启动 1 次；本 Worker 复用流，其他 Worker 返回 409。
  完成后同键重试回放持久化结果；同键不同输入返回 409。
- Agent 正常关闭（SIGTERM）立即释放租约，可在其他 Worker 重新运行；崩溃（SIGKILL）在租约内拒绝新运行，
  到期后旧轮次为 `backend_restart`，新运行完成。

执行命令（工作目录 `apps/backend`、`apps/web`）：

```bash
CHAT_DATABASE_URL= uv run --locked --no-sync python -m unittest discover -s tests
CHAT_DATABASE_URL=postgresql://shenzhi_test@127.0.0.1:55473/shenzhi_idem_test uv run --locked --no-sync alembic upgrade head
CHAT_DATABASE_URL=postgresql://shenzhi_test@127.0.0.1:55473/shenzhi_idem_test uv run --locked --no-sync alembic check
CHAT_DATABASE_URL=postgresql://shenzhi_test@127.0.0.1:55473/shenzhi_idem_test uv run --locked --no-sync python -m unittest \
  tests.test_persistence tests.test_acceptance_2a.Acceptance2a tests.test_chat_api \
  tests.test_knowledge2chat_degradation tests.test_worker_lease
SHENZHI_MIGRATION_TEST_URL=postgresql://shenzhi_test@127.0.0.1:55473/shenzhi_idem_migration_test \
  uv run --locked --no-sync python -m unittest tests.test_idempotency_migrations   # 另一空库再跑 tests.test_interaction_migrations
pnpm test && pnpm typecheck && pnpm lint
```

隔离环境：在会话临时目录新建 PostgreSQL 16.15 集群，仅监听 `127.0.0.1:55473`，trust 认证，
关闭 Unix socket。本机 `55441` 端口已有其他 PostgreSQL 实例，本轮未连接或改动它。
多 Worker 验收脚本及日志保存在会话临时目录，没有提交。

未验证：真实模型和 Agent 工具调用、浏览器端到端（BFF→Backend 的转发只有单元测试覆盖）、
生产构建 `pnpm build`、Vercel Serverless 实例模型、共享或生产数据库迁移。

## 5. 数据库迁移

- 迁移链：`011_agent_uploads → 012_topic_follows → 013_paper_likes → 014_platform_snapshots → 015_recommendation_foundation → 016_request_idempotency`，
  唯一 Head 为 `016_request_idempotency`。原 `012_request_idempotency` 只存在于 Feature 分支，从未进入 dev，
  因此没有改动任何已合并的迁移。
- 016 内容：给 `chat_messages` 增加 7 列，给 `agent_turns` 增加 4 列，各建一个 `idempotency_key IS NOT NULL` 部分唯一索引；
  给在途行设置 10 分钟过渡租约。downgrade 删除这些列与索引，业务行保留（已由测试验证）。
- **与推荐模块 `015_recommendation_foundation` 的衔接**：推荐模块（PR #58）先合入 dev。016 此前未在任何共享库执行，
  因此直接把 016 的 `down_revision` 由 `014_platform_snapshots` 改为 `015_recommendation_foundation`，得到线性链；两者改动的表互不相交。
  单一 Head 校验由 `test_idempotency_migrations` 负责，互动与推荐迁移测试分别显式升级到 014、015。
  - 若将来需要合并已在共享环境执行过的平行迁移，应新增空的合并迁移而非改动已执行的 revision；
    revision ID 不能超过 32 个字符（`alembic_version.version_num` 为 `varchar(32)`），超长时 PostgreSQL 会在最后一步报错并回滚整个升级。
- 如果某个环境曾执行过 Feature 分支的 `012_request_idempotency`，其 `alembic_version` 不在新链中，需要人工核对后处理，
  不能直接 `upgrade`。本轮没有访问任何共享库，无法确认是否存在这种环境。

## 6. 遗留问题

### P0：合入 dev 前必须解决

无。仍需人工审查本地提交。

### P1：建议后续处理

- SSE 事件缓冲和 Agent LiveRun 仍在进程内：生成期间跨 Worker 不能加入实时流（返回 409）；
  Agent 的 steer/stop 按 run_id 只在本进程生效（dev 既有限制）。如需完整的多实例实时续传，需要另行设计共享事件通道。
- 跨 Worker 停止依赖浏览器断开 SSE，由所属 Worker 停止生成。如果同一消息还有其他标签页在订阅，停止请求会在 5 秒后返回 409，生成继续进行。
- 进程崩溃后，在途任务最长需要一个租约周期（5 分钟）才能恢复。这是以不误判其他 Worker 在途任务为代价的取舍。
- 租约到期恢复沿用既有错误文案 `backend restarted while generating`（英文），从未拉流的消息到期时也显示此文案。
- 滚动发布期间旧版本进程启动时仍会把全部 streaming 行标记为失败（旧代码行为），应尽快完成替换。
- `EnvironmentChecks.test_E01_E02_schema` 断言过时；8 个 Memory 测试在设置数据库地址时不能和全量 discover 一起运行。均为 dev 既有问题。

### P2：可以暂缓

- 幂等键没有过期清理，随业务行保留，删除会话时级联删除。
- 匿名会话被认领到登录账号后，旧匿名 owner 下的键不会迁移，重试会创建新资源。

## 7. 合并判断

**具备合入 dev 的条件（人工审查后再发起 PR）**。迁移已接到最新 dev 且只有一个 Head，并为推荐模块预留 015，
两种衔接方式都已实测；Chat 和 Agent 的重复请求、并发认领、租约恢复、跨 Worker 停止与续接、正常关闭释放，
均有 PostgreSQL 单元测试和多进程 HTTP 验收覆盖。前后端测试、类型检查和 Lint 无新增问题。
所有提交只在本地 `integration/idempotency`。
