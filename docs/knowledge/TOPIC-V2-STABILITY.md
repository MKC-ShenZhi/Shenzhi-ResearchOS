# Topic V2 稳定性与维护约定

Topic 继续沿用 JSON → FastAPI → Next.js BFF → Knowledge Client → Feature。
不新增数据库、推荐算法或创作者主页。关注仍为本地模拟状态。

## 目录维护

- 数据文件：`apps/backend/app/data/topic_catalog.json`。
- 运行时检查 Schema、必要文本非空、ID 唯一、忽略大小写后的 subjectQuery 唯一、非负统计和平台作者 ID。
- 图片只接受 `/images/topics/<文件名>.<png|jpg|jpeg|webp|avif|svg>` 的本地资源路径；禁止目录穿越、编码路径、URL、查询串和反斜杠。
- FastAPI 不读取前端源码或 public 目录。图片存在性由 `test_topic_catalog.py` 在仓库中验证；卡片和详情共用 `TopicCover`，加载失败显示默认封面。
- 数量和分类版本快照仅保留在数据质量测试中。正常新增主题或分类不需要修改 Loader 常量；有意更新目录时同步更新测试快照及演示 fixture。
- 当前前端 `MOCK_TOPICS` 是显式 mock 数据，测试校验它与后端 JSON 一致；正式 BFF 失败不会切换到 mock。

2026-10-13 核对：293 条记录全部启用，ID 与 subjectQuery 无重复，8 个分类：

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
后端当前校验 `0 <= offset < 1000`、`1 <= limit <= 100`；本次保留该约束。

`topic-paper-query.ts` 维护 Topic 分页配置和可独立测试的纯判断：

- 下一页为上一页请求 offset 加实际返回条数。
- 总数耗尽、空页或达到 1000 时终止；接近上限时缩小 limit，最多展示前 1000 条。
- 达到上限且还有论文时显示“仍有论文未展示”；上游提前返回空页时显示部分结果尚未展示，不误报全部加载完成。
- UI 按 ID 去重，但分页按原始结果条数递进。
- 首次失败使用统一错误组件及 `refetch`；下一页失败保留缓存，通过 `isFetchNextPageError` 展示“重试下一页”，调用 `fetchNextPage({ cancelRefetch: false })`。
- IntersectionObserver 在请求中或失败时不自动加载；并发触发设请求锁。关闭焦点/重连自动全量刷新，沿用 Knowledge 的最多一次、仅 retryable 错误自动重试规则。

Catalog 的 `paperCount` 是目录收录时的统计，目前没有统计时间或上游版本字段。卡片明确标为“目录统计”，不会逐卡查询知识底座。详情仅在相关论文区使用最近检索响应的 `total`；不同时展示另一个目录总数。

## 广场和详情

- 精选主题在 `topic-metadata.ts` 配置固定 ID；跳过缺失或禁用的主题，与 JSON 顺序无关。
- 创作者只展示静态信息，取消没有可见结果的按钮与预取行为。
- 搜索保持显式提交，输入法合成期间不提交；清空和分类与关键词组合保留现有行为。
- URL 更新保留其他参数，去除空的 q/category；有变化时 push 浏览历史，使前进/后退能恢复查询与分类。
- 详情显示封面、中文名、英文名、分类、创建者、简介和实时关联论文；保留加载、404、错误和空数据状态。

## 本地验证（2026-10-13）

| 命令 / 验收 | 结果 |
| --- | --- |
| `cd apps/web && pnpm typecheck` | 通过 |
| `cd apps/web && pnpm lint` | 通过 |
| `cd apps/web && pnpm test` | 279 项通过 |
| `cd apps/web && pnpm build` | 通过，Turbopack 生产构建及 30 个静态页面生成成功 |
| `cd apps/backend && uv --cache-dir /private/tmp/shenzhi-topic-uv-cache run --locked --no-sync python -m unittest discover -s tests -p 'test_topic*.py'` | 14 项通过，包含目录质量与资源存在性 |
| `cd apps/backend && uv --cache-dir /private/tmp/shenzhi-topic-uv-cache run --locked --no-sync python -m unittest discover -s tests -p 'test_knowledge*.py'` | 103 项通过，包含正常响应与分页边界 |
| `cd apps/backend && uv --cache-dir /private/tmp/shenzhi-topic-uv-cache run --locked --no-sync python -m unittest discover -s tests` | 403 项：379 通过、23 跳过、1 导入错误 |
| 浏览器实际 BFF 链路 | 中文、llm、英文 subjectQuery、Enter、搜索按钮、分类组合、空结果、前进/后退已验证 |
| 真实知识底座 | 机器翻译主题 total=22；offset=0/10/20 均 200，10→20→22，结束提示正确；打开论文摘要成功并通过返回按钮回到 Topic |
| 窄屏详情 | 封面、简介、创建者、实时数量及列表正常，无横向页面溢出 |
| 下一页故障注入 | 对比学习已加载 10 条后临时停止本次启动的本地 FastAPI；offset=10 两次 503（初次 + 一次自动重试）后保留 10 条并显示手动重试；继续滚动没有额外请求；恢复后手动重试仅请求 offset=10，追加为 20 条，20 个唯一论文链接 |

后端全量测试的唯一错误是 `test_reading_history.py` 仍导入已不存在的 `app.services.reading_history`，本地 dev 也存在相同引用；属于既有无关问题。本次没有修改它。23 个跳过项需要对应数据库/集成测试环境。

沙箱内无法监听本地端口，最初 Turbopack 构建未完成；获得工具权限后，沿用原构建命令成功。uv 使用临时缓存及 `--locked --no-sync`，不更新依赖和锁文件。本地联调启动 FastAPI 时关闭 lifespan，避免无关的 Chat 恢复操作，因此不代表完整后台启动和数据库恢复验证。

真实输入法候选确认、不同浏览器、PDF 正文/图谱及超 1000 条主题的上游实测仍需人工验收。1000 条停止、失败后缓存保留和只重试下一页由实际 TanStack Query Observer 回归测试覆盖。

## 合并 dev 前的既有分支差异

以下是 `dev...HEAD` 中已有内容，本次未修改或删除，需负责人确认是否应随 Topic 合并：

- `apps/backend/uv.lock`：1581 行增加、1408 行删除，registry 从 PyPI 改为清华镜像，26 个包版本变化，并新增 opentelemetry-api。pyproject.toml 没有对应差异；不能视为 Topic 所需依赖变化。
- `app/models/chat.py`：增加匿名会话过期索引；仓库已有对应迁移，仍属于 Chat 清理能力。
- `migrations/env.py`：新增 collections、reading_history 模型导入，属于文献/阅读历史迁移配置。
- `OPEN.bat`、`scripts/start-local-services.ps1`、`scripts/start-local-postgres.bat`、ONBOARDING：修改 Windows PostgreSQL、FastAPI、Next.js 的启动与就绪检查流程；本次 macOS 未执行这些脚本。

Topic 修改已通过适用检查；整分支尚不能作为全量绿灯直接合并。需先确认上述范围、修复或明确豁免既有测试导入错误，并完成真实输入法与部署环境人工验收。
