# 搜索推荐第一阶段实现

> 本文是搜索推荐的现行实现说明，随代码维护。集成交付报告是历史记录，见 [`search-recommendation-delivery.md`](../dev/records/engineering/search-recommendation-delivery.md)；其中的时点描述不代表当前状态。

## 边界与模块

论文主动搜索仍走原有 Knowledge API、Service 和 Adapter。推荐由独立的 `/api/v1/recommendations` 路由提供，不向主动搜索注入画像，也不改变其查询、过滤、原始排序和分页。身份沿用 Better Auth → Web BFF → `require_user`，请求体不接受用户 ID。

Backend 中 `BehaviorEventService` 负责事件校验后的幂等写入；`PaperFeatureService` 通过现有 Knowledge Service 有界获取论文详情；`UserProfileService` 从当前关系状态和近 90 天隐式事件重建画像；`CandidateRecallService` 只召回个人候选（调用现有主题检索与增强检索），共享数据源（`daily` / `trending` / `fallback`）由 `app/services/home_feed` 提供；`RecommendationService` 排序、过滤，与共享数据源组装后保存一小时的分页快照。Web 的首页 Feed 对登录用户请求推荐；只有第一页失败或为空时整份列表降级为现有全局发现，推荐分页开始后的失败保留已加载内容并重试同一游标，快照过期（409）时提示刷新并从第一页重建。匿名发现列表在浏览中途被替换（例如当天候选在 0:05 生成）时同样返回 `20001/409`，前端统一抛 `HomeFeedExpiredError`，提示“论文列表已更新”并从第一页重建；游标格式错误仍为 400。

## 事件与数据库

迁移 `015_recommendation_foundation` 在 `014_platform_snapshots` 后增加：

- `behavior_events`：UUID 事件 ID、可信用户 ID、事件类型、对象类型和 ID、来源、推荐请求 ID、搜索 `query_id`、位置、有效阅读秒数、Schema 版本、服务端发生和接收时间。主键保证重试幂等；按用户和时间、用户和对象建立索引。
- `user_interest_profiles`：每用户一行，存算法版本、画像版本、计算时间、最新事件时间及 JSONB 特征。
- `recommendation_snapshots`：按请求 ID 保存用户拥有的有序候选及一小时过期时间，使后续页读取同一排序结果。

升级使用现有 Alembic 命令 `uv run --frozen alembic upgrade head`；回滚该迁移使用 `uv run --frozen alembic downgrade 014_platform_snapshots`。这两个命令需要专用测试数据库或明确授权的部署环境。

服务端点赞、取消点赞、关注、取消关注和收藏状态改变时，在原事务内追加事件。收藏按用户与论文去重：加入第二个文件夹和同用户文件夹间移动不新增收藏兴趣；移除最后一个文件夹才记撤销。标记已读及详情访问沿用原阅读历史接口；详情访问的十分钟去重检查在用户/论文级 PostgreSQL 事务锁内执行，避免并发请求重复写入。浏览器仅能批量提交受白名单约束的隐式事件，每批最多 20 条、每用户每分钟最多 120 条；该用户的并发批次在 PostgreSQL 事务锁内计数，UUID 幂等，字段长度及阅读秒数有限制。关键词搜索提交使用事件 ID 作为 `query_id`，当前页面的搜索结果点击沿用它；直接打开搜索结果 URL 时点击可以没有关联 ID。曝光需卡片至少一半可见并持续一秒；PDF 有效阅读按前台可见时间累计 30 秒，切换阅读/助手面板不会清零。曝光不作为负反馈。事件上报失败不会阻塞页面跳转。搜索查询作为短期兴趣信号存储，不写普通请求日志。每次该用户上报时会清理其 90 天前事件；独立维护命令 `cd apps/backend && uv run --frozen python -m app.services.recommendation.maintenance` 全局清理 90 天前事件与已过期分页快照；开启 `HOME_FEED_SCHEDULER_ENABLED` 后由 API 进程内调度器每小时自动执行。账号删除会同时清理事件、画像及推荐快照。

## 画像与内容特征

`content-v1` 初始权重：收藏 4、点赞 2、主题关注 3、有效阅读 1.5、标记已读 1、摘要主动展开 0.8、详情访问 0.5、卡片点击 0.3、搜索提交 0.2。本文参数为基线，未经真实用户实验验证。指数衰减为 `2 ** (-age_days / half_life_days)`：收藏 90 天、点赞 45 天、阅读及摘要 14 天、点击和详情 7 天；显式主题关注直到取消前不衰减。长期、近 14 天短期主题和关键词分别归一化，再以 `0.6 * long + 0.4 * short` 融合。相同论文同一天的多个弱行为只采用最高权重一次；收藏表按论文去重。撤销显式行为直接移除当前关系贡献，重建不会向主题施加负分。

点赞、收藏和主题关注的长期状态来自现有关系表；画像重建不依赖 90 天保留期内的显式事件。因此删除旧事件不会删除仍有效的关系信号。数据库回归用例覆盖“旧点赞事件被清理后仍能从有效点赞关系重建兴趣”；当前环境缺少 `CHAT_DATABASE_URL` 时该集成用例会跳过。

论文 `subjects`、`keywords` 来自知识底座详情；Topic Catalog 的 `subjectQuery` 是显式关注主题的召回词。缺失元数据时保留行为事实，但不推造主题或关键词。单次画像最多处理 40 篇不同论文，元数据经现有详情缓存，有界并发且单篇超时四秒。点赞/收藏/关注及撤销、已读、有效阅读和搜索意图等强信号会立即使画像缓存失效；卡片点击、详情访问、摘要展开等弱信号在下次十分钟 TTL 重建时一并吸收，曝光不使画像重建。画像行中的 `last_event_at` 用于比较最近强信号时间。只有搜索提交的用户也视为有短期兴趣，按兴趣匹配排序。`GET /api/v1/recommendations/me/profile` 仅返回当前用户聚合的主题与关键词分数，不返回他人数据。

## 召回、排序与分页

个人召回每次最多调用四个知识底座查询，每路最多 12 篇：显式关注主题、推断主题和高分关键词。知识底座某路失败仍用其他来源。论文 ID 作为不透明字符串去重。已点赞或收藏的论文默认过滤。召回论文与其他首页数据源一样，要通过统一的准入检查（`app/services/home_feed/rules.py`）：必须带有 Web 图片代理能展示的知识库 `image_id`（png/jpg/webp，SVG 视为无图），标题、摘要、作者能正常展示，否则不进入列表。知识底座的图片几乎只覆盖首页所展示的年份（当前 2026），因此召回限定该年份（取当天共享数据源中最常见的年份）：关键词检索传 `yearFrom/yearTo`；主题检索不支持年份过滤，改为多取 3 倍后本地按年份筛选，每路仍至多 12 篇。对真实底座的抽样中，不限年份时关键词检索 12 篇中仅 1–2 篇有图，限定年份后为 11–12 篇。

登录 Feed 中，个人推荐作为 `personal` 数据源（排序与多样性处理后最多 100 篇），与匿名首页相同的 `daily`、`trending` 数据源一起交给 `app/services/home_feed/composer.py` 组装：每屏 12 张按个人 6、每日 4、热门 2 的配额分配，某个数据源用完后，空位按其余数据源的权重比例分配，同一篇论文只出现一次；实时数据源合计不足 36 篇时追加兜底快照。详见 [后端 README · 首页论文数据源](../../apps/backend/README.md#首页论文数据源)。共享数据源不可用时只返回个人推荐，全部为空时前端第一页退回全局发现。第一页直接使用当天匿名列表（去掉已点赞、已收藏），个人推荐在请求第二页时才召回并组装、追加到同一份快照，前端在第一页显示后立即预取第二页；快照只存 ID 与归因，每页从候选池解析内容（详见后端 README）。快照中每篇论文的 `sources` 字段：个人推荐为召回来源，其他为数据源名（`daily` / `trending` / `fallback`）。

排序有效特征权重：主题 0.40、关键词 0.25、显式关注 0.20、已发布平台热度 0.10、论文年份时效 0.05；缺失特征不参与分母。关键词检索命中可作为该次兴趣查询的证据，即使知识底座没有返回完全相同的关键词标签；该信号按上游结果位置有界衰减，并使用“与你近期搜索的方向相关”理由。没有个人匹配的候选分数封顶为 0.15，避免仅凭时效超过相关论文。冷启动没有个人召回时，Feed 即为当天全站列表。主题多样性只在替代候选分数至少达到当前候选的 80% 时调整，避免引入明显不相关论文。推荐理由由实际匹配特征决定，不暴露行为明细；没有个人匹配或平台热度时 `reason` 为 `null`。按产品决定，首页卡片**不展示**推荐理由（避免让用户感到被分析），`reason` 仅随快照保存，用于归因与效果分析。首页与知识检索卡片共用结构化 `topics`，按上游顺序展示最多 5 个，并以完整 ID 跳转主题详情。每日候选和热门来自候选池，个人召回来自检索，兜底使用随包快照自带数据。历史条目缺失 `topics` 时显示无标签的卡片。分数是排序信号，不是喜欢概率。

`GET /api/v1/recommendations/papers?limit=12&cursor=...` 返回论文基础信息、理由、来源、位置、请求 ID、下一页游标、总数和算法版本。首次请求保存一小时用户私有快照（此时只含第一页，`has_more` 为真，`total` 为当前已确定的条数，第二页请求后才是整份列表的条数）；游标请求验证拥有者与过期时间：格式错误返回 400，快照不存在、已过期或属于他人统一返回 `20001/409`（与统计快照游标一致，表示不可重试、需从第一页重新开始）。`POST /api/v1/behavior-events/batch` 只接受登录用户受控事件；推荐曝光和点击携带推荐请求 ID 与位置。前端 Feed 的查询缓存按当前用户 ID 隔离，匿名用户继续使用全局发现列表。

三个接口都使用现有 BFF 身份，响应由现有 `{code, data}` 封装：

| 接口 | 输入 | `data` 核心字段 |
| --- | --- | --- |
| `GET /api/v1/recommendations/papers` | `limit` 1–48，`cursor` 可选 | `items`（每篇含 `id/title/abstract/authors/year/venue/pdf_url/thumbnail_url/image_id/keywords/subjects/topics/source/reason/sources/request_id/rank`；`reason` 可为 `null`；各数据源论文都携带 `image_id`，`thumbnail_url` 只有兜底快照论文非空，Web 优先使用该静态图）、`next_cursor`、`has_more`、`request_id`、`total`、`algorithm_version` |
| `GET /api/v1/recommendations/me/profile` | 无 | `long_topics`、`short_topics`、`long_keywords`、`short_keywords`、`explicit_subjects`、`has_history`、`computed_at`、`algorithm_version` |
| `POST /api/v1/behavior-events/batch` | `{events:[...]}`，每批 1–20 条；事件含 UUID `event_id`、类型、来源和对象，推荐事件另含 `request_id/rank`，搜索事件可含 UUID `query_id` | `inserted`（幂等后实际新增条数） |

前端采集失败会被吞掉，不影响原跳转；后端非法字段返回 422、非本人推荐反馈返回 400、未登录返回 401、超出每分钟限额返回 429。推荐召回单路知识底座异常（含超时与非预期异常）保留其他来源和全局发现；首屏推荐接口异常时 Web Feed 回退原发现 API，后续页不回退。主动搜索继续调用原 Knowledge 路由，推荐画像不进入搜索请求参数或排序。

## Embedding 后续评估

本地 `fastembed` 项目是 Apache-2.0 许可的 ONNX 推理库，`pgvector` 是 PostgreSQL 向量扩展。第一阶段不复制源码、不安装模型、不加数据库扩展，也不依赖第三方 Embedding API Key。后续用真实论文语言分布、标题/摘要覆盖率与 CPU/内存基准选择小模型，在离线任务批量生成向量，并以内容规则基线对照离线相关性和在线点击指标，再决定是否将向量召回接入现有推荐 Service；主动搜索保持独立。

历史验收与变更记录见 [search-recommendation-validation.md](../dev/records/engineering/search-recommendation-validation.md)。
