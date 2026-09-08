# dev + recovery/ai-agent-B 集成记录

## 基线

- `git fetch origin` 后，dev / origin/dev 均为 `522cad08e96cf72f50bf9b19e87c3b99efb320dd`。
- `git merge-base dev recovery/ai-agent-B` 为 `2bec337153625f92dcba19834ecbee649fc8fd75`。
- B 来源仅 `recovery/ai-agent-B`（`f3354e6`）；按共同祖先两侧差异分析后移植，没有 merge / 整体 cherry-pick。
- 工作分支 `feat/chat-architecture-integration`；未更新 dev，未 push。

## dev 路径迁移

以下 Web 路径均相对 `apps/web`。

| dev 原路径 | 新路径 | 说明 |
| --- | --- | --- |
| `features/agents/AgentsPage.tsx` | `features/chat/ChatPage.tsx` | 保留 `/agents` |
| `features/agents/components` | `features/chat/components` | 保留 dev Composer/模型选择器，增量扩展真实 Chat |
| `features/agents/ask` | `features/chat/ask` | 保留 `/agents/ask`，共用 AgentChat |
| `features/agents/ask/components/ask-stage.tsx` | `features/chat/components/chat-thread.tsx` | 提取消息展示；原 hook 成为统一状态控制 |
| `features/agents/deep-research` | `features/deep-research` | 纯业务边界移动，算法不改 |
| `features/agents/auto-research` | `features/auto-research` | 同上 |
| `features/agents/deep-search` | `features/search/deep-search` | 既有静态搜索结果原型，不再另建一级 Feature |
| `lib/ask/use-ask-session.ts` | `features/chat/hooks/use-chat-session.ts` | 统一状态、历史、取消和续写 |
| `lib/ask/{draft,errors}.ts` | `features/chat/services/` | 首页草稿与错误显示 |
| `lib/api/{http,auth-token,uploads}.ts` | `clients/backend/` | Chat HTTP/SSE 再拆到 `chat.ts` |
| `lib/sse.ts` | `clients/backend/sse.ts` | 单协议、增量 UTF-8/CRLF 解析 |
| `services/backend/{forward.ts,README.md}` | `clients/backend/` | BFF 边界与文档 |
| `components/{layout,graph}` | `components/common/{layout,graph}` | 跨 Feature UI |
| `lib/citations.tsx` | `components/common/citations.tsx` | 保留原静态引用；Chat 双向引用单独放 Feature |
| 旧论文检索代理 | `apps/backend/app/services/knowledge.py` + `integrations/knowledge` | 统一由 Knowledge Capability 提供 |
| `apps/backend/app/main.py` | `api/*`、`schemas/chat.py`、`core/*`、`services/*` | main 只保留应用、生命周期、全局错误、注册 |

第一提交仅 `git mv`（54 文件、零行内容变化），第二提交单独修复 imports 和拆分后端入口。历史可按 `git log --follow` 查看。

## B 能力来源与落点

B 路径相对旧仓库根目录；没有将 B 同名组件覆盖 dev。

| B 来源 | 当前落点 | 迁移内容 |
| --- | --- | --- |
| `components/features/agent/agent-chat.tsx` | `features/chat/components/{agent-chat,chat-thread}.tsx` + hook | 多轮、状态、错误、耗时、推理、复制、继续生成、追问 |
| `components/features/agent/composer.tsx`、`attachment-menu.tsx` | dev Composer 与 AttachmentMenu | 保留 dev 样式和模型选择器，补齐真实上传、批量添加、错误/截断显示 |
| `components/features/agent/session-list.tsx` | `components/common/layout/sidebar-chat-history.tsx` | 侧栏历史列表、切换、删除；DB 走 FastAPI，本地降级见 `local-history` |
| `components/features/agent/reference-grid.tsx`、`lib/citations.tsx` | Chat `reference-grid.tsx`、`citations.tsx` | 真实来源、展开、双向定位；去掉空结果 mock fallback |
| `lib/markdown-content.tsx` | Chat `markdown-content.tsx` | Markdown、表格、代码、KaTeX；不移植会误改代码块的裸 LaTeX 猜测 |
| 旧 Search client | `clients/knowledge` + Knowledge Search Feature | 统一论文搜索产品协议 |
| `lib/ask/draft.ts`、`lib/ask/errors.ts` | Chat `services/{draft,errors}` | 草稿安全读写、匹配、成功后清理；错误保留 Backend 具体原因 |
| `stores/composer.ts` | dev 受控 Composer + Chat hook | 不保留 A/B/C 数据总线；状态/草稿功能由统一链路承载 |
| `app/api/ai/chat/route.ts` | FastAPI `services/model_provider.py` | DashScope/DeepSeek、真实 HTTP SSE、reasoning、取消、标准错误、模型/参数、追问 |
| `lib/chat-prompt.ts` | FastAPI `services/chat.py` | 四种回答模式、服务端历史/附件/来源上下文 |
| `lib/c-server/web-search-client.ts`、`app/api/web-search/route.ts` | FastAPI `services/web_search.py` | Tavily→SearXNG、超时、news/general、来源归一化与告警 |
| `lib/c-server/parse-document.ts`、`app/api/uploads/route.ts` | FastAPI `services/{document_parser,upload_reader}.py`、`api/uploads.py` | PDF/TXT/Markdown、20MB、不落盘、30k/60k、截断 warning |
| B `ChatSession/ChatMessage/Favorite` 概念 | FastAPI `services/sessions.py` + CRUD API | 临时会话仓库；不迁移 SQLite 数据、Prisma schema |

## 没有迁入

- B `auth.ts`、`auth.config.ts`、NextAuth provider/middleware、User / PasswordResetToken、注册登录找回密码、Prisma / SQLite 及其迁移：与正式 Better Auth 边界冲突，原样留在 recovery 分支。
- B session CRUD routes 和前端的 Prisma 用户调用：改用 FastAPI 临时 Repository。
- `SharedSession` 持久化/公开分享、数据库数据迁移：需要用户授权与数据库设计，留后续。
- A/B 双协议、`NEXT_PUBLIC_AI_BACKEND_MODE`、浏览器拼模型 prompt / 调联网供应商：由统一 Backend 服务取代。
- B 全站 README、brand、deploy、Docker、workflow、旧路径删除、无关项目数据：不 replay。保留 dev 品牌、infra、CI、Auth、Knowledge 与研究算法。
- B 的 pdf-parse/pdfjs worker、导出/表单/认证依赖：当前正式 Chat 不需要，不安装。

## 依赖与配置

Web 新增 `react-markdown`、`remark-gfm`、`remark-math`、`rehype-katex`、`katex`；Backend 新增 `pypdf`。没有升级既有直接依赖，没有引入 B ORM/Auth 包。pnpm 自动重算 peer dependency 快照并清理无引用锁条目，Better Auth / Next / React 等既有直接版本保持不变。

新增 Backend `DASHSCOPE_*`、`DEEPSEEK_*`、`AI_ALLOWED_MODELS`、`AI_TIMEOUT_SEC`、`TAVILY_API_KEY`、`SEARXNG_BASE_URL`；两端增加 `BACKEND_BFF_SECRET` 和仅 loopback 本地开发可显式开启的 `BACKEND_ALLOW_INSECURE_LOCAL_BFF`。检索地址改为显式配置，Key 全在 Backend。新增根 `.env.example` 作为两应用配置入口说明。

## 静态验收

| 检查项 | 正式源码 | 说明 |
| --- | --- | --- |
| `next-auth` | 无 | 不迁入第二套 Auth |
| `@prisma/client` | 无 | 锁文件仅有 Better Auth 自身可选 peer 元数据，未安装/导入 |
| `better-sqlite3` | 无 | 同上，Better Auth 可选 peer 元数据不等于 Chat 依赖 |
| `NEXT_PUBLIC_AI_BACKEND_MODE` | 无 | 仅本迁移文档提到历史名字 |
| `/api/ai/chat` | 无正式入口 | 仅本迁移文档记录 B 来源 |
| `/api/web-search` | 无正式入口 | 同上 |

Auth 核心目录、数据库迁移、Auth 路由和配置与 dev 的 diff 为空。仅公共布局的 import 路径随 `components/common` 移动发生变化。

测试与验收结果见 [VALIDATION.md](VALIDATION.md)。未来边界见 [维护指南](README.md#临时-session-与-auth)。
