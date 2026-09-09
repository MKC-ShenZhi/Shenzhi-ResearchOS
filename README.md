# 深知 ShenZhi · Research OS

> 深知是面向人工智能领域学术科研的**专业可信知识智能体服务平台**,提供论文检索、投稿筛选,以及用于 Deep Research 与 Auto Research 的知识智能体服务。
>
> 本目录是其前端工程:`prototype_v1` SVG 原型的正式 React 实现,**9 个页面已全部完成转换**(7 张 SVG + 2 个知识图谱页),并落地了品牌体系与日/夜模式。

---

## 快速开始

```bash
cd apps/web
pnpm install        # pnpm 11:构建脚本白名单见 pnpm-workspace.yaml(sharp)
pnpm dev            # 开发(--turbopack)
pnpm typecheck      # TypeScript
pnpm lint           # ESLint
pnpm test           # 认证、配置与 Chat 协议测试
pnpm build          # 生产构建
pnpm start          # 启动生产服务
```

AI 生成（可选，问 AI 需要）:

```bash
cd apps/backend
uv sync
cp .env.example .env  # 在 .env 配置模型和可选搜索 Key
uv run uvicorn app.main:app --env-file .env --reload --port 8000
```

Web 环境变量 `BUSINESS_BACKEND_URL=http://127.0.0.1:8000`（仅服务端）。项目介绍见 [docs/dev/项目介绍.md](docs/dev/项目介绍.md)，进度见 [docs/dev/开发日志.md](docs/dev/开发日志.md)。

> 新人入门请先看 [ONBOARDING.md](ONBOARDING.md)。

打开 http://localhost:3000 。URL 加 `?theme=dark` / `?theme=light` 可强制日/夜模式(用于调试与分享)。

> **Turbopack 恢复说明**:本副本运行于 WSL2,dev/build 均使用 `--turbopack`(见 package.json)。Windows 侧曾因智能应用控制拦截 Turbopack 原生二进制而临时改用 `--webpack`,该问题仅存在于 Windows 环境,当前副本不受影响。

---

## 部署(Vercel,当前线上 ✅)

> 本节面向系统平台与测试人员,配置与限制务必通读。改任何部署相关配置前请先同步本文档。

### 架构总览

```
浏览器
  │  (仅访问同源 Next.js BFF /api/v1,不直接接触后端)
  ▼
shenzhi.vercel.app ──── Vercel 项目 shenzhi (apps/web, Next.js)
  │  服务端携带 x-shenzhi-bff-secret 调用
  ▼
shenzhi-backend.vercel.app ──── Vercel 项目 shenzhi-backend (apps/backend, FastAPI Serverless)
  │
  ▼
Vercel Postgres (Neon):Auth 表 + Chat 表共存于 neondb 库
```

| Vercel 项目 | 根目录 | 生产域名 | 说明 |
|------|------|------|------|
| `shenzhi` | `apps/web` | https://shenzhi.vercel.app | Next.js 前端 + BFF |
| `shenzhi-backend` | `apps/backend` | https://shenzhi-backend.vercel.app | FastAPI,以单个 Python Serverless Function 运行(`apps/backend/api/index.py` 导出 ASGI app,`apps/backend/vercel.json` 将全部路径 rewrite 至该函数,`maxDuration=300`) |

### 分支与部署映射(当前阶段)

| Git 分支 | 部署级别 | 访问入口 |
|------|------|------|
| `dev` | **生产**(Production Branch 当前设为 `dev`,条件成熟后切回 `main`) | `shenzhi.vercel.app` / `shenzhi-backend.vercel.app` |
| `feat/*` 等 | 预览(Preview) | `shenzhi-git-<分支名>-hakrin-devs-projects.vercel.app`(分支别名,随该分支最新部署移动) |
| 任意单次部署 | 固定快照 | `shenzhi-<哈希>-hakrin-devs-projects.vercel.app`(不可变,用于定位历史版本) |

- 部署触发:push 到 GitHub 自动构建;另为两个项目的 `dev` 分支配置了 **Deploy Hook**(URL 见各项目 Settings → Git → Deploy Hooks),供 CI 或外部系统 POST 触发。
- 预览环境已关闭 Deployment Protection,预览 URL 无需登录 Vercel 即可访问。
- 后端构建使用 Vercel 原生 uv 支持:依据 `apps/backend/uv.lock` 安装依赖、`.python-version` 选定 Python 3.12,**不要**另行添加 `requirements.txt`。

### 环境变量规则(严格遵守)

1. 变量清单与含义以 [apps/web/.env.example](apps/web/.env.example) 与 [apps/backend/.env.example](apps/backend/.env.example) 为准,真实值一律注入 Vercel(Settings → Environment Variables),**绝不入库**。
2. 勾选规则:除 `BETTER_AUTH_URL`、`BUSINESS_BACKEND_URL` 按环境拆值(Production 与 Preview 各一条)外,**所有变量必须同时勾选 Production + Preview**,否则预览环境会出现“功能缺失型”故障(如邮件未配置、知识底座不可用)。
3. 修改变量后**必须 Redeploy 才生效**;`NEXT_PUBLIC_` 前缀变量在构建期内联,仅重新部署前端项目。
4. 数据库连接串给后端(`CHAT_DATABASE_URL`)时,Neon 原始串中的 `channel_binding=require&sslmode=require` 必须改写为 `?ssl=require`(asyncpg 不识别原参数,运行时会直接抛错)。
5. `BACKEND_BFF_SECRET` 两端必须一致;`BACKEND_ALLOW_INSECURE_LOCAL_BFF` 仅限本机 loopback 联调,线上永不开启。

### 限制与已知事项(测试必读)

1. **Serverless 形态**:FastAPI 的 `lifespan` 在 Serverless 下不保证执行;其唯一副作用是中断中的流式消息不会被标记为 failed,不影响会话读写。函数单次执行上限 300s,后端模型调用超时 `AI_TIMEOUT_SEC=90`,流式长回答不会触顶;冷启动首请求略慢属正常。
2. **会话与附件**:`CHAT_DATABASE_URL` 必须配置,缺失时会话退化为函数内存态,多实例下随机丢失(接口会返回 `ephemeral: true`,可作为测试探针:`GET /api/v1/chat/sessions` 带 `x-shenzhi-bff-secret` 与 `x-shenzhi-anonymous-id` 头)。上传附件的解析结果当前仍存内存,跨实例可能取不到,属已知限制。
3. **知识底座可达性**:`KNOWLEDGE_BASE_API_URL` 必须是**公网可达**地址(Vercel 函数位于美国机房);国内服务需确认安全组未按来源 IP 拦截。上游不可用时接口显式报错(“知识底座暂不可用”),不会返回 mock 数据。
4. **数据库分支陷阱**:已断开 `shenzhi` 项目与 Neon 集成的连接并改用手动 `DATABASE_URL`。**不要重新连接该集成**,其“预览分支”功能会向预览部署注入独立数据库分支(无迁移后的表),表现为 `relation "verification" does not exist`。
5. **国内网络访问**:`*.vercel.app` 域名在国内存在 DNS 污染与阻断,测试人员需自备可访问外网的网络环境;`api.vercel.com`(CLI/管理接口)国内可直连。
6. **邮件/OAuth 回调**:`AUTH_EMAIL_FROM` 必须在阿里云 DirectMail 完成验证;GitHub OAuth App 的回调地址须与当前访问域名匹配(生产 `https://shenzhi.vercel.app/api/auth/callback/github`)。

### 回滚与故障处置

- 回滚:对历史健康部署执行 `vercel promote <部署URL>`(需 Vercel CLI 登录),约 10 秒切换生产指向,零停机。
- 后端健康探针:`GET https://shenzhi-backend.vercel.app/health` 返回 `{"status":"ok"}`。
- 日志:Vercel 项目 → Logs(需账号权限),或 CLI `vercel logs <部署URL> [--follow]`。

### ECS/Docker 备用链路

`infra/` 保留阿里云 ECS + GHCR + Watchtower 的传统部署方案,当前不在使用;若 FastAPI 后续迁回国内长驻服务(解决知识底座连通性与 Serverless 限制),按 [infra/README.md](infra/README.md) 恢复。

---

## 页面路由(已实现 ✅)

| 路由 | 页面 | 对应原型 | 实现位置 |
|------|------|----------|----------|
| `/` | 主发现页(搜索 + Feed 流) | 深知-主发现页.svg | [HomePage.tsx](apps/web/features/home/HomePage.tsx) |
| `/submit` | 投稿详情页(期刊/会议 + 倒计时) | 深知-投稿详情页.svg | [SubmitPage.tsx](apps/web/features/submit/SubmitPage.tsx) |
| `/papers/[id]` | 论文详情页(沉浸式阅读器) | 深知-论文详情页.svg | [PaperDetailPage.tsx](apps/web/features/papers/[id]/PaperDetailPage.tsx) |
| `/scholars` | 学者画像(检索/排序/关注) | 深知-学者画像页.svg | [page.tsx](apps/web/app/scholars/page.tsx) |
| `/scholars/[id]` | 学者详情(引用图表/发表列表) | 深知-学者详情页.svg | [ScholarDetailPage.tsx](apps/web/features/scholars/[id]/ScholarDetailPage.tsx) |
| `/knowledge` | 知识库(文献库 + 在读表格) | 深知-知识库页面.svg | [KnowledgePage.tsx](apps/web/features/knowledge/KnowledgePage.tsx) |
| `/knowledge/search` | 知识库论文检索(Simple Search) | — | [KnowledgeSearchPage.tsx](apps/web/features/knowledge/search/KnowledgeSearchPage.tsx) |
| `/papers/[id]/graph` | 公域知识图谱(引用关系三栏页) | 知识图谱样页.png | [PaperGraphPage.tsx](apps/web/features/papers/[id]/graph/PaperGraphPage.tsx) |
| `/knowledge/graph` | 私域知识图谱(发表×收藏分层双色) | 知识图谱样页.png | [KnowledgeGraphPage.tsx](apps/web/features/knowledge/graph/KnowledgeGraphPage.tsx) |
| `/agents` | AI 研究助手(深度研究对话) | 深知-AI研究助手.svg | [ChatPage.tsx](apps/web/features/chat/ChatPage.tsx) |
| `/agents/ask` | AI 研究助手(URL 会话入口) | — | [AskPage.tsx](apps/web/features/chat/ask/AskPage.tsx) |
| `/search` | 旧搜索地址兼容重定向 | — | [page.tsx](apps/web/app/search/page.tsx) |

导航联动与 `prototype_v1.html` 热区一致:简单搜索 → `/knowledge/search`;智能搜索 → `/agents/ask`;论文卡片 → `/papers/[id]`;作者/学者 → `/scholars/[id]`。

---

Chat 已统一为 `features/chat → clients/backend → /api/v1 BFF → FastAPI`；`/agents` 与 `/agents/ask` 共用实现。
简单搜索是论文检索入口，直接进入 `/knowledge/search` 的 Knowledge Search，不创建 Chat 会话或调用模型；智能搜索才进入 `/agents/ask` 的 Knowledge2Chat。
当前 Session 为单进程临时内存数据，不绑定新的账号体系。架构、SSE、配置与边界见 [docs/chat/README.md](docs/chat/README.md)。

Knowledge Base 是外部 Research Capability，FastAPI 后端统一通过
`apps/backend/app/integrations/knowledge/` 接入。当前只承诺 Search、Paper Detail、
Paper Graph 三项能力，不表述为完整知识底座已接入，也不在本轮接入 Chat Tool。

## 技术栈(当前实际)

| 类别 | 技术 | 状态 |
|------|------|------|
| 框架 | Next.js 16(App Router)+ React 19 + TypeScript | ✅ |
| 样式 | Tailwind CSS 4(CSS-first `@theme`)+ tw-animate-css | ✅ |
| 组件 | 手写 shadcn 风格 UI 原语(cva 变体) | ✅ |
| 服务端数据 | TanStack Query v5(含 placeholderData) | ✅(mock 数据) |
| 客户端状态 | Zustand v5 + persist(点赞/收藏/关注) | ✅ |
| 表单 | Zod(搜索校验 schema,当前尚未接入表单组件) | 🟡 |
| 动效 | Framer Motion(入场动画) | ✅ |
| 图标 | Lucide React | ✅ |
| 包管理 | pnpm 11 | ✅ |
| 认证与数据 | Better Auth 1.6.28 + PostgreSQL (`pg`) | ✅ 已接入并上线(Vercel + Neon Postgres) |
| 编辑器 / 可视化 / 测试 | TipTap、D3.js、Node.js `node:test`(认证/配置) | 🟡 业务数据层与浏览器测试仍待接入 |

## 目录结构(实际)

```
shenzhi/
├── apps/
│   ├── web/                  # Next.js Web；app 为薄路由，features 为页面实现
│   └── backend/              # FastAPI：Chat / 检索 / Knowledge Capability / 模型流 / 搜索 / 附件解析
├── infra/                    # Dockerfile、Compose 与部署文档
├── tests/visual/             # 页面、主题与图谱截图验证脚本
├── tools/brand/              # 品牌资源处理工具
├── docs/                     # PRD、开发文档、设计材料与原型
├── .github/workflows/        # deploy.yml:构建 Web 镜像并推送 GHCR
└── README.md
```

## 品牌与设计令牌

- **标识**:用户书法定稿「深知」日/夜双版(白字黑底 / 黑字白底),成品直用;随主题 CSS 切换,无 JS 闪烁。运行时资产位于 `apps/web/public/brand/`,资产管线见 `tools/brand/process_logo.py`。
- **配色「深识」体系**:主色深识蓝 `#002FA7`(夜间调浅 `#5B84F1`);辅助灵犀紫 / 探索青 / 桂冠金 `#f3d029`(金底一律配墨字)。
- **日/夜模式**:`apps/web/styles/globals.css` 用 `.dark` 块重定义同名令牌,组件零改动;`layout.tsx` 内联脚本首屏定主题(`?theme=` > localStorage `shenzhi-theme` > 系统偏好);切换按钮在侧边栏 Logo 右侧与移动端顶栏。
- 完整规范:见本地 `docs/superpowers/specs/`(仅本地工作文档,不入库)

---

## 开发规范

### 命名约定

| 目标 | 约定 | 示例 |
|------|------|------|
| 文件名 | kebab-case | `paper-card.tsx`、`use-debounce.ts` |
| 组件名 | PascalCase | `PaperCard`、`SearchHero` |
| 函数/变量 | camelCase | `getPaperById` |
| 类型/接口 | PascalCase | `Paper`、`Scholar` |
| 常量 | UPPER_SNAKE_CASE | `SITE`、`LEVEL_CHIPS` |
| 动态路由 | 方括号 | `[id]` |

### 状态管理分层

```
服务端状态   TanStack Query   → 论文列表等；Chat 使用 Feature hook + Backend Client
客户端全局   Zustand persist  → 点赞/收藏/关注等用户偏好
组件局部     useState         → 输入值、Tab 切换、面板显隐
URL 状态     useSearchParams  → 搜索关键词、筛选条件、?theme 调试参数
```

### 颜色使用纪律

- 一律走 `globals.css` 令牌(`bg-card`、`text-ink`、`bg-primary` …),**禁止在组件里写死页面结构色**;少数语义徽章色(琥珀/绿/紫)必须成对提供 `dark:` 变体。
- 金(`brand-gold`)只作底色/图标色并配墨字,不作正文文字色(明度高,可读性差)。

### 数据约定

- `apps/web/lib/data/*.ts` 的内容逐字提取自 SVG 原型,属展示用 mock;接真实后端时替换为 `apps/web/clients/backend/` + FastAPI,组件接口保持不变。

---

## 验证工具

```bash
cd apps/web
pnpm build && pnpm start -p 3100      # 先起生产服务(动画页截图更稳定)
cd ../..
python tests/visual/shot_pages.py      # 全页面截图 → %TEMP%(f_home / f_submit / f_paper / f_scholars / f_scholar_detail / f_knowledge / f_agents)
python tests/visual/shot_themes.py     # 日/夜对比截图 → %TEMP%(theme-*-day/night.png)
python tests/visual/shot_graph.py      # 知识图谱页日/夜截图
```

依赖本机 Edge headless;截图时机过早可能捕获到 Framer Motion 入场动画半途(伪影,非缺陷),以 SSR HTML 内容为准。

## 与原型的关系

| 维度 | prototype_v0 / v1 | apps/web |
|------|-------------------|-------------|
| 定位 | 原型探索 | 工程化前端(当前开发基准) |
| 页面 | 7 张 SVG + HTML 热区 | 9 路由完整覆盖(7 SVG + 2 图谱页),热区已转为真实导航 |
| 数据 | 静态 | mock(逐字提取)→ 规划 Server Actions + DB |
| 状态 | 无 | TanStack Query + Zustand persist + URL state |
| 主题 | 无 | 日/夜双模式 + 品牌令牌 |
