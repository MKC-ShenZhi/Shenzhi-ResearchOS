# ShenZhi 日志与异常 · 综合实现方案（V1 待审批）

本文是 Logging Core 与 Chat 报错处理的唯一实现基线。  
大方向、分层、**两个边界**、阶段、禁止项只看第 1～6 节。字段、事件名、文件清单、测试在第 7 节以后。  
两人怎么拆任务见 [分工.md](./分工.md)。

Chat 业务说明仍以 `docs/chat/` 为准。本文不改回答流程、认领、持久化和错误码语义。

P1–P4 已合入 `dev`（PR #4、#10）。不要平行新建 Core，不要重写已合入的 `chat.py` / 错误气泡。走查见 [../chat/BROWSER-WALKTHROUGH.md](../chat/BROWSER-WALKTHROUGH.md)。分工见 [分工.md](./分工.md)。

---

## 1. 目标

系统出 Bug 时，能拿到一个 `request_id`，沿 Next.js BFF → FastAPI →（按需）Knowledge / LLM / Search / Chat 流，回答四件事：哪一层、什么错、耗时多少、未知异常的真实 traceback。

Chat 多请求（创建、SSE、Stop、Resume）用已有 `session_id` / `message_id` 旁路关联，不在 V1 强制上浏览器 `trace_id`。

**不是：** 监控平台、业务异常框架、重试/降级中枢。不引入 ELK、Grafana、Sentry、OpenTelemetry。

---

## 2. 原则（全局，必须遵守）

1. **Logging Core 不理解业务。** 不维护事件枚举，不依赖 Chat / Knowledge 类型。
2. **只观察，不决定。** 不改 retry、fallback、HTTP status、业务码、状态机、返回值。
3. **普通能力自动有，业务事件按需补。** 新 API 不写日志，也必须有 `request_id`、HTTP 状态与耗时、未知异常 traceback。
4. **禁止再造。** 新业务不得自建 logger、request-id、异常中间件。
5. **业务与异常出口分离。** 已知错误继续抛原有类型；未知 traceback 只在最终边界打一次。
6. **可观测失败不得挡业务。** 打日志失败则丢弃，不重试占事件循环。
7. **敏感数据 allowlist。** 只记明确允许的字段，禁止 dump header / body / prompt / 全文。

---

## 3. 两个必须守住的边界

后面无论谁改代码，先看自己落在哪一条。看一眼就能判断该不该写 `try`。

语法（没有「default」）：

- Python：`try` / `except` / `else` / `finally`。兜底是 `except Exception`，收尾用 `finally`。
- TypeScript：`try` / `catch` / `finally`。前端业务页尽量少捕；网络失败集中在 BFF / `clients/backend`。

金规则：catch 之后若什么也不改、只打日志再 `raise`，就不要 catch，交给全局边界。

### 边界一：普通 HTTP —— 不要为了打日志去 catch

认可并维护：未知异常自然冒泡，只在最终边界记一份 traceback。

```text
Browser → BFF → FastAPI 路由 → Service
                    异常往上走
                         ▼
              main.py 全局 Exception handler
              （或 BFF 转发失败那一处）
              打一次日志 + 安全 500/503
```

普通 HTTP 在响应发出前失败，框架还能接住并返回安全 500。

**禁止（无价值）：**

```python
try:
    ...
except Exception:
    logger.exception(...)
    raise
```

client / service / api / middleware 禁止对同一未知异常各打一遍堆栈。

**业务代码应保持：**

```python
async def create_xxx():
    result = await do_something()
    return result
```

### 边界二：这里必须自己 try / except，且允许写完备

最小侵入 **不禁止** 必要的捕获。下列位置优先保证异常处理够用。Logging 只旁路记录，**不得**改 retry、fallback、HTTP status、状态机、返回值。

**（1）外部服务边界**（通常要 catch）  
落点：Knowledge Client、LLM Provider、Web Search、Database Repository。  
要接住：超时、HTTP 500/401、返回格式错误、网络断开。

四件事：译成内部可理解的错误；旁路记录 `provider` / `status` / `duration`；执行**原有** fallback；第三方 SDK 异常类型不准漏进业务层。  
有没有 catch 不重要，重要的是 catch 出现在正确边界。

**（2）Chat Streaming**（必须自己 try / except / finally）  
普通 HTTP：异常 → FastAPI handler 还能接住。  
Chat：`GET /stream` 已发出 HTTP 200，`StreamingResponse` 已建立，后台 `generate()` 再失败，**不能再改成 HTTP 500**。

现有 `generate` 里 CancelledError → `stopped`、BusinessError → `failed`+`error`、未知 Exception → 一份 traceback + `failed`、`finally` 发 `done`，是必要的业务生命周期边界，不是过度侵入。P3 只把终态日志收成结构化事件，**不删这套 except，不新套一层**。

**（3）有业务意义的决策**才在业务函数里 catch：降级、补偿、释放资源、改状态、fallback、转换第三方错误、保证最终事件。

```python
# 有业务意义：知识库不可用则空列表，继续回答
except KnowledgeUnavailable:
    papers = []

# persist 失败由 Chat / Repository 决定 Message 终态，不能交给 Logging Core
try:
    await persist(...)
except DatabaseError:
    ...  # 按业务语义处理 message
```

一眼看进度：

| 你在文件里看到 | 阶段 |
| --- | --- |
| `lib/observability` + `core/logging.py` + `request_context.py` | P1 |
| knowledge / model_provider / web_search 出口有 completed/failed 一行 | P2 |
| `chat.py` 的 `generate` 仍是上述 except，且有 `chat.stream.*` | P3 |
| 错误 UI 能复制 `request_id` | P4 |

---

## 4. 架构

逻辑上只有两层。Core 一次建好；业务只在边界补事件。

```text
                    用户请求
                        │
                        ▼
              ┌───────────────────┐
              │   Next.js BFF     │  生成 request_id
              │   Logging Core    │  记转发 status + duration
              └─────────┬─────────┘
                        │  X-Request-ID
                        ▼
              ┌───────────────────┐
              │    FastAPI Core   │  复用或自生成 ID
              │                   │  ContextVar
              │                   │  HTTP 一行日志
              │                   │  未知异常一次 traceback
              └─────────┬─────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
    Knowledge          LLM        Web Search     ← 仪器化（按需）
         └──────────────┼──────────────┘
                        ▼
                       Chat
                 Stream 生命周期         ← 仪器化（按需）
```

```text
┌─────────────────────────────────────┐
│           Logging Core              │
│  request_id · context · JSON logger │
│  BFF 关联 · HTTP 中间件 · 未知异常    │
│           完全不认识业务              │
└──────────────────▲──────────────────┘
                   │ 统一能力
┌──────────────────┴──────────────────┐
│      Business Instrumentation       │
│  外部调用 completed/failed          │
│  Chat stream started/…/failed       │
│           只有诊断价值才补            │
└─────────────────────────────────────┘
```

目录原则：横切能力进 `apps/web/lib/observability` 与 `apps/backend/app/core`。  
不建 `features/logging`。业务留在 `features/`、`services/`、`integrations/`。

```text
apps/web/lib/observability/     服务端 logger + request-id
apps/web/clients/backend/       现有 BFF 边界增强，不新建路由
apps/backend/app/core/          logging、request_context
apps/backend/app/main.py        只注册基础设施
docs/logging/README.md          本文（落地方案）
docs/logging/分工.md            两人任务拆分
```

---

## 5. 工作流程

### 5.1 一次普通 HTTP（Core，自动）

```text
Browser
  → BFF 生成 request_id（浏览器不生成）
  → 记 bff 开始；X-Request-ID 转 FastAPI
  → FastAPI：合法则复用，否则自生成；写入 ContextVar
  → 业务原样执行
  → 结束：HTTP 一行（status + duration_ms）
  → 未知异常：全局 handler 打一次 traceback，对外稳定文案
  → 响应头带回同一 X-Request-ID
```

Backend 连不上：`bff.backend.failed`，页面 503。  
Backend 返回 4xx / 5xx：仍记 `bff.backend.completed`，保留真实 `status_code`。

Knowledge 原有 catch-all 若把未知异常转成 UNKNOWN 500：以该最终边界上已安排的一次 traceback 为准，不强迫冒泡，不改原 status / 文案 / retry / fallback。

### 5.2 已知业务错误（不改语义）

```text
业务抛 BusinessError / 既有 Integration 错误
  → 按原映射返回原 code / status
  → Logging 可在该边界记 provider + duration + error_code
  → 不改 retry / fallback / UI
```

### 5.3 Chat 流（HTTP 已 200 之后）

```text
创建消息（一次 request_id）
  → 订阅 SSE（另一次 request_id，同一 message_id）
  → generate 在后台跑
       ├─ 完成  chat.stream.completed
       ├─ 停止  chat.stream.stopped
       └─ 失败  chat.stream.failed   ← 流边界打 traceback（HTTP 中间件够不到）
  → 用 message_id 把上述请求和日志对上
```

Stop / Resume 是新的 `request_id`，仍带同一 `message_id`。  
重连只重放事件，不自动再 POST 一条消息。

### 5.4 排障（人）

```text
用户或 Network 里的 X-Request-ID
  → Web 窗口搜 ID
  → Backend 窗口搜同一 ID
  → 若是生成问题，再搜 message_id
```

日志在进程 stdout（本机两个启动窗口，或以后的 `docker logs`）。不自建日志库。

---

## 6. 阶段与验收

| 阶段 | 状态 | 做什么 | 完成标准 |
| --- | --- | --- | --- |
| **P1 Logging Core** | 已推 `feat/logging-v1`，未合 `dev` | BFF/FastAPI 贯通 `request_id`；HTTP 一行；未知异常一次；allowlist | 无业务日志代码的请求仍有 ID、status、耗时；两侧 `request_id` 一致；非法头被替换；连不上 Backend 为 `failed` |
| **P2 外部能力** | 未开始 | Knowledge / LLM / Web Search 现有边界补 completed/failed | 不改现有 retry/fallback；能看到 provider 与耗时 |
| **P3 Chat 流** | 未开始 | `chat.stream` started/completed/stopped/failed | HTTP duration ≠ 生成 duration；终态仍是 done/stopped/failed |
| **P4 可诊断** | 未开始 | 错误 UI 可复制 `request_id` | 不改 `{code,message}` 主字段，只加展示 |

**P1 未合入 `dev` 前不开 P2/P3。** 浏览器走查可在 `feat/logging-v1` 上对照；Chat 仪器化前应先确认主路径没回归。

### 明确不做（V1）

ELK / Loki / Grafana / Prometheus / Sentry / OTel；独立日志库；应用内 `logs/`；Prompt/正文/SQL 入日志；全仓库改 logger；统一 Knowledge 与 Chat 错误协议（P2 只做 ID 对齐）；改业务 retry；为 Logging 做 migration；浏览器强制 `trace_id`；`error_id` 与改信封（若以后要做，只追加字段，`code` 仍为数字）。

---

## 7. 标识（标准）

| 名称 | 生命周期 | 谁生成 | 用途 |
| --- | --- | --- | --- |
| `request_id` | 一次 HTTP / 一次 BFF 转发 | BFF；FastAPI 兜底 | **V1 主关联键**，Header：`X-Request-ID`；P4 错误展示这个 |
| `session_id` | 一个对话 | Chat 业务（已有） | 会话，不是链路 ID |
| `message_id` | 一轮问答 | Chat 业务（已有） | 串联该轮多次 HTTP 与流日志 |
| `research_run_id` / `agent_run_id` | 一次研究/Agent | 对应业务（已有或以后） | 仅仪器化时写入 |

V1 不上 `trace_id`、`error_id`。需要「一轮多请求」时先查 `message_id`。  
若未来加 `X-Trace-Id`，由 Client 可选携带，Core 只校验透传，不进错误体、不入库。

浏览器不生成 ID。非法/超长 Header 丢弃后重生成，防日志注入。

---

## 8. 异常三层（标准）

**层 1 已知业务错误**  
`BusinessError`、校验、既有 Knowledge/Provider 错误：原样向上。Logging 旁路记 provider / status / duration / error_code。

**层 2 未知 HTTP 异常**  
仅 `main.py` 全局 handler：`ERROR` + traceback + `request_id`。用户：稳定文案 + 响应头 ID。禁止 client/service/api/middleware 各打一遍堆栈。

**层 3 异步 / Streaming**  
`generate` 已离开 HTTP 成功路径。未知失败由 stream 边界打一次 traceback，SSE 仍走现有 `error` → `done(failed)`。`touch` 失败只记日志，不把已成功回答改成失败。

现有 Chat `except` **P1 不改**。P3 只在终态旁路加事件，不把 Logging 写进状态机分支。

---

## 9. 实现顺序与文件（细）

### P1 文件（已在 `origin/feat/logging-v1` · `405d1f0`）

新增：

- `apps/web/lib/observability/request-id.ts`
- `apps/web/lib/observability/logger.ts`
- `apps/backend/app/core/request_context.py`
- `apps/backend/app/core/logging.py`
- `apps/backend/tests/test_logging_core.py`
- `apps/web/tests/chat/forward.test.ts`
- `apps/web/tests/config/observability.test.ts`

改：

- `apps/web/clients/backend/forward.ts`（生成/转发 ID，`completed` / `failed`）
- `apps/backend/app/main.py`（`configure_logging`、`http_logging_middleware`、结构化未知异常）
- `apps/backend/app/api/knowledge.py`（原 catch-all 增加一次 `log_exception`，不改返回语义）

认领专用路由 `anonymous-claim` **未改**；合入时核对接头，缺则补。

### P2 文件（Core 合入后再开）

仅在现有出口旁路一行：`integrations/knowledge`、`model_provider.py`、`web_search.py`。  
Knowledge 错误体里的 `requestId` 改为读 ContextVar，不再自己生成。

### P3 文件

`apps/backend/app/services/chat.py` 终态各一条事件。  
可选：`clients/backend/http.ts` / `sse.ts` 只读响应头，不改业务编排。  
不改 `use-chat-session` 状态机。

### P4 文件

错误展示组件读取已有响应头或 BFF 回写的 ID，可复制。  
不改 `{code, message}`。

---

## 10. 结构化日志（细）

单行 JSON，stdout/stderr。本地看终端；不写 `logs/`。生产轮转只放 `infra/`，本机 V1 不 blocker。

**P1 公共字段：** `timestamp` `level` `service` `environment` `event` `request_id`  
**HTTP 再加：** `method` `route` `status_code` `duration_ms`  
**出错再加：** `error_type`  
**仪器化再加（有则写）：** `provider` `operation` `session_id` `message_id`

事件名：`domain.object.state`。Core 不维护允许列表。建议：

```text
http.request.completed / http.request.failed
bff.backend.completed / bff.backend.failed
knowledge.request.completed / knowledge.request.failed
llm.request.completed / llm.request.failed
web_search.completed / web_search.provider_failed
chat.stream.started / completed / stopped / failed
```

示例（P2 以后才需要这么全）：

```json
{
  "timestamp": "2026-09-06T12:00:00.000Z",
  "level": "ERROR",
  "service": "backend",
  "event": "chat.stream.failed",
  "request_id": "abc123",
  "session_id": "s1",
  "message_id": "m1",
  "duration_ms": 12004,
  "error_type": "RuntimeError"
}
```

---

## 11. 敏感字段（细）

**允许：** `request_id`、route 模板、method、status、duration、provider、model 别名、result_count、`session_id`、`message_id`、MIME、文件大小、`owner_type`（anon/user）。

**禁止：** 密码、OTP、Authorization、Cookie、Token、API Key、BFF Secret、完整 Prompt/消息/模型输出、用户 Query 原文、论文正文、上传正文、HTTP body、SQL 参数、`console.log(headers)` / `logger.error(request.json())`。

---

## 12. 与现有代码的关系（细）

- FastAPI 已有响应头 `X-Request-Id` 与未知异常 500：P1 抽到 core，不叠第二套中间件。
- `{code, message}` 保持数字业务码；ID 走 Header。
- Chat `generate` 已有未知失败 / persist 失败日志：P3 收成结构化事件，避免再加一层 `except`。
- 专用认领 BFF 必须与 `forward.ts` 同一套 ID，否则认领链对不上。
- Knowledge 内部 catch-all 不进入全局 handler：以已安排的该边界 traceback 为准。
- 单 worker 流状态不是 Logging 能解决的；跨 worker 以后再谈 OTel。

---

## 13. 测试与走查（细）

**P1：** `test_logging_core`、`forward.test.ts`、`observability.test.ts`、认领路由带头。已合入。

**P2：** 各外部边界成功/失败各一条；降级路径与改前一致。已合入。

**P3：** 完成 / Stop / persist 失败三条流，日志能用 `message_id` 对上多次 `request_id`；UI 终态与现在一致。Backend：`test_chat_api.py`。已合入。

**P4：** 错误气泡展示并可复制 `request_id`，不改 `{code,message}`。Web：`tests/chat/error-bubble.test.ts`。已合入实现；该测试锁定接线。

**浏览器：** 见 `docs/chat/BROWSER-WALKTHROUGH.md`。登录 / 迁移 / 账号隔离需真人两账号。未做走查不得宣称 Chat 仪器化验收完成。

---

## 14. 以后怎么用

新业务：走现有 BFF + FastAPI 即可。普通 CRUD 可以一个事件都不加。  
外部 IO 或长生命周期（Research Run）再在 service/integration 边界加 2～4 个事件。  
Logging 不参与业务决策。

演进：先 stdout；真有多实例/检索/告警再上阿里云 SLS；跨长期服务再上 Trace/Span。不提前建平台。
