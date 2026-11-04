# 深知 ShenZhi · Research OS

> 深知是面向人工智能领域学术科研的**专业可信知识智能体服务平台**,提供论文检索、投稿筛选,以及用于 Deep Research 与 Auto Research 的知识智能体服务。
>
> 仓库为 monorepo:`apps/web` 是 Next.js 前端与 BFF,`apps/backend` 是 FastAPI 核心业务后端。

新人请先看 [ONBOARDING.md](ONBOARDING.md);工程架构见 [docs/engineering/architecture-confirmation.md](docs/engineering/architecture-confirmation.md);部署与运行环境见 [docs/engineering/deployment.md](docs/engineering/deployment.md)。

---

## 快速开始

Web:

```bash
cd apps/web
pnpm install        # pnpm 11:构建脚本白名单见 pnpm-workspace.yaml(sharp)
cp .env.example .env.local
pnpm dev            # http://localhost:3000(--turbopack)
```

Backend(AI 对话、知识库、个人数据等能力需要):

```bash
cd apps/backend
uv sync
cp .env.example .env                          # 配置模型 Key、CHAT_DATABASE_URL 等
uv run --env-file .env alembic upgrade head   # 配置数据库后执行迁移
uv run uvicorn app.main:app --env-file .env --reload --host 127.0.0.1 --port 8000
```

Web 端设置 `BUSINESS_BACKEND_URL=http://127.0.0.1:8000`(仅服务端)。本地最小配置与常见问题见 [ONBOARDING.md](ONBOARDING.md)。

URL 加 `?theme=dark` / `?theme=light` 可强制日/夜模式,`?theme=<预设 ID>` 可指定主题预设(用于调试与分享)。

常用检查:

```bash
cd apps/web && pnpm typecheck && pnpm lint && pnpm test && pnpm build
cd apps/backend && uv run python -m unittest discover -s tests -v
```

---

## 页面路由

侧栏一级入口为「发现」「深知 AI」「会议DDL」「我的文献」与「知识库」子栏目。`lib/feature-availability.ts` 集中登记暂未开放的路由,访问时提示「功能暂未上线」。

| 路由 | 页面 | 实现位置 |
|------|------|----------|
| `/` | 发现页(搜索入口 + 首页论文 Feed) | [HomePage.tsx](apps/web/features/home/HomePage.tsx) |
| `/agents` | 深知 AI(无 `session` 参数为新对话页,带 `?session=` 为会话页) | [agent-home-page.tsx](apps/web/features/agent-chat/agent-home-page.tsx)、[shenzhi-ai-page.tsx](apps/web/features/agent-chat/shenzhi-ai-page.tsx) |
| `/submit` | 会议DDL(会议截稿倒计时与关注,见 [docs/conferences](docs/conferences/README.md)) | [SubmitPage.tsx](apps/web/features/submit/SubmitPage.tsx) |
| `/papers/[id]` | 论文详情(PDF 阅读器 + 论文 Agent 问答) | [PaperDetailPage.tsx](apps/web/features/papers/[id]/PaperDetailPage.tsx) |
| `/papers/[id]/graph` | 论文关系图谱 | [KnowledgeRelationGraphPage.tsx](apps/web/features/knowledge/graph/KnowledgeRelationGraphPage.tsx) |
| `/knowledge` | 知识库总览 | [KnowledgePage.tsx](apps/web/features/knowledge/KnowledgePage.tsx) |
| `/knowledge/papers` | 我的文献(收藏、点赞、阅读记录、私有论文) | [KnowledgePapersPage.tsx](apps/web/features/knowledge/papers/KnowledgePapersPage.tsx) |
| `/knowledge/search` | 论文库(关键词检索 / 会议导览) | [KnowledgeSearchPage.tsx](apps/web/features/knowledge/search/KnowledgeSearchPage.tsx) |
| `/knowledge/search/conferences` | 会议目录 | [ConferenceDirectoryPage.tsx](apps/web/features/knowledge/search/conferences/ConferenceDirectoryPage.tsx) |
| `/knowledge/scholars`、`/knowledge/scholars/[scholarId]` | 学者库与学者详情 | [ScholarsPage.tsx](apps/web/features/knowledge/scholars/ScholarsPage.tsx)、[ScholarDetailPage.tsx](apps/web/features/knowledge/scholars/ScholarDetailPage.tsx) |
| `/knowledge/scholars/graph` | 学者关系网络 | [ScholarGraphPage.tsx](apps/web/features/knowledge/scholars/graph/ScholarGraphPage.tsx) |
| `/knowledge/topics`、`/knowledge/topics/[topicId]` | 主题库与主题详情 | [TopicsPage.tsx](apps/web/features/knowledge/topics/TopicsPage.tsx)、[topic-detail-page.tsx](apps/web/features/knowledge/topics/detail/topic-detail-page.tsx) |
| `/knowledge/funding` | 项目基金库 | [FundingPage.tsx](apps/web/features/knowledge/funding/FundingPage.tsx) |
| `/knowledge/institutions`、`/knowledge/patents` | 机构库、专利库(展示数据,未接真实接口) | [features/knowledge/](apps/web/features/knowledge/) |
| `/settings` | 个人设置 | [SettingsPage.tsx](apps/web/features/settings/SettingsPage.tsx) |
| `/login/[provider]`、`/reset-password` | OAuth 校验、重置密码 | [features/login](apps/web/features/login/)、[features/reset-password](apps/web/features/reset-password/) |

暂未开放(原型页面,由 `feature-availability` 拦截):`/knowledge/graph`(私域知识图谱)、`/projects/*`、`/submit/journals`、`/agents/deep-research`、`/agents/auto-research`、`/agents/deep-search`。

兼容重定向:`/search` → `/knowledge/search`;`/scholars[/id]` → `/knowledge/scholars[/id]`;`/knowledge/search/[paperId][/graph]` → `/papers/[id][/graph]`;`/agents/ask` → `/`。

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | Next.js 16(App Router,Turbopack)+ React 19 + TypeScript |
| 样式 | Tailwind CSS 4(CSS-first `@theme`)+ tw-animate-css;手写 shadcn 风格 UI 原语(cva 变体) |
| 数据与状态 | TanStack Query v5;Zustand v5(侧栏、主题、本地偏好等客户端状态);Zod 校验 |
| 内容渲染 | react-markdown + remark-gfm / remark-math + KaTeX;react-pdf / pdfjs-dist;latex.js |
| 图谱与动效 | @relation-graph/react;Framer Motion;Lucide React |
| 认证 | Better Auth + PostgreSQL(`pg`),邮件经阿里云 DirectMail |
| 后端 | FastAPI(Python 3.12,uv 管理依赖),SQLAlchemy + asyncpg + Alembic |
| 测试 | Web:Node.js `node:test`;Backend:`unittest`;`tests/visual/` 截图脚本 |

---

## 目录结构

```text
shenzhi/
├── apps/
│   ├── web/          # Next.js:app 为薄路由,features 为页面实现,clients 封装 BFF / Backend 调用
│   └── backend/      # FastAPI:api / services / integrations / schemas / models / core
├── data/             # 首页兜底快照种子、会议截稿等离线数据源
├── docs/             # 工程规范、模块文档、PRD、设计材料与历史记录(见 docs/README.md)
├── scripts/          # 数据发布脚本(会议截稿、首页兜底快照)与本地辅助脚本
├── tests/visual/     # 页面、主题与图谱截图脚本
├── tools/brand/      # 品牌资源处理工具
└── README.md
```

---

## 品牌与设计令牌

- **标识**:书法「深知」日/夜双版,随主题 CSS 切换,无 JS 闪烁。运行时资产位于 `apps/web/public/brand/`,资产管线见 `tools/brand/process_logo.py`。
- **配色**:默认「深知」预设主色 `#174a7e`(夜间 `#5a94c8`),智能体强调色 `#0f766e`;辅助紫 / 青 / 金 `#f3d029`(金底一律配墨字)。令牌定义在 `apps/web/styles/globals.css`。
- **主题**:`lib/theme-presets.ts` 登记全部预设(深知、极致黑白、青绿、墨蓝青绿、深知绿及多套扩展预设)与自定义主题;`app/layout.tsx` 内联脚本首屏确定主题(`?theme=` > localStorage `shenzhi-theme-preset` / `shenzhi-theme` > 系统偏好)。说明见 [docs/design/visual-themes.md](docs/design/visual-themes.md)。

---

## 开发规范

协作规则见 [AGENTS.md](AGENTS.md) 及 `apps/web/AGENTS.md`、`apps/backend/AGENTS.md`;Git 流程见 [docs/engineering/git-conventions.md](docs/engineering/git-conventions.md)。

### 命名约定

| 目标 | 约定 | 示例 |
|------|------|------|
| 组件、Hook、工具文件 | kebab-case | `paper-card.tsx`、`use-search-draft.ts` |
| Feature 页面入口 | PascalCase(沿用现有) | `HomePage.tsx`、`SubmitPage.tsx` |
| 组件名 / 类型 | PascalCase | `PaperCard`、`Paper` |
| 函数 / 变量 | camelCase | `getPaperById` |
| 常量 | UPPER_SNAKE_CASE | `FEATURE_AVAILABILITY` |

### 状态管理分层

```text
服务端状态   TanStack Query / Feature hook + clients   → 论文、会话、收藏等,以后端为准
客户端全局   Zustand(按需 persist)                    → 侧栏、主题、本地偏好
组件局部     useState                                 → 输入值、Tab、面板显隐
URL 状态     useSearchParams                          → 检索条件、会话 ID、?theme 调试参数
```

### 颜色使用纪律

- 一律走 `globals.css` 令牌(`bg-card`、`text-ink`、`bg-primary` …),禁止在组件里写死页面结构色;少数语义徽章色必须成对提供 `dark:` 变体。
- 金(`brand-gold`)只作底色 / 图标色并配墨字,不作正文文字色。

### 展示数据

部分 Feature 下的 `data*.ts` 为展示用数据(机构库、专利库、项目页等尚未接真实接口的页面)。接入真实能力时替换为 `clients/` + FastAPI,不新增平行的请求实现。

---

## 验证工具

```bash
cd apps/web
pnpm build && pnpm start -p 3100      # 先起生产服务(动画页截图更稳定)
cd ../..
python tests/visual/shot_pages.py     # 全页面截图
python tests/visual/shot_themes.py    # 日/夜对比截图
python tests/visual/shot_graph.py     # 图谱页日/夜截图
```

依赖本机 Microsoft Edge(headless)与 Node。路径默认按平台取,可用 `EDGE_PATH`、`NODE_BIN` 覆盖;截图输出到系统临时目录,可用 `SHOT_OUT_DIR` 指定。截图时机过早可能捕获到 Framer Motion 入场动画半途,以 SSR HTML 内容为准。
