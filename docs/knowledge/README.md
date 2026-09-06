# 知识底座接入说明

本文说明 ShenZhi Knowledge MVP（论文搜索、论文详情、论文关系图谱）的
工程边界、运行配置和稳定契约。科研组 Knowledge Base 是外部 Capability：
ShenZhi 只调用、隔离并适配，不修改其内部实现。

## 调用链

```text
Browser
  ↓ same-origin
Next.js /api/v1/*（BFF）
  ↓ server-side forwarding + Better Auth/BFF credential
FastAPI /api/v1/knowledge/*
  ↓
services/knowledge.py
  ↓
integrations/knowledge（client / schemas / adapter / exceptions）
  ↓
External Knowledge Base
```

浏览器只能访问同源 Next.js BFF，不能直接请求 FastAPI 或外部知识库。
外部知识库地址只允许存在 Backend 服务端配置中。

## 代码边界

### Web

| 路径 | 职责 |
|---|---|
| `apps/web/clients/knowledge/types.ts` | Search / Detail / Graph / Error 的前端 wire type |
| `apps/web/clients/knowledge/client.ts` | `KnowledgeClient` 与 `KnowledgeClientError` |
| `apps/web/clients/knowledge/bff.ts` | 调用同源 `/api/v1/knowledge/*`，解析正式错误契约 |
| `apps/web/clients/knowledge/mock.ts` | 显式开发、测试和 demo fixture 使用的 Mock Client |
| `apps/web/clients/knowledge/index.ts` | Client 工厂；默认 BFF，显式 `source=mock` 才启用 Mock |
| `apps/web/features/knowledge/retry.ts` | Knowledge 查询的局部 retry predicate |
| `apps/web/features/knowledge/{search,paper,graph}` | 页面、交互和展示逻辑 |

### Backend

| 路径 | 职责 |
|---|---|
| `apps/backend/app/api/knowledge.py` | `/api/v1/knowledge/*` HTTP 边界、鉴权和错误状态 |
| `apps/backend/app/services/knowledge.py` | Knowledge 业务服务边界 |
| `apps/backend/app/integrations/knowledge/client.py` | 外部 HTTP、timeout 和外部异常映射 |
| `apps/backend/app/integrations/knowledge/schemas.py` | 外部 Knowledge Base transport schema |
| `apps/backend/app/integrations/knowledge/adapter.py` | 外部 snake_case/异构字段到 ShenZhi 契约的适配与 normalization |
| `apps/backend/app/integrations/knowledge/exceptions.py` | 集成异常与正式错误类别 |

Backend 不提供自动 Mock fallback。未配置或不可用的外部 Knowledge Base
会返回真实的 `UPSTREAM_UNAVAILABLE` / `TIMEOUT` 等错误。

## 配置

Web（`apps/web/.env.example`）：

```dotenv
# 默认/正式运行使用 BFF；仅显式开发、测试或 demo 时使用 mock。
NEXT_PUBLIC_KNOWLEDGE_SOURCE=bff
```

`NEXT_PUBLIC_KNOWLEDGE_SOURCE=mock` 才启用 `MockKnowledgeClient`；未配置或
其他值都使用 BFF。BFF 请求失败时不会切换到 Mock。

Backend（`apps/backend/.env.example`）：

```dotenv
KNOWLEDGE_BASE_API_URL=
KNOWLEDGE_BASE_TIMEOUT_SEC=30
```

`KNOWLEDGE_BASE_API_URL` 和 Backend 的 BFF secret 只能注入服务端环境，不能
使用 `NEXT_PUBLIC_` 前缀，也不能出现在浏览器 Network 请求中。

## HTTP API

| 能力 | ShenZhi API | 外部 API |
|---|---|---|
| 论文检索 | `POST /api/v1/knowledge/search` | `POST /api/retrieval/search` |
| 论文详情 | `GET /api/v1/knowledge/paper?paperId=...` | `GET /api/kg/paper?paperId=...` |
| 论文图谱 | `GET /api/v1/knowledge/graph?paperId=...&depth=1\|2` | `GET /api/kg/graph?paperId=...&depth=1\|2` |

Search 请求使用 `query`、`topK`、`yearFrom`、`yearTo`、`venue`、`author`、
`keyword`、`subject`。Backend 只在 adapter 边界把它们映射为外部 API 所需的
字段（例如 `top_k`、`year_gte`、`conference`）。

图谱 `depth` 只支持 `1 | 2`，默认值为 `1`。Backend 可以返回异构节点和边；
前端保持 `kind`、`relation` 为开放字符串，未知值使用默认展示。

## 稳定契约

- `id`、`paperId`、`rootId` 都是 opaque string，禁止按 `paper:`、`AAAI:` 等
  内部格式解析。
- `Search result id === Detail request paperId === Graph request paperId === Graph.rootId`。
- `abstract`、`venue`、`year` 可为 `null`；`authors`、`keywords`、`subjects`
  缺省为空数组。
- `citationCount`、`referenceCount` 为 `null` 表示外部未提供，不能静默转成 `0`。
- 外部数字字段允许 number 或 numeric string：`"2021" → 2021`、`"42" → 42`、
  `"0.87" → 0.87`；空字符串变为 `null`，非法数字、非有限值和非法 integer
  变为 `CONTRACT_VIOLATION`。
- Graph `CITES` 统一表示 `sourceId` 引用了 `targetId`：
  `sourceId === rootId` 是 References，`targetId === rootId` 是 Citations。
- Graph 顶层保留 `provenance`；节点和边的 `kind` / `relation` 不因未知值抛错。

### Error Contract

Knowledge API 错误响应使用字符串 code，不使用历史数字错误码：

```json
{
  "code": "NOT_FOUND",
  "message": "safe user-facing message",
  "retryable": false,
  "requestId": "request-id-or-null"
}
```

允许的 code 为 `NOT_FOUND`、`INVALID_ARGUMENT`、`RATE_LIMITED`、
`UPSTREAM_UNAVAILABLE`、`TIMEOUT`、`CONTRACT_VIOLATION`、`UNKNOWN`。
`message` 必须是安全的用户可见信息，不得包含外部 URL、traceback 或 secret。

Knowledge 查询最多自动重试一次；`TIMEOUT`、`RATE_LIMITED`、
`UPSTREAM_UNAVAILABLE` 只有在 `retryable=true` 时重试。`NOT_FOUND`、
`INVALID_ARGUMENT`、`CONTRACT_VIOLATION` 在正式契约中不可重试；`UNKNOWN`
也必须遵守 `retryable` 和最多一次的上限，不能无限重试。

## 页面范围

| 路由 | 行为 |
|---|---|
| `/knowledge/search` | 论文搜索、筛选、loading、zero-result、error |
| `/papers/[id]` | 统一论文详情与 PDF 阅读器；通过 Knowledge Client 加载真实详情 |
| `/papers/[id]/graph` | fullGraph（保留异构节点/边）、References/Citations 筛选、节点详情 |
| `/knowledge/search/[paperId]` | 旧链接兼容跳转到 `/papers/[id]`，保留合法 `returnTo` |
| `/knowledge/search/[paperId]/graph` | 旧图谱链接兼容跳转到 `/papers/[id]/graph`，保留合法 `returnTo` |

当前 Knowledge MVP 打通 Search → 统一 Paper Detail → Graph，并由 Chat Core 复用
Search Capability 完成 Knowledge → Chat。论文详情页的 Assistant 通过 `paper`
attachment 显式绑定当前 `paperId`，由 Backend 重新读取对应论文详情，并仅使用
title、authors、venue、year、abstract 等元信息回答；该流程不使用全局 Search
猜测“这篇论文”，也不读取 PDF 全文。

暂不包含
multistep、会议浏览、ID resolver、scholar、patents、projects、funds、
Deep Research 或 Auto Research。

## Mock 规则

Mock 只由 `NEXT_PUBLIC_KNOWLEDGE_SOURCE=mock` 显式启用，适用于 unit test、
component test 和 demo fixture。真实 BFF 请求失败、Backend 未配置 upstream
或 upstream 不可用时，都保持真实错误状态，不自动返回 Mock 数据。
