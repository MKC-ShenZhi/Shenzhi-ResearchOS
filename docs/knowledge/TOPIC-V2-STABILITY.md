# Topic V2 稳定性与维护约定

Topic 目录继续沿用 JSON → FastAPI → Next.js BFF → Knowledge Client → Feature；
目录本身不入库，不含推荐算法或创作者主页。主题关注为服务端账号数据：
`topic_follows` 表（迁移 `012_topic_follows`），经 `PUT/DELETE /api/v1/topic-follows/{topic_id}`
写入，卡片与详情通过 `features/knowledge/interactions/components/topic-follow-button.tsx`
操作，口径与接口见 [收藏人数、论文点赞与主题关注](INTERACTIONS-AND-STATS.md)。

## 目录维护

- 数据文件：`apps/backend/app/data/topic_catalog.json`。
- 运行时检查 Schema、必要文本非空、ID 唯一、忽略大小写后的 subjectQuery 唯一、非负统计和平台作者 ID。
- 图片只接受 `/images/topics/<文件名>.<png|jpg|jpeg|webp|avif|svg>` 的本地资源路径；禁止目录穿越、编码路径、URL、查询串和反斜杠。
- FastAPI 不读取前端源码或 public 目录。图片存在性由 `test_topic_catalog.py` 在仓库中验证；卡片和详情共用 `TopicCover`，加载失败显示默认封面。
- 数量和分类版本快照仅保留在数据质量测试中。正常新增主题或分类不需要修改 Loader 常量；有意更新目录时同步更新测试快照及演示 fixture。
- 当前前端 `MOCK_TOPICS` 是显式 mock 数据，测试校验它与后端 JSON 一致；正式 BFF 失败不会切换到 mock。
- Registry 构造及路由导入不读取 Catalog；首次 Topic / Creator 请求才加载。加载失败沿用知识接口的日志与标准 `UNKNOWN` 500，不影响其他知识接口；有效目录中的缺失 ID 仍返回 404。
- `load_topic_catalog()` 按进程缓存成功结果，失败不缓存，修复文件后下一次请求可重试。更新已缓存的目录时，在对应服务进程调用 `load_topic_catalog.cache_clear()`；已有 Registry 随下一次请求取得新数据，多 worker 时需逐进程清理或滚动重启 worker。

当前目录 293 条记录全部启用，ID 与 subjectQuery 无重复，8 个分类：

| 分类 | 数量 |
| --- | ---: |
| 机器学习 | 49 |
| 计算机视觉 | 34 |
| 自然语言处理 | 30 |
| 大语言模型 | 58 |
| 智能体 | 25 |
| 多模态 | 22 |
| 语音/音频处理 | 40 |
| 生成式AI | 35 |

原始规划的 294 条、语音/音频 41 条尚未核实。仓库未发现原始 Excel 或 Topic 导入脚本；可访问 Git 历史中的目录从 7 条直接扩展为 293 条，未找到 294 条版本。应由数据提供方对照原始清单确认，不补造主题。

## 相关论文与数量

Subject Search 使用 `subjectQuery`，经 ShenZhi 自身接口
`GET /api/v1/knowledge/subjects/search?subject=...&offset=0&limit=10` 查询。
后端校验 `0 <= offset < 1000`、`1 <= limit <= 100`。

`topic-paper-query.ts` 维护 Topic 分页配置和可独立测试的纯判断：

- 下一页为上一页请求 offset 加实际返回条数。
- 总数耗尽、空页或达到 1000 时终止；接近上限时缩小 limit，最多展示前 1000 条。
- 达到上限且还有论文时显示“仍有论文未展示”；上游提前返回空页时显示部分结果尚未展示，不误报全部加载完成。
- UI 按 ID 去重，但分页按原始结果条数递进。
- 首次失败使用统一错误组件及 `refetch`；下一页失败保留缓存，通过 `isFetchNextPageError` 展示“重试下一页”，调用 `fetchNextPage({ cancelRefetch: false })`。
- IntersectionObserver 在请求中或失败时不自动加载；并发触发设请求锁。关闭焦点/重连自动全量刷新，沿用 Knowledge 的最多一次、仅 retryable 错误自动重试规则。

Catalog 的 `paperCount` 是目录收录时的统计，目前没有统计时间或上游版本字段。卡片明确标为“目录统计”，不会逐卡查询知识底座。详情仅在相关论文区使用最近检索响应的 `total`；不同时展示另一个目录总数。

## 广场和详情

- 广场目录仍一次获取全部主题，搜索与分类筛选始终基于完整目录；只改变卡片挂载策略，不改变 FastAPI Catalog 契约。目录 Query 的 `staleTime` 为 15 分钟、`gcTime` 为 30 分钟。
- 默认广场保留精选和分类轮播。每个轮播先挂载 6 张，横向滚动距已挂载末尾约一张卡片时追加 6 张；滚动/resize 的同一批次只追加一次。向左返回保留已挂载卡片。
- 首个分类直接挂载，其余分类在距离视口 300px 时激活；占位保留一行卡片高度。键盘聚焦分类区域也会激活；不支持 IntersectionObserver 时退回立即挂载。Observer 和滚动监听随卸载清理。
- 分类与搜索结果按完整筛选结果每批展示 24 张，通过“加载更多主题”追加，保留分组和分类总数；改变 q/category 时重置批次。结果计数通过 `role="status"` 通知辅助技术。
- 卡片的关注状态与关注人数由 `TopicFollowButton` / `TopicFollowerCount` 按主题读取（同一事件循环内微批合并为一次 `POST /api/v1/topics/interactions`）；写入后以服务端返回为准并失效对应缓存，同一主题在精选、分类与详情中同步更新。匿名点击只弹出登录窗口。
- 精选主题在 `topic-metadata.ts` 配置固定 ID；跳过缺失或禁用的主题，与 JSON 顺序无关。
- 创作者只展示静态信息，取消没有可见结果的按钮与预取行为。
- 搜索保持显式提交，输入法合成期间不提交；清空和分类与关键词组合保留现有行为。
- URL 更新保留其他参数，去除空的 q/category；有变化时 push 浏览历史，使前进/后退能恢复查询与分类。
- 广场卡片将当前内部 URL 编码到详情链接的 `returnTo`。详情正常页与错误页均通过该参数返回，刷新或新标签打开仍保留 q/category；缺失或非法来源回退 `/knowledge/topics`。复用内部 URL 校验并仅允许字面路径 `/knowledge/topics`，拒绝外部地址、协议相对地址、其他页面、编码路径和目录穿越。
- 详情显示封面、中文名、英文名、分类、创建者、简介和实时关联论文；保留加载、404、错误和空数据状态。

历史验收与变更记录见 [TOPIC-V2-validation.md](../dev/records/knowledge/TOPIC-V2-validation.md)。
