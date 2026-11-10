# ShenZhi FastAPI

深知 AI（Agent）对话、Knowledge Capability、个人数据（收藏、点赞、阅读记录、私有论文）、首页论文 Feed、推荐、会议截稿、模型流与附件解析。浏览器只访问 Next.js 的 `/api/v1` BFF。

```bash
cd apps/backend
uv sync
cp .env.example .env

# 持久化开发需要 PostgreSQL：配置 CHAT_DATABASE_URL 后执行迁移。
#   uv run --env-file .env alembic upgrade head
# Windows 可用 ..\..\scripts\start-local-postgres.bat 启动项目专用实例（端口 5433，
# 可用 PG_BIN 指定安装目录）；CHAT_DATABASE_URL 的 host/port 需与实际实例一致。

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

推荐行为事件保留 90 天、分页快照 1 小时。清理入口为维护命令 `uv run --frozen python -m app.services.recommendation.maintenance`（可安全重复执行），以及只接受 `Authorization: Bearer $CRON_SECRET` 的 `GET /api/v1/internal/recommendation-maintenance`（未配置 `CRON_SECRET` 时返回 503）。开启 `BACKGROUND_JOBS_ENABLED` 后，进程内调度器每小时执行一次同样的清理（见下文“首页论文数据源 · 调度”），无需额外配置 Cron。

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

Agent 对话调用链（深知 AI、论文详情问答）：

```text
api/agent.py → services/agent/{runtime,service,...} + services/agent_sessions
→ services/agent/{knowledge_tools,read_paper,...} 等工具 → integrations / 外部 Provider
```

`api/identity.py` 提供 `/identity/bootstrap`（匿名身份初始化）与 `/identity/anonymous-claim`（登录后认领匿名 Agent 会话、工作区与附件，`services/identity/anonymous_claim.py`），见 [认证架构](../../docs/auth/ARCHITECTURE.md#anonymous-identity-and-claim)。

`app/api/knowledge.py` 提供的 ShenZhi-owned Knowledge API（前缀 `/api/v1/knowledge`）：

| 能力 | 接口 |
| --- | --- |
| 论文检索 / 详情 / 图谱 | `POST /search`、`GET /paper`、`GET /graph` |
| 会议导览 | `GET /conferences`、`GET /papers` |
| 知识库总览 | `GET /overview`、`GET /personal-overview`、`POST /overview/search` |
| 主题 | `GET /topics`、`GET /topics/{id}`、`GET /creators/{id}`、`GET /subjects/search` |
| 学者 | `GET /scholars/search`、`GET /scholars/{id}` |
| 基金 | `GET /funding/search`、`GET /fundings/search` |
| 批量论文 | `POST /api/v1/papers/batch` |

Agent 通过 `services/agent/knowledge_tools.py` 以工具形式调用同一 Knowledge Service。

Integration 内部职责保持分离：`client.py` 负责上游 HTTP transport，`schemas.py`
描述上游实际字段，`adapter.py` 映射到 ShenZhi Domain Contract，`exceptions.py`
统一上游调用异常。上游资源包括 retrieval search、scholars、funding、kg paper / graph、
`/api/papers`（会议浏览与首页候选池同步）及 knowledge summary 等。

响应使用 `data` envelope 和独立 Knowledge Contract；上游 `paper_id` 是不透明
字符串。不接知识底座认证/收藏接口，也不在 ShenZhi 侧修复上游数据和检索能力。

检索、详情、图谱 Contract v0 的核心字段为：Search `results[].id/title/abstract/authors/year/venue/keywords/subjects/score/rank`；
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

配置 `CHAT_DATABASE_URL` 后，Agent 会话及待发送附件的解析文本可跨后端实例读取。Agent 附件源文件不入库；临时文本在对话运行结束并写入记录后删除，未发送的记录 24 小时后失效，并由上传请求及维护命令清理。未配置数据库时的会话与附件仍依赖进程内存。

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
| `daily` | 当天的每日候选（`home_daily_editions`，由候选池离线生成）；当天没有时取 7 天内最新的一期，一条查询 | 300 | 每次组装 |
| `trending` | 候选池中平台点赞数 + 收藏数最高的论文，按列表日期之前（不含当天）最新完成的统计快照计算，当天快照重算不会让列表在白天变化 | 30 | 每次组装（缓存 60 秒） |
| `personal` | 登录用户的个人推荐（召回与排序见 [推荐实现](../../docs/engineering/search-recommendation-implementation.md)） | 100 | 登录用户首次请求 |
| `fallback` | 随包快照 `app/data/home_discovery_snapshot.json`（298 篇，自带 `public/paper-thumbnails` 静态图，即使底座图片服务不可用也能显示） | — | **只在**实时数据源合计不足 36 篇时追加一次 |

每屏 12 张按配额分配（`app/services/home_feed/config.py`）：匿名用户为每日 10、热门 2；登录用户为个人 6、每日 4、热门 2。某个数据源用完后，空位按其余数据源的权重比例分配（平滑加权轮询）。同一篇论文只保留第一次出现的位置；每屏同一会议不超过 4 张；整份列表最多 400 篇。每张卡片的 `source` 字段记录它来自哪个数据源，便于按数据源分析曝光和点击。

`GET /api/v1/discovery/papers`（匿名）每天组装一份列表。输入相同，组装结果就完全相同，所以各个实例不需要共享存储也能保持一致；cursor 绑定日期和列表哈希，跨过午夜继续翻页仍然读开始浏览时的那份列表；cursor 里的日期只接受今天和昨天，其他日期一律按“列表已更新”处理，不会为任意日期组装或缓存列表。各数据源的进程内缓存有效 60 秒，写入时清掉过期条目，所以内存占用不随运行时间或请求内容增长。如果同一天列表发生变化（例如 0:05 生成了当天的每日候选），旧 cursor 返回 `20001/409`，前端提示刷新并从第一页重新开始；cursor 格式错误返回 400。匿名首页请求从不访问知识底座。

登录用户的 `GET /api/v1/recommendations/papers` 每次访问对应一份 1 小时有效的私有快照：

- **第一页**直接取当天的匿名列表（去掉用户已点赞、已收藏的论文），不等知识底座召回。
- **第二页**请求时才召回、排序个人推荐，并与共享数据源按登录配额组装（排除第一页已展示的论文），追加到同一份快照。前端在第一页显示后立即请求第二页，所以召回时间被用户阅读第一屏的时间掩盖。并发的第二页请求只有一个会写入，其余读取已写入的结果。
- 快照只保存每篇论文的 ID、位置、数据源、推荐理由和召回来源（每篇约 100 字节）；每页按 ID 从候选池取内容，兜底论文从随包快照取。候选池里没有的论文（例如召回到的其他会议论文）才在快照里保存完整内容。快照期间被同步移出候选池的论文会被跳过。

### 候选池与每日候选

`discovery_pool_papers`（迁移 `018_discovery_pool`）保存候选池年份内能在首页展示的知识底座论文，包括 `primary_subject`。候选池年份默认 2026（底座图片几乎只覆盖这一年），可以用 `HOME_FEED_POOL_YEAR` 覆盖。每日候选存于 `home_daily_editions`（迁移 `019_home_daily_editions` 由已退役功能的 `daily_recommendations` 表改名而来，旧数据不会被当作每日候选使用，超过 120 天后由调度器清理）。

- `sync`：按会议遍历 `/api/papers` 该年份的全部分页，经规则 B 过滤后，在一个事务内整体替换该年份的候选池。任一分页重试后仍失败则整次中止；如果新结果少于原有的一半，视为上游异常，拒绝写入。2026-11-01 实测：24 个会议、抓取 18,863 篇、收录 15,803 篇，耗时约 2 分 20 秒。
- `publish`（规则 A）：每天生成 300 篇。"最久未展示的优先、同一天内按哈希打散"，整个候选池轮完一遍才会重复（约 52 天一个周期）。展示时间相同的候选中，同一会议不超过 25%、同一 `primary_subject` 不超过 5%。同一天重复执行结果一致；只回溯最近 120 天的展示历史。

```bash
cd apps/backend
uv run --locked --env-file .env python -m app.services.discovery_pool sync [--year 2026] [--dry-run]
uv run --locked --env-file .env python -m app.services.discovery_pool publish [--date 2026-11-02] [--dry-run]
```

**调度**：设置 `BACKGROUND_JOBS_ENABLED=true` 后，API 进程每 10 分钟检查一次，并用 Postgres advisory lock 保证多个 worker 或实例中只有一个执行：候选池为空或距上次同步超过 7 天时执行 `sync`（失败后 1 小时内不重试）；上海时间 00:05 之后当天还没有每日候选时执行 `publish`；每小时执行一次 `purge`，删除已过期的推荐快照、90 天前的行为事件和 120 天前的每日候选（之后的生成不再读取它们）。是否到期完全由数据库状态判断，所以进程重启或错过某次检查后，下一次检查会自动补上。默认关闭，本地开发和测试不会去请求底座。调度器随 FastAPI `lifespan` 启动，依赖长驻进程；Serverless 部署下的限制见 [部署与运行环境](../../docs/engineering/deployment.md)。

**兜底快照**：输入是 `data/discovery/home-seed-300.json`，部署产物是 `apps/backend/app/data/home_discovery_snapshot.json` 和 `apps/web/public/paper-thumbnails/*.webp`，可以用 `python3 scripts/publish_home_discovery.py [--check]` 重新发布（需要种子中指向的原始图片）。2026-11-01 已用候选池数据为种子和快照补上了 `image_id`、`keywords` 和 `subjects`；种子里有 2 篇（标题为 "1 Introduction"、摘要被截断）会被规则 B 剔除。

部署新版本仍需按常规流程执行数据库迁移：

```bash
cd apps/backend
uv run --locked --env-file .env alembic upgrade head
```

`agent_uploads` 临时文本表的过期清理：`uv run --locked python -m app.services.agent_uploads`（输出 `expired_agent_uploads`）。迁移 `021_drop_chat_tables` 删除旧 Chat 会话表 `chat_sessions` / `chat_messages`，数据不保留。

维护说明：[Agent 对话](../../docs/agent/README.md) · [认证架构](../../docs/auth/ARCHITECTURE.md) · [部署与运行环境](../../docs/engineering/deployment.md)。

## 会议 DDL 后台同步

会议更新统一由原有 `HomeFeedScheduler` 在常驻后端中执行，不使用独立的 Vercel Cron、Actions 或 HTTP 触发接口。

- 配置 `CHAT_DATABASE_URL` 并按团队数据库变更流程执行迁移。
- 设置统一开关 `BACKGROUND_JOBS_ENABLED=true`，启动常驻后端。
- 每10分钟检查数据库状态，成功检查满23小时才访问上游；失败满1小时后由后续检查重试，失败保留旧快照。
- 是否启用只由上述显式开关决定，不再根据 VERCEL 环境变量静默关闭；部署者须确保后端进程持续运行。临时Serverless环境不能据此验收定时任务。
- 手动排查：`uv run --locked --env-file .env python -m app.services.conferences.cli sync --dry-run`。

部署步骤、删除会议处理和流程图见 [会议同步设计](../../docs/conferences/AUTO-SYNC-DESIGN.md)。
