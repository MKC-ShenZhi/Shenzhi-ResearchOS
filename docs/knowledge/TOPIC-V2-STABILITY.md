# Topic V2 稳定性与维护约定

## 目录和详情

- 广场通过 Knowledge Client 和 Next.js BFF 请求 ShenZhi FastAPI。FastAPI 通过现有 Knowledge Base Client 使用 `KNOWLEDGE_BASE_API_URL`，读取 `GET /api/v1/topics/tree` 的默认响应。
- 默认 Tree 是广场、详情和新增关注的可见性依据。仅收录启用的 Topic 叶节点，按嵌套关系归入 Subfield。每个分类的 ID、标题和数量来自当前树。标题优先使用底座中文名，缺失时使用底座英文名。
- `GET /api/v1/knowledge/topics` 返回 `items`、`total` 和 `categories`。分类对象含 `id`、`name`、`total`。主题的 `category` 为 Subfield ID，`categoryName` 为显示名称。
- `GET /api/v1/knowledge/topics/{topicId}` 在目录校验后读取底座详情。原样使用完整 OpenAlex Topic ID，URL 中按单个路径段编码。旧 ID、父级节点及未开放主题返回 404。
- 每个 FastAPI 进程共享一份 5 分钟目录缓存，并合并并发刷新。失败后可以重试。旧 `topic_catalog.json` 仅供历史元数据消费者使用，广场和主题详情不读取该文件。
- 主题卡片和详情页通过 `TopicCover` 根据 OpenAlex Topic ID 加载同一张静态 WebP，缺图时显示默认渐变。主题卡片保留通用主题图标。底座暂未提供创作者和独立详细介绍，界面隐藏空的创作者字段，使用真实简介。论文目录统计来自底座。

## 广场交互

- 广场 Query 的 `staleTime` 为 15 分钟、`gcTime` 为 30 分钟。搜索和分类筛选基于完整目录。分类标签按 Subfield ID 写入 URL，标签只显示名称，空间不足时自动换行。
- 精选 ID 配置在 `topic-metadata.ts`，只展示当前目录中存在的启用主题。
- 广场保留精选和分类轮播。轮播先挂载 6 张，横向滚动临近末尾时追加 6 张。首个分类直接挂载，其余分类在距离视口 300px 时或键盘聚焦时激活。
- 分类和搜索结果每批展示 24 张，改变 `q` 或 `category` 时重置批次。搜索显式提交，输入法合成期间不提交。
- `q` 和 `category` 保留在浏览器历史中。详情链接通过 `returnTo` 保留当前广场 URL，详情正常页与错误页均可返回。`returnTo` 只接受内部的 `/knowledge/topics` 路径。

## 关联论文

- `GET /api/v1/knowledge/topics/{topicId}/papers?limit=20&offset=0` 在目录校验后调用底座的同名 Topic 论文接口。Adapter 将 `items` 转为已有论文卡片消费的 `results`，并用 `paper_id` 作为论文 ID。底座返回的 `total`、`limit`、`offset` 用于分页。
- 详情每批加载 10 篇，按请求 offset 加实际返回条数推进，空页或达到总数即停止。列表按论文 ID 去重。Subject Search 的 1,000 条限制仅适用于原 Subject Search 接口。
- 首次请求失败可重新加载。下一页失败保留已加载论文，暂停自动翻页并允许单独重试。分页缓存按 Topic ID 隔离，关闭焦点和重连时的自动全量刷新。

## 关注

- `topic_follows` 按 `(user_id, topic_id)` 持久化。新增关注要求登录并校验 OpenAlex Topic 是否在默认目录，重复写入保持幂等。
- 历史关注以原 ID 保存。旧记录可在个人列表中显示为下架主题并取消关注。两套 ID 各自统计，未进行名称匹配或数据迁移。
- 卡片和详情使用 `TopicFollowButton` 与 `TopicFollowerCount` 读取平台互动数据。微批查询、账号隔离、鉴权和写后缓存失效规则见 [收藏人数、论文点赞与主题关注](INTERACTIONS-AND-STATS.md)。

## 生成主题封面

[A1 封面生成工具](../../tools/topic-cover/README.md)经 ShenZhi Web 的主题关联论文接口和图片代理取图，将 8 张论文配图拼成四条斜向条带。工具批量输出 `1440 × 400` 的 WebP 到 `apps/web/public/topic-covers/`，主题卡片和详情页直接使用这些静态文件。

旧版验收记录见 [Topic V2 历史验收](../dev/records/knowledge/TOPIC-V2-validation.md)。
