# 搜索推荐第一阶段验收记录

> 从 [search-recommendation-implementation.md](../../../engineering/search-recommendation-implementation.md) 拆出的历史记录，只反映记录当时的状态；当前约定以原文档为准。

## 验证与限制

> 时间顺序说明：下方早期 2026-10-26 段落保留当时的环境状态和历史验证记录；其中“9 项跳过/数据库未复验”发生在隔离测试实例建成前，已由文末“最新数据库与端到端验收”的 34 项 PostgreSQL 通过证据更新。正文以文末最新节为当前状态；本轮修改后由于本地后端 pytest 不可用，34 项后端集成测试没有再次运行。

本地单元测试覆盖输入白名单、身份限制、时间衰减、特征缺失、推荐理由、部分召回失败、去重和多样性。独立临时 PostgreSQL 测试库已验证迁移、回滚、事件幂等、显式状态与事件一致性、画像重建、用户私有分页和全局保留期清理；维护命令已在该测试库运行。又以新建测试库验证搜索事件关联、仅搜索兴趣影响排序、不同兴趣并存、重复重建、用户隔离、并发上报限流及关键词召回匹配。后端推荐测试 18 项、搜索/发现/互动回归 56 项通过。前端类型检查与 lint 通过；修正与提交基线不符的收藏选择器旧断言后，前端完整测试 437 项全部通过，其中新增测试覆盖推荐数据映射、故障回退、匿名发现列表和搜索事件关联。

2026-10-26 本轮复核：推荐、互动 API、发现、阅读历史和知识搜索相关后端测试 **86 项通过、45 个子测试通过**；9 项 PostgreSQL 持久化用例因未设置 `CHAT_DATABASE_URL` 跳过（不是通过），其中新增并发详情访问、强弱信号刷新策略及旧事件清理后画像重建回归也在这 9 项中。推荐 API、服务、迁移和测试 Ruff 检查通过（FastAPI `Depends` 的通用 B008 规则单独忽略），Python 编译检查、Vercel 配置 JSON 解析及 `git diff --check` 通过。`015_recommendation_foundation` 的 Alembic offline SQL 生成成功；本轮未对 PostgreSQL 实际执行迁移。Vercel Cron 的密钥校验由 API 测试覆盖，线上 Cron 注册和数据库清理未在生产环境执行或验证。前端 `tsc --noEmit`、相关 ESLint、完整测试均通过；新增累计阅读计时测试后完整测试为 440 项通过。

2026-10-26 数据库集成复验：重新检查仓库测试约定和本机数据库。`apps/backend/.env` 的 `CHAT_DATABASE_URL` 指向 `127.0.0.1:5432/shenzhi_chat` 开发库；该实例正在运行并有本机客户端连接。生产 `infra/compose/docker-compose.yml` 不含 PostgreSQL，Docker Engine 未启动，且本机 PostgreSQL 发行版目录无可用客户端工具。因此没有把开发库 URL 注入测试进程、没有在其上运行迁移、没有修改 `.env`，也没有伪报数据库测试通过；需要在隔离 PostgreSQL 实例中创建专用 `shenzhi_recommendation_test` 数据库后再验证。可用无凭据示例 `postgresql://<test-user>:<test-password>@127.0.0.1:<test-port>/shenzhi_recommendation_test` 设置进程级 `CHAT_DATABASE_URL`，先确认数据库名和端口确属测试实例，再从 `apps/backend` 使用现有 `.venv/Scripts/python.exe -m alembic -c alembic.ini upgrade head` 执行迁移，并用同一进程级环境配置启动测试；不要使用会加载开发库 URL 的 `.env`，也不要将测试 URL 写入开发 `.env`。本轮尝试的 `uv run --locked` 因现有锁文件需要更新而在启动前失败；遵守 `uv.lock` 不变要求，改用已有 `.venv` Python 跑相关测试。数据库未配置时重新运行的推荐/阅读历史/互动/发现/知识相关模块为 **95 项通过、9 项跳过**；9 项均在 `CHAT_DATABASE_URL` 条件下才执行，包含并发阅读去重、事件持久化与幂等、跨用户快照/画像隔离、画像刷新及 retention。Python `compileall` 与 `git diff --check` 通过；此环境 `.venv` 没有 Ruff 模块，故本轮 Ruff 未运行（此前记录的 Ruff 结果不是本轮复验）。

本轮静态行为复核确认：阅读历史的 `pg_advisory_xact_lock(hashtext('reading-history:<user>'), hashtext('<paper>'))` 在单个 `session_scope` 事务内先于读取十分钟窗口并写关系/事件；事务锁在提交、回滚或连接关闭时由 PostgreSQL 释放，散列键按用户与论文分区（理论上 `hashtext` 冲突可能造成额外串行，不会破坏正确性）。真实 PostgreSQL 并发行为和 600 秒边界仍待隔离库验收。画像刷新触发集合含收藏/点赞/关注及撤销、已读、有效阅读和搜索提交；权重另由 `EVENT_WEIGHTS` 控制：搜索提交为 0.2，仅进入短期关键词、3 天半衰期；有效阅读 1.5、14 天半衰期；显式状态来自关系表，撤销后重建不保留其贡献。同论文弱事件按天取最高权重，避免点击与详情重复放大。推荐首页通过 `fetchHomeFeedPage` 调个性化 API，失败或首屏空结果回退全局发现；分页 cursor 继续读用户私有快照。API/前端映射与故障回退有自动化覆盖，但首次/下一页快照、数据库事件触发后新首页更新及用户隔离的持久化链路本轮都未能连数据库实测。主动搜索仍走独立 Knowledge API。

本轮前端审查修复了有效阅读计时的边界：之前按 5 秒 interval 固定加时，切换到后台发生在两次 tick 之间时会多计最多 5 秒。现改用 `performance.now()` 实测前台间隔，在 `visibilitychange` 和 effect 清理时重置间隔基准，同时保留累计值；达到 30 秒才尝试提交一次。同一 tracker 在相同用户/论文身份跨面板 effect 重挂时保留已累计时间，切换身份会重置；上报函数仍为异步幂等事件，网络失败不重试或重复计权。单测覆盖前后台间隔、面板中断后的累计、门槛和身份切换。

本轮完整前端测试 **440/440 通过**，`pnpm exec tsc --noEmit` 和相关文件 ESLint 通过。后端推荐/阅读历史/互动/发现/知识模块 **95 项通过、9 项数据库测试跳过**；Python 编译和 `git diff --check` 通过。数据库测试跳过原因是隔离库不可用（开发 `.env` 指向正在使用的 `shenzhi_chat`，Docker 不可用）；本轮未迁移、未运行真实 PostgreSQL 并发及首页登录浏览器手动验收。Ruff 未能运行，因为现有 `.venv` 不含 Ruff 模块；`uv run --locked` 因检测到 lockfile 需更新而在运行命令前退出，本轮未改 `uv.lock`。未运行生产构建、线上调度或第三方知识底座实时集成。以上区分自动化通过、未验证及环境阻碍；数据库验收完成前不进入算法增强。

后端仍通过 `require_user` 获取身份；事件 `event_id` 主键冲突忽略提供重试幂等，推荐反馈验证快照所有者/论文/排名。搜索 `query_id` 归因限定 `(user_id, query_id)` 匹配，评估只输出计数；原始搜索词仍按设计存储于 `search_submit.entity_id`，故数据库访问、保留与账号删除权限仍属于隐私边界，不能声称完全不持久化搜索历史。

本地浏览器在 `http://localhost:3000` 使用 5433 独立数据库和一次性测试账号完成真实链路验收：匿名首页正常显示全局发现；登录后首次推荐因空论文历史触发 `asyncio.wait` 错误，页面按设计回退全局发现。修复空列表边界并补回归测试后，登录首页显示推荐理由；测试库生成推荐快照，并写入 `recommendation_impression`。点击推荐论文成功进入详情，写入 `recommendation_click` 和详情浏览事件。第二次验收中，关键词搜索与结果点击通过相同 `query_id` 关联，PDF 阅读器加载后页面可见累计 30 秒产生 `active_read` 事件。仅有搜索历史时的首页还暴露出关键词标签缺失导致检索结果未得到匹配分的问题；加入有界的关键词召回证据后，重启 Backend 并刷新页面，首页首条显示相关论文及“与你近期搜索的方向相关”理由。

`uv run --frozen python -m app.services.recommendation.evaluation` 对最近七天推荐曝光/点击和搜索提交/结果点击输出匿名聚合计数，包括重复推荐事件、未关联曝光的推荐点击、点击率，以及搜索结果点击与同一用户搜索提交的 query_id 关联情况；不输出查询内容、用户 ID 或论文 ID。直接打开搜索结果可能没有 query_id，因此单独计数而不判为错误；携带 query_id 但找不到同用户提交事件的点击会作为未匹配计数。样本超过 10 万条时明确标记为不完整。传入 `--judgments <json文件> --k 5 10` 可对同一批候选的多种排序计算宏平均 Recall@K 与 NDCG@K。输入格式为 `{"cases":[{"relevant_ids":["paper:1"],"rankings":{"global_discovery":["paper:1","paper:2"],"explicit_topic":["paper:2","paper:1"],"content_v1":["paper:1","paper:2"]}}]}`；工具拒绝候选集合不一致、重复 ID 或标签引用集合外论文。当前尚无人评标注集，因此该命令是可复现的评估入口，尚无真实基线结果；不能据点击率推断离线相关性，也不能声称个性化效果优于基线。

需要知识底座团队确认：论文元数据字段覆盖率及缓存许可、主题名称与 `subjectQuery` 的匹配规则、接口限流和可用性、搜索结果 ID 的稳定性，以及检索结果的主题/关键词质量。当前发现快照是有限静态集合，不代表完整论文库。发现 Feed 和知识搜索结果的长摘要现在提供显式展开控件，首次展开写入 `abstract_expand`；同一组件会避免重复发送该事件。尚未实现实验指标看板和真实人工标注集。

对仓库内打包的 300 篇发现快照做只读字段统计：标题、摘要、作者、venue、年份均有值 300/300；subjects、keywords 均为 0/300。它是静态发现候选集，不代表知识底座真实覆盖率。当前 PaperDetail/搜索 Schema 中作者为字符串列表，没有稳定作者 ID；作者偏好和 venue 偏好尚未加入画像或排序。需要先从获准的 Knowledge API 样本统计真实字段覆盖，并用标注数据验证价值，再决定是否新增特征与升级算法版本。

（历史记录，集成时已撤销：本轮未修改 `vercel.json`，未注册 Cron。）原分支曾将维护任务配置在 `apps/backend/vercel.json`，每天 UTC 17:18 调用 `/api/v1/internal/recommendation-maintenance`（上海时间次日 01:18）。该路由要求 Vercel 环境变量 `CRON_SECRET`，只接受匹配的 `Authorization: Bearer ...` 请求；成功响应包含本次清理计数。清理是可重复执行的删除操作，适合 Vercel Cron 至少一次/可能漏发的投递语义。部署后仍需在 Vercel Cron Jobs 和函数日志中确认生产调度已激活；本地代码和配置检查不代表线上已运行。手动执行仍可用 `cd apps/backend && uv run --frozen python -m app.services.recommendation.maintenance`。

## 2026-10-26 最新数据库与端到端验收

### PostgreSQL 集成验收证据

此前本地隔离数据库复验已经完成迁移 `001`–`015`（Alembic `upgrade head`），并运行推荐与阅读历史数据库集成组 **34/34 通过**：`test_recommendation.py` **27/27**、`test_reading_history.py` **7/7**。覆盖事件写入与幂等、画像刷新/重建、推荐快照及用户私有访问、详情阅读十分钟去重与并发锁等持久化路径。这是 PostgreSQL 集成通过证据，不应再沿用本文较早的“9 项跳过、数据库待复验”作为当前项目状态。

专用实例为临时 PostgreSQL **16.15** 集群，数据目录位于 `%TEMP%\shenzhi_recommendation_test_pg\data`，只监听 loopback `127.0.0.1:55433`。连接预检返回 `current_database=shenzhi_recommendation_test`、`current_user=postgres`、`inet_server_addr=127.0.0.1`、`inet_server_port=55433`；实例的 `pg_hba.conf` 仅允许 `postgres` 从 `127.0.0.1/32` 连接这个测试数据库。其 Alembic 版本为 `015_recommendation_foundation`。开发实例 `127.0.0.1:5432/shenzhi_chat` 未执行迁移或测试，本次也未访问生产数据库。Better Auth 的测试表 `001_better_auth.sql`、`002_turnstile_verification.sql` 只安装在同一隔离库；登录使用合成账号，没有注册、发送邮件或触发真实 DirectMail。

本轮重新执行数据库测试时发现当前 `apps/backend/.venv` 和全局 Python 环境都没有可用的 `pytest` 模块；历史可见的 `pytest.exe` 是无对应 Python 解释器的残留启动器。`uv run --locked python -m pytest --version` 在测试启动前退出，原文为 `The lockfile at uv.lock needs to be updated, but --locked was provided`。遵守不执行 `uv lock` 的要求，`apps/backend/uv.lock` 未改；因此上面 34 项是最近一次已完成的隔离数据库验收结果，本轮代码改动后未能重新运行后端 34 项。前端回归已另行完整复跑。

### 登录首页及埋点 E2E

浏览器打开 `http://localhost:3000`。Next.js 的 Better Auth、Web BFF 与 FastAPI Backend 使用临时进程级配置，数据库均指向 `127.0.0.1:55433/shenzhi_recommendation_test`；BFF 密钥为仅供本地进程使用的测试值。主动搜索走前端 mock Knowledge 数据；论文详情/PDF 的 Backend Knowledge 上游由 `127.0.0.1:8100` 的临时确定性测试桩提供，PDF 流本身通过 Backend 资源路由从公开 arXiv 获取。因此这条链路验证了应用行为与数据库埋点，不代表生产 Knowledge Base 的可用性或元数据质量。

使用隔离库中预置的已验证合成账号完成正常密码登录。登录首页调用 `/api/v1/recommendations/papers`，创建 `content-v1` 私有快照，快照共 **48** 个候选；页面首屏 **12** 项，滚动触发游标请求后增加至 **24** 项。测试库记录了推荐 impression 与 click；两者的 `request_id`、论文和 `rank` 完全匹配。实际观测到 4 条曝光及 1 条推荐点击。先前测试中空画像产生的冷启动响应能正常退回全局发现；有搜索/阅读历史后，Feed 首条显示兴趣相关论文和个性化理由。

主动搜索提交产生 1 条 `search_submit`。点击结果写入 2 条 `search_result_click`：1 条携带并匹配同一用户的非空 `query_id`；另 1 条来自直接打开带查询参数的结果 URL，没有 `query_id`，符合现有“直达链接可无归因 ID”的边界，没有携带无效 ID。

PDF 阅读器通过本地 Knowledge 测试桩解析详情、从 `paper-resource` 流式加载并渲染真实 PDF。浏览器 `document.visibilityState` 为 `visible`，渲染画布存在，前台停留约 35 秒后测试库收到 1 条 `active_read`，`duration_seconds=30`。首次尝试返回 HTTP 422：浏览器计时产生了小数秒，而后端 schema 只接受整数。已在 [behavior.ts](../../../../apps/web/clients/backend/behavior.ts) 上报边界对有效阅读秒数向下取整，并在 `recommendation-feed.test.ts` 加入小数秒序列化回归；修复后前台 PDF E2E 成功。前端完整测试 **441/441 通过**，包含该新增回归。

测试过程中还发现，静态发现快照中的一篇论文 ID 不存在于 Next mock 详情数据，直接打开其详情得到“未找到”；这是全局快照与 mock 数据集不重叠造成的测试夹具限制。后续 PDF 计时使用知识搜索可解析的 mock 论文验证，没有把该失败伪装为通过。生产 Knowledge 底座中相同 ID 的详情可达性仍需真实环境验收。

### 离线质量评估初版

新增 [robot-visuomotor-v0.json](../../../../apps/backend/evaluation/recommendation-judgments/robot-visuomotor-v0.json) 和配套指标/方法说明，比较 `global_discovery`、`explicit_topic` 与 `content-v1`。目前为 **1 个 query、13 个 pooled candidate、6 个二元相关项**；三种排序都覆盖相同候选集，判定基于标题与摘要，不使用点击率代替相关性。用 `python -m app.services.recommendation.evaluation --judgments evaluation/recommendation-judgments/robot-visuomotor-v0.json --k 3 5 10` 可离线复算。

初标结果：`global_discovery` Recall@3/@5/@10 为 `0 / 0 / 0.833333`，NDCG@3/@5/@10 为 `0 / 0 / 0.482681`；`explicit_topic` 与 `content-v1` 的 Recall@3/@5/@10 都为 `0.5 / 0.833333 / 1.0`，NDCG 均为 `1.0 / 1.0 / 1.0`。该样本只有一个场景，且主题召回与 content-v1 的候选来自本地测试桩和 mock 论文库。标签由 Codex 单人初判、尚未真人领域复核；这些数字仅验证评估入口与候选对齐，不能作为算法效果结论或调整权重的依据。下一步应扩大到多主题、多查询，提供标题/摘要的盲评候选池，并由至少一名领域人员复核、保留分歧后再建立可用于决策的人工相关性基线。
