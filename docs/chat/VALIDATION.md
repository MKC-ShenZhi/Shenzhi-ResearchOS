# Chat 迁移验收

验证基线：`dev=522cad0`，`recovery/ai-agent-B=f3354e6`，共同祖先 `2bec337`。
在工作分支 `feat/chat-architecture-integration` 完成；不修改 dev、不 merge、不 push。

## 可重复执行的检查

| 目录 | 命令 | 结果 |
| --- | --- | --- |
| `apps/web` | `pnpm install --frozen-lockfile` | 通过，必要新依赖已先安装并更新 lock |
| `apps/web` | `pnpm typecheck` | 通过 |
| `apps/web` | `pnpm lint` | 0 error；1 条 dev 已有 warning：`lib/use-popover-placement.ts:37` 的 `anchorRef` 依赖 |
| `apps/web` | `pnpm test` | 47 通过，0 失败，0 跳过 |
| `apps/web` | `pnpm build` | 通过，27 个静态页面；保留原 `/agents` 系列 URL |
| `apps/web` | `pnpm why @prisma/client better-sqlite3` | 成功、无依赖关系输出 |
| `apps/backend` | `python -m compileall app` | 通过 |
| `apps/backend` | `python -c 'from app.main import app; print(app.title)'` | 成功导入 FastAPI 应用 |
| `apps/backend` | `python -m unittest discover -s tests -v` | 16 通过 |
| 仓库根目录 | `git diff --check` | 通过 |

Backend 使用 `/tmp/shenzhi-backend-venv` 的 Python 3.14.7，已安装 `requirements.txt`。Web 使用 pnpm 11.22.0。
首次 Turbopack 构建因执行沙箱不允许监听端口而失败，获得权限后重新执行并通过；依赖安装也在必要时申请了网络/包缓存权限。
Auth 负向测试预期打印 `delivery failed`，坏 PDF 负向测试预期打印解析诊断，均不是测试失败。

### 新增覆盖范围

- Web：SSE CRLF、多行、UTF-8 与尾块解析；reasoning 分发和提前断流；HTTP 状态/业务错误一致性；历史消息适配。
- Backend：Provider streaming/reasoning、缺失 Key、供应商错误/提前 EOF、取消与 followups；Tavily 超时→SearXNG fallback 与 news/general。
- Backend：PDF/TXT/Markdown、坏文件/不支持类型/大小限制、截断、附件归属；multipart 超过 1MiB 仍不使用磁盘 spool。
- Backend：会话 CRUD/收藏/历史、owner 隔离、多轮、事件重放不重复生成、停止/续写/断连、容量限制、上下文截断告警。
- BFF/Auth：生产默认要求内部 Secret；只有显式 loopback 本地模式可无 Secret；空 Better Auth Session 与鉴权异常分开处理。
- API 边界：Chat 配置/会话/SSE 使用 `/api/v1/chat/*`，论文搜索使用 `/api/v1/knowledge/search`。

## 浏览器与实际 HTTP 链路

使用临时本地 OpenAI-compatible / Knowledge Base / SearXNG fixture，经过真实 Web BFF、FastAPI、HTTP SSE 和浏览器 UI 验证；fixture 位于 `/tmp`，没有进入仓库或正式运行时代码。

已检查：

- `/agents` 发问、阶段状态、reasoning、多轮追问、耗时、Markdown 表格/代码/KaTeX、引用定位和真实来源卡片。
- 慢速流 Stop 保留部分回答，Resume 在同一消息追加；切换历史后仍显示完整续写结果。
- 两份合成附件在一次选择中同时保留、成功随问题提交。
- `/agents/ask?q=...&mode=deep&web_search=1` 自动发送一次、合并论文与网页来源。
- 模型选择、四种回答模式可操作，收藏状态可恢复。
- 上游 429 显示标准化错误及继续生成入口，不显示供应商原始错误体。
- 独立 HTTP 客户端在同一来源地址仍隔离匿名会话；伪造身份/内部凭据头不能访问另一客户端会话；直接访问 Backend 使用错误共享凭据返回 401。删除行为由 API 测试验证。

**没有验证付费 Provider 的在线可用性、真实 Tavily 账号、生产 PostgreSQL/Auth 登录或部署环境。** 本次不使用真实用户数据，不声称 fixture 是供应商联调。部署后需使用正式环境配置执行小规模在线验收。

## 静态边界与回归

- 正式源码无 `next-auth`、`@prisma/client`、`better-sqlite3`、`NEXT_PUBLIC_AI_BACKEND_MODE`、`/api/ai/chat`、`/api/web-search`；这些旧名字只用于迁移说明，Prisma/SQLite 在 lock 中仅为 Better Auth 可选 peer 元数据。
- 正式源码无旧 `features/agents`、`lib/api`、`services/backend` imports；Chat 外部调用集中于 Backend Client。
- Auth 核心目录、Auth routes、数据库与配置相对 dev 没有变化；Auth 原有测试全部保留并通过。
- 比较迁移前后 pnpm importer，既有直接依赖版本不变；仅增加 Markdown/数学渲染依赖，Backend 增加 pypdf。
- 当前内存仓库仅支持单 worker、重启丢失。持久化/用户关联/公开分享/分布式任务留待下一阶段，见 [维护指南](README.md)。
