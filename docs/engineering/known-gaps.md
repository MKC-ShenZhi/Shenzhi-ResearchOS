# 已知偏移与待收敛项

本文登记当前代码与 [工程架构说明](architecture-confirmation.md) 之间已知的偏移、遗留代码与工程缺口，供下一阶段排期。

这里只做记录：普通业务修改不因本文进行无关的大范围重构；在相关模块修改时可顺带收敛，收敛后从本文删除对应条目。

---

## 一、部署与运行形态

| 项 | 现状 | 方向 |
|----|------|------|
| Serverless 与长驻进程设计不匹配 | 后端在 Vercel 上以单个 Serverless 函数运行，而 `lifespan` 恢复与首页调度器、进程内 Agent 运行归属、本地 workspace、900s 的 Agent 运行时限都依赖长驻进程 | 明确正式服务器部署方式；Vercel 定位为开发测试环境。详见 [部署与运行环境](deployment.md) |
| 平台统计快照未调度 | `python -m app.services.stats` 不在进程内调度器中，首页 `trending` 数据源依赖这些快照 | 随部署方式确定定时任务 |
| 无 CI 门禁 | 仓库没有运行 typecheck / lint / test 的 workflow | 增加基础检查 workflow |

## 二、Agent

| 项 | 现状 | 方向 |
|----|------|------|
| 匿名 Agent 会话无保留期 | 维护命令 `python -m app.services.agent_uploads` 只清理过期附件暂存文本，`agent_sessions` 中的匿名会话不会过期删除 | 增加与匿名 Cookie 有效期一致的保留期清理 |
| 沿用 chat 命名的外部状态 | 匿名 Cookie `shenzhi-chat-anon`、环境变量 `CHAT_DATABASE_URL` / `CHAT_ANONYMOUS_TTL_SECONDS` 仍带 chat 前缀；改名会让已有匿名浏览器失去身份或需要同步修改部署配置 | 需要时以“新名优先、旧名兼容”的方式迁移 |
| 账号注销不清理 workspace | `services/user/account_deletion.py` 只删除数据库记录，Agent 会话的本地 workspace 文件不会删除 | 注销时一并清理，或随 workspace 外置统一处理 |

## 三、边界例外

| 项 | 现状 | 方向 |
|----|------|------|
| Web 直连知识底座图片 | `apps/web/app/api/paper-images/` 在 Web 服务端代理 `KNOWLEDGE_BASE_API_URL` 的图片 | 经 FastAPI `integrations/knowledge` 代理，或保留为显式的静态资源例外 |
| Agent 外部调用未经 integrations | `services/agent/provider.py` 是第二套 OpenAI 兼容 Provider；`chart_tools.py` 直接调用 Exa 并 `os.getenv('EXA_API_KEY')`；`read_paper.py` 直接请求 arXiv / OpenReview / Unpaywall（Unpaywall 邮箱写死）；`fetch_url.py` 在 Service 层发起 HTTP | 迁入 `integrations/{llm,web_search,paper_resource}`，配置统一经 `core/config` |
| Router 承载逻辑 | `api/agent.py` 内联请求 Schema 并直接调用 repository；`api/knowledge.py` 在路由内组合 `personal_overview` | 补薄 Service，Schema 移入 `schemas/` |
| BFF 计算业务结果 | `apps/web/app/api/identity/anonymous-claim/route.ts` 的 GET 读取匿名身份的 Agent 会话列表并在 Next 中计算数量 | 后端提供预览接口，BFF 只转发 |
| 全局层反向依赖 Feature | `components/common/**`、`stores/collections.ts`、`providers/interaction-sync.tsx` 引用 `features/*`，如 `sidebar-chat-history.tsx`、`components/auth/anonymous-claim-coordinator.tsx` → `features/agent-chat`、`composer/attachment-menu.tsx` → `features/knowledge` 示例数据 | 尽力收敛：共享部分迁到 `components/common`、`lib` 或 `stores` |
| 论文互动组件跨 Feature 共用 | 收藏选择、点赞、收藏数、已读标记被 papers、search、knowledge、graph 共用，目前位于 `features/knowledge` | 提升为公共论文组件 |

## 四、展示数据与遗留代码

| 项 | 现状 | 方向 |
|----|------|------|
| 正式页面使用展示数据 | `/agents` Composer 的引用菜单（`components/common/composer/attachment-menu.tsx`）列出 `features/knowledge/data-*.ts` 与 `features/projects/data.ts` 的展示数据；`/knowledge/institutions`、学者关系网络、侧栏项目列表同样使用展示数据，未经 `feature-availability` 拦截 | 接入真实数据或标记为未上线 |
| 无引用代码 | `features/scholars/`（学者页已重定向到 `/knowledge/scholars`）、`features/knowledge/data-library.ts` | 删除 |
| Mock 数据进入客户端 bundle | `clients/knowledge/index.ts`（`"use client"`）静态导入 `mock.ts` → `mock-data.ts`（约 5900 行），仅 `NEXT_PUBLIC_KNOWLEDGE_SOURCE=mock` 时使用 | 改为动态导入或移入测试 fixture |
| 截图脚本目标过时 | `tests/visual/shot_pages.py`、`shot_themes.py` 仍截取已重定向的 `/scholars` 路径 | 更新为 `/knowledge/scholars` |

## 五、命名与体量

| 项 | 现状 | 方向 |
|----|------|------|
| `features/search` 命名 | 实际承载首页论文 Feed（见 [V1 模块](V1-modules.md)） | 可考虑更名为 `features/discovery` |
| 首页 Feed 相关模块分散 | `services/discovery.py`、`home_feed/`、`discovery_pool/`、`recommendation/` | 可将 `discovery.py` 并入 `home_feed/` |
| 大文件 | Web：`components/auth/login-modal.tsx`（约 1270 行，逻辑位于 components 而非 Feature）、`features/agent-chat/shenzhi-ai-page.tsx`（约 920 行）；Backend：`integrations/knowledge/adapter.py`（约 920 行）、`services/agent/runtime.py`（约 800 行） | 修改相关模块时按职责拆分 |
