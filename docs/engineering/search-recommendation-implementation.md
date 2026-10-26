# 搜索推荐第一阶段实现

## 边界与模块

论文主动搜索仍走原有 Knowledge API、Service 和 Adapter。推荐由独立的 `/api/v1/recommendations` 路由提供，不向主动搜索注入画像，也不改变其查询、过滤、原始排序和分页。身份沿用 Better Auth → Web BFF → `require_user`，请求体不接受用户 ID。

Backend 中 `BehaviorEventService` 负责事件校验后的幂等写入；`PaperFeatureService` 通过现有 Knowledge Service 有界获取论文详情；`UserProfileService` 从当前关系状态和近 90 天隐式事件重建画像；`CandidateRecallService` 调用现有主题检索、增强检索及发现快照；`RecommendationService` 排序、过滤并保存一小时的分页快照。Web 的首页 Feed 对登录用户请求推荐，接口失败时使用现有全局发现候选。

## 事件与数据库

迁移 `015_recommendation_foundation` 在 `014_platform_snapshots` 后增加：

- `behavior_events`：UUID 事件 ID、可信用户 ID、事件类型、对象类型和 ID、来源、推荐请求 ID、搜索 `query_id`、位置、有效阅读秒数、Schema 版本、服务端发生和接收时间。主键保证重试幂等；按用户和时间、用户和对象建立索引。
- `user_interest_profiles`：每用户一行，存算法版本、画像版本、计算时间、最新事件时间及 JSONB 特征。
- `recommendation_snapshots`：按请求 ID 保存用户拥有的有序候选及一小时过期时间，使后续页读取同一排序结果。

升级使用现有 Alembic 命令 `uv run --frozen alembic upgrade head`；回滚该迁移使用 `uv run --frozen alembic downgrade 014_platform_snapshots`。这两个命令需要专用测试数据库或明确授权的部署环境；本次仅在本机 5433 的独立临时测试库运行迁移，没有对真实用户数据库执行迁移。

服务端点赞、取消点赞、关注、取消关注和收藏状态改变时，在原事务内追加事件。收藏按用户与论文去重：加入第二个文件夹和同用户文件夹间移动不新增收藏兴趣；移除最后一个文件夹才记撤销。标记已读及详情访问沿用原阅读历史接口，详情访问十分钟内重复记录不重复产生兴趣事件。浏览器仅能批量提交受白名单约束的隐式事件，每批最多 20 条、每用户每分钟最多 120 条；该用户的并发批次在 PostgreSQL 事务锁内计数，UUID 幂等，字段长度及阅读秒数有限制。关键词搜索提交使用事件 ID 作为 `query_id`，当前页面的搜索结果点击沿用它；直接打开搜索结果 URL 时点击可以没有关联 ID。曝光需卡片至少一半可见并持续一秒；PDF 有效阅读需可见页面累计 30 秒。曝光不作为负反馈。事件上报失败不会阻塞页面跳转。搜索查询作为短期兴趣信号存储，不写普通请求日志。每次该用户上报时会清理其 90 天前事件；独立维护命令 `cd apps/backend && uv run --frozen python -m app.services.recommendation.maintenance` 全局清理 90 天前事件与已过期分页快照，需要由部署环境定期调度。账号删除会同时清理事件、画像及推荐快照。

## 画像与内容特征

`content-v1` 初始权重：收藏 4、点赞 2、主题关注 3、有效阅读 1.5、标记已读 1、摘要主动展开 0.8、详情访问 0.5、卡片点击 0.3、搜索提交 0.2。本文参数为基线，未经真实用户实验验证。指数衰减为 `2 ** (-age_days / half_life_days)`：收藏 90 天、点赞 45 天、阅读及摘要 14 天、点击和详情 7 天；显式主题关注直到取消前不衰减。长期、近 14 天短期主题和关键词分别归一化，再以 `0.6 * long + 0.4 * short` 融合。相同论文同一天的多个弱行为只采用最高权重一次；收藏表按论文去重。撤销显式行为直接移除当前关系贡献，重建不会向主题施加负分。

论文 `subjects`、`keywords` 来自知识底座详情；Topic Catalog 的 `subjectQuery` 是显式关注主题的召回词。缺失元数据时保留行为事实，但不推造主题或关键词。单次画像最多处理 40 篇不同论文，元数据经现有详情缓存，有界并发且单篇超时四秒。画像在事件变化或十分钟后重建并保存版本。只有搜索提交的用户也视为有短期兴趣，按兴趣匹配排序。`GET /api/v1/recommendations/me/profile` 仅返回当前用户聚合的主题与关键词分数，不返回他人数据。

## 召回、排序与分页

每次推荐最多调用四个知识底座查询，每路最多 12 篇：显式关注主题、推断主题和高分关键词；并合并现有全局发现快照中的 48 篇。知识底座某路失败仍用其他来源，全部失败时保留全局候选。论文 ID 作为不透明字符串去重。已点赞或收藏的论文默认过滤。

排序有效特征权重：主题 0.40、关键词 0.25、显式关注 0.20、已发布平台热度 0.10、论文年份时效 0.05；缺失特征不参与分母。关键词检索命中可作为该次兴趣查询的证据，即使知识底座没有返回完全相同的关键词标签；该信号按上游结果位置有界衰减，并使用“与你近期搜索的方向相关”理由。没有个人匹配的候选分数封顶为 0.15，避免仅凭时效超过相关论文。冷启动直接保留现有每日发现顺序。主题多样性只在替代候选分数至少达到当前候选的 80% 时调整，避免引入明显不相关论文。推荐理由由实际匹配特征决定，不暴露行为明细。分数是排序信号，不是喜欢概率。

`GET /api/v1/recommendations/papers?limit=12&cursor=...` 返回论文基础信息、理由、来源、位置、请求 ID、下一页游标、总数和算法版本。首次请求保存一小时用户私有快照；游标请求验证拥有者与过期时间。`POST /api/v1/behavior-events/batch` 只接受登录用户受控事件；推荐曝光和点击携带推荐请求 ID 与位置。前端 Feed 的查询缓存按当前用户 ID 隔离，匿名用户继续使用全局发现列表。

三个接口都使用现有 BFF 身份，响应由现有 `{code, data}` 封装：

| 接口 | 输入 | `data` 核心字段 |
| --- | --- | --- |
| `GET /api/v1/recommendations/papers` | `limit` 1–48，`cursor` 可选 | `items`（每篇含 `id/title/abstract/authors/year/venue/reason/sources/request_id/rank`）、`next_cursor`、`has_more`、`request_id`、`total`、`algorithm_version` |
| `GET /api/v1/recommendations/me/profile` | 无 | `long_topics`、`short_topics`、`long_keywords`、`short_keywords`、`explicit_subjects`、`has_history`、`computed_at`、`algorithm_version` |
| `POST /api/v1/behavior-events/batch` | `{events:[...]}`，每批 1–20 条；事件含 UUID `event_id`、类型、来源和对象，推荐事件另含 `request_id/rank`，搜索事件可含 UUID `query_id` | `inserted`（幂等后实际新增条数） |

前端采集失败会被吞掉，不影响原跳转；后端非法字段返回 422、非本人推荐反馈返回 400、未登录返回 401、超出每分钟限额返回 429。推荐召回单路知识底座异常保留其他来源和全局发现，整个推荐接口异常时 Web Feed 回退原发现 API。主动搜索继续调用原 Knowledge 路由，推荐画像不进入搜索请求参数或排序。

## 验证与限制

本地单元测试覆盖输入白名单、身份限制、时间衰减、特征缺失、推荐理由、部分召回失败、去重和多样性。独立临时 PostgreSQL 测试库已验证迁移、回滚、事件幂等、显式状态与事件一致性、画像重建、用户私有分页和全局保留期清理；维护命令已在该测试库运行。又以新建测试库验证搜索事件关联、仅搜索兴趣影响排序、不同兴趣并存、重复重建、用户隔离、并发上报限流及关键词召回匹配。后端推荐测试 18 项、搜索/发现/互动回归 56 项通过。前端类型检查与 lint 通过；修正与提交基线不符的收藏选择器旧断言后，前端完整测试 437 项全部通过，其中新增测试覆盖推荐数据映射、故障回退、匿名发现列表和搜索事件关联。

2026-10-26 本轮复核：推荐、互动 API、发现、阅读历史和知识搜索相关后端测试合计 82 项通过、45 个子测试通过；6 项 PostgreSQL 持久化用例因未设置 `CHAT_DATABASE_URL` 跳过（不是通过）。推荐 API、服务、迁移和测试 Ruff 检查通过（FastAPI `Depends` 的通用 B008 规则单独忽略），Python 编译检查、Vercel 配置 JSON 解析及 `git diff --check` 通过。`015_recommendation_foundation` 的 Alembic offline SQL 生成成功；本轮未对 PostgreSQL 实际执行迁移。Vercel Cron 的密钥校验由 API 测试覆盖，线上 Cron 注册和数据库清理未在生产环境执行或验证。前端 `tsc --noEmit`、相关 ESLint、完整测试均通过；完整测试为 438 项通过。

本地浏览器在 `http://localhost:3000` 使用 5433 独立数据库和一次性测试账号完成真实链路验收：匿名首页正常显示全局发现；登录后首次推荐因空论文历史触发 `asyncio.wait` 错误，页面按设计回退全局发现。修复空列表边界并补回归测试后，登录首页显示推荐理由；测试库生成推荐快照，并写入 `recommendation_impression`。点击推荐论文成功进入详情，写入 `recommendation_click` 和详情浏览事件。第二次验收中，关键词搜索与结果点击通过相同 `query_id` 关联，PDF 阅读器加载后页面可见累计 30 秒产生 `active_read` 事件。仅有搜索历史时的首页还暴露出关键词标签缺失导致检索结果未得到匹配分的问题；加入有界的关键词召回证据后，重启 Backend 并刷新页面，首页首条显示相关论文及“与你近期搜索的方向相关”理由。

`uv run --frozen python -m app.services.recommendation.evaluation` 对最近七天推荐曝光与点击输出聚合计数、重复事件、未关联曝光的点击和点击率，不输出用户 ID 或论文 ID；样本超过 10 万条时明确标记为不完整。传入 `--judgments <json文件> --k 5 10` 可对同一批候选的多种排序计算宏平均 Recall@K 与 NDCG@K。输入格式为 `{"cases":[{"relevant_ids":["paper:1"],"rankings":{"global_discovery":["paper:1","paper:2"],"explicit_topic":["paper:2","paper:1"],"content_v1":["paper:1","paper:2"]}}]}`；工具拒绝候选集合不一致、重复 ID 或标签引用集合外论文。当前尚无人评标注集，因此该命令是可复现的评估入口，尚无真实基线结果；不能据点击率推断离线相关性，也不能声称个性化效果优于基线。

需要知识底座团队确认：论文元数据字段覆盖率及缓存许可、主题名称与 `subjectQuery` 的匹配规则、接口限流和可用性、搜索结果 ID 的稳定性，以及检索结果的主题/关键词质量。当前发现快照是有限静态集合，不代表完整论文库。发现 Feed 和知识搜索结果的长摘要现在提供显式展开控件，首次展开写入 `abstract_expand`；同一组件会避免重复发送该事件。尚未实现实验指标看板和真实人工标注集。

维护任务已配置在 `apps/backend/vercel.json`，每天 UTC 17:18 调用 `/api/v1/internal/recommendation-maintenance`（上海时间次日 01:18）。该路由要求 Vercel 环境变量 `CRON_SECRET`，只接受匹配的 `Authorization: Bearer ...` 请求；成功响应包含本次清理计数。清理是可重复执行的删除操作，适合 Vercel Cron 至少一次/可能漏发的投递语义。部署后仍需在 Vercel Cron Jobs 和函数日志中确认生产调度已激活；本地代码和配置检查不代表线上已运行。手动执行仍可用 `cd apps/backend && uv run --frozen python -m app.services.recommendation.maintenance`。

## Embedding 后续评估

本地 `fastembed` 项目是 Apache-2.0 许可的 ONNX 推理库，`pgvector` 是 PostgreSQL 向量扩展。第一阶段不复制源码、不安装模型、不加数据库扩展，也不依赖第三方 Embedding API Key。后续用真实论文语言分布、标题/摘要覆盖率与 CPU/内存基准选择小模型，在离线任务批量生成向量，并以内容规则基线对照离线相关性和在线点击指标，再决定是否将向量召回接入现有推荐 Service；主动搜索保持独立。
