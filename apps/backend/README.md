# ShenZhi FastAPI

Chat、论文检索、模型流、联网搜索、附件解析及 Knowledge Capability。浏览器只访问 Next.js 的 `/api/v1` BFF。

```bash
cd apps/backend
uv sync
cp .env.example .env

# Windows 本地持久化开发：先启动项目专用 PostgreSQL 5433 实例。
# PowerShell/CMD:
#   ..\..\scripts\start-local-postgres.bat
# 若已有可用的 PostgreSQL，请确保 CHAT_DATABASE_URL 的 host/port 与实例一致。

# Configure provider/search keys before starting.
# Missing keys produce explicit errors, never mock answers.
uv run uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000

# Validate backend code and tests.
uv run python -m compileall app
uv run python -m unittest discover -s tests -v
```

Web 设置：

```text
BUSINESS_BACKEND_URL=http://127.0.0.1:8000
```

两端配置相同 `BACKEND_BFF_SECRET`；后端只允许私网/BFF 访问，不能直接暴露公网。

推荐行为事件保留 90 天、分页快照 1 小时。清理入口为维护命令 `uv run --frozen python -m app.services.recommendation.maintenance`（可安全重复执行），以及只接受 `Authorization: Bearer $CRON_SECRET` 的 `GET /api/v1/internal/recommendation-maintenance`（未配置 `CRON_SECRET` 时返回 503）。仓库当前**未**在 `vercel.json` 注册任何 Cron，线上调度需部署负责人另行配置并确认。

未配置 Secret 时默认拒绝；仅 loopback 本地开发可在两端显式设置：

```text
BACKEND_ALLOW_INSECURE_LOCAL_BFF=true
```

## Knowledge Capability

Knowledge Base 是外部 Research Capability。FastAPI 后端统一通过
`app/integrations/knowledge/` 接入，调用链固定为：

```text
FastAPI API → app/services/knowledge/service.py → app/integrations/knowledge → 上游知识底座科研组 API
```

Chat 调用链：

```text
api/chat.py → services/chat/service.py → services/chat/{repository,attachments,grounding,...}
→ integrations/{llm,web_search} → 外部 Provider
```

当前只承诺三条 ShenZhi-owned Capability API：

```text
POST /api/v1/knowledge/search
GET  /api/v1/knowledge/paper?paperId=...
GET  /api/v1/knowledge/graph?paperId=...&depth=1
```

Integration 内部职责保持分离：`client.py` 负责上游 HTTP transport，`schemas.py`
描述上游实际字段，`adapter.py` 映射到 ShenZhi Domain Contract，`exceptions.py`
统一上游调用异常。当前上游资源仅限 retrieval search、paper detail、paper graph。

响应使用 `data` envelope 和独立 Knowledge Contract；上游 `paper_id` 是不透明
字符串，且必须来自 retrieval search，不能使用会议列表接口的 `paper_id`。本阶段
不接 Chat Tool、`/api/papers`、multistep 或知识底座认证/收藏接口，也不在 ShenZhi
侧修复上游数据和检索能力。

Contract v0 的核心字段为：Search `results[].id/title/abstract/authors/year/venue/keywords/subjects/score/rank`；
Detail `id/title/abstract/authors/year/venue/doi/pdfUrl/keywords/subjects/citationCount/referenceCount`；
Graph `rootId/nodes/edges`，边使用 `sourceId/targetId/relation`。空字符串归一化为 `null`，
未知引用数保持 `null`，节点和关系类型为开放字符串。错误响应包含
`code/message/retryable/requestId`。Search 请求只使用 `query/topK/yearFrom/yearTo/venue/author/keyword/subject`；
上游的 snake_case 字段只在 Adapter 到 HTTP Client 的边界出现。

`GET /api/v1/knowledge/paper` 只返回知识底座论文详情和 `pdfUrl`，不预先访问 PDF 源站。
用户首次打开 Paper 视图时，站内 PDF.js 才通过受控的
`GET /api/v1/paper-resource/pdf?paperId=...` 同源端点读取字节流，避免科研源站缺少
CORS 响应头导致浏览器拒绝加载。端点只接受可信 `paperId`，不接受任意 URL；Backend
在该端点内复用 `PaperResourceService` 与 Provider 完成校验和流式读取，不持久化或缓存 PDF。
配置项为 `PAPER_RESOURCE_TIMEOUT`（秒）与
`PAPER_MAX_SIZE_MB`（可获取资源大小上限）。

配置 `CHAT_DATABASE_URL` 后，Agent 会话及待发送附件的解析文本可跨后端实例读取。Agent 附件源文件不入库；临时文本在对话运行结束并写入记录后删除，未发送的记录 24 小时后失效，并由上传请求及维护命令清理。旧 Chat 附件和未配置数据库时的会话仍依赖进程内存。

Python 环境与依赖统一使用 [uv](https://docs.astral.sh/uv/) 管理。新增依赖使用：

```bash
uv add <package>
```

新增开发依赖使用：

```bash
uv add --dev <package>
```

## 首页论文数据源

首页 Feed 由多个**数据源**组成，每个数据源只产出候选论文；合并、排序、去重统一由 `app/services/home_feed/composer.py` 完成。所有数据源的论文都要通过同一道准入检查（规则 B，`app/services/home_feed/rules.py`），不能在卡片上正常展示的论文会被剔除：图片必须是图片代理能接受的 png/jpg/webp（或兜底快照自带的静态 WebP），标题不能是章节名（如 "1 Introduction"），摘要至少 200 字，作者清洗后不能为空；topic 会去掉会议标签和重复项。

| 数据源 | 来源 | 上限 | 何时读取 |
| --- | --- | --- | --- |
| `daily` | 当天的每日候选（`daily_recommendations`，由候选池离线生成）；当天没有时取 7 天内最新的一期，一条查询 | 300 | 每次组装 |
| `trending` | 候选池中平台点赞数 + 收藏数最高的论文，按列表日期当天或之前最新完成的统计快照计算 | 30 | 每次组装（缓存 60 秒） |
| `personal` | 登录用户的个人推荐（召回与排序见 [推荐实现](../../docs/engineering/search-recommendation-implementation.md)） | 100 | 登录用户首次请求 |
| `fallback` | 随包快照 `app/data/home_discovery_snapshot.json`（298 篇，自带 `public/paper-thumbnails` 静态图，即使底座图片服务不可用也能显示） | — | **只在**实时数据源合计不足 36 篇时追加一次 |

每屏 12 张按配额分配（`app/services/home_feed/config.py`）：匿名用户为每日 10、热门 2；登录用户为个人 6、每日 4、热门 2。某个数据源用完后，空位按其余数据源的权重比例分配（平滑加权轮询）。同一篇论文只保留第一次出现的位置；每屏同一会议不超过 4 张；整份列表最多 400 篇。每张卡片的 `source` 字段记录它来自哪个数据源，便于按数据源分析曝光和点击。

`GET /api/v1/discovery/papers`（匿名）每天组装一份列表。输入相同，组装结果就完全相同，所以各个实例不需要共享存储也能保持一致；cursor 绑定日期和列表哈希，跨过午夜继续翻页仍然读开始浏览时的那份列表。如果同一天重新发布了每日候选导致列表变化，旧 cursor 返回 400，前端需要刷新。登录用户的 `GET /api/v1/recommendations/papers` 使用同样的组装逻辑，结果保存为 1 小时有效的私有快照。首页请求从不访问知识底座。

### 候选池与每日候选

`discovery_pool_papers`（迁移 `018_discovery_pool`）保存候选池年份内能在首页展示的知识底座论文，包括 `primary_subject`。候选池年份默认 2026（底座图片几乎只覆盖这一年），可以用 `HOME_FEED_POOL_YEAR` 覆盖。

- `sync`：按会议遍历 `/api/papers` 该年份的全部分页，经规则 B 过滤后，在一个事务内整体替换该年份的候选池。任一分页重试后仍失败则整次中止；如果新结果少于原有的一半，视为上游异常，拒绝写入。2026-11-01 实测：24 个会议、抓取 18,863 篇、收录 15,803 篇，耗时约 2 分 20 秒。
- `publish`（规则 A）：每天生成 300 篇。"最久未展示的优先、同一天内按哈希打散"，整个候选池轮完一遍才会重复（约 52 天一个周期）。展示时间相同的候选中，同一会议不超过 25%、同一 `primary_subject` 不超过 5%。同一天重复执行结果一致；只回溯最近 120 天的展示历史。

```bash
cd apps/backend
uv run --locked --env-file .env python -m app.services.discovery_pool sync [--year 2026] [--dry-run]
uv run --locked --env-file .env python -m app.services.discovery_pool publish [--date 2026-11-02] [--dry-run]
```

**调度**：设置 `HOME_FEED_SCHEDULER_ENABLED=true` 后，API 进程每 10 分钟检查一次，并用 Postgres advisory lock 保证多个 worker 或实例中只有一个执行：候选池为空或距上次同步超过 7 天时执行 `sync`（失败后 1 小时内不重试）；上海时间 00:05 之后当天还没有每日候选时执行 `publish`。是否到期完全由数据库状态判断，所以进程重启或错过某次检查后，下一次检查会自动补上。默认关闭，本地开发和测试不会去请求底座。

**兜底快照**：输入是 `data/discovery/home-seed-300.json`，部署产物是 `apps/backend/app/data/home_discovery_snapshot.json` 和 `apps/web/public/paper-thumbnails/*.webp`，可以用 `python3 scripts/publish_home_discovery.py [--check]` 重新发布（需要种子中指向的原始图片）。2026-11-01 已用候选池数据为种子和快照补上了 `image_id`、`keywords` 和 `subjects`；种子里有 2 篇（标题为 "1 Introduction"、摘要被截断）会被规则 B 剔除。

部署新版本仍需按常规流程执行数据库迁移：

```bash
cd apps/backend
uv run --locked --env-file .env alembic upgrade head
```

`agent_uploads` 临时文本表及匿名 Chat 会话仍按原维护策略清理。

维护说明：[Chat 架构、协议与配置](../../docs/chat/README.md)。
