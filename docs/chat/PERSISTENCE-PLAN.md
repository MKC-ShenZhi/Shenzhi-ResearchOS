# Chat 会话持久化实现方案

只改 Backend 存储层。页面 → BFF → FastAPI Chat API → SSE 协议均不改动。

## 能力分层（与后续演进）

本方案交付的是**会话持久化（基础能力）**，为上层**历史管理（产品能力）**与**上下文工程**提供数据基座。2a 不实现搜索、归档、跨设备等，但表结构与 Repository 读写方式应为后续扩展留口。

```text
历史管理（产品能力，后续）
  ├─ 历史会话列表 / 打开旧会话 / 重命名 / 收藏 / 删除
  ├─ 搜索历史 / 恢复上下文继续聊天
  └─ 归档、分页、跨设备 …
        ↑ 依赖
会话持久化（2a 基座）
  ├─ Session / Message 落库
  ├─ owner 隔离、重启不丢、可重新加载
  └─ 多轮上下文由 session.messages 重建（model_messages）
```

| 层级 | 2a 范围 | 后续（产品/架构另行敲定） |
| --- | --- | --- |
| 持久化基座 | PG 存 session + message 终态；列表/详情/续问可读 | checkpoint、事件表、附件对象存储 |
| 历史管理 UI | 现有侧栏能力在重启后仍可用 | 全文搜索、批量归档、跨设备同步 |
| 上下文工程 | 沿用 `model_messages` 从 DB 重建 prior 轮 | 摘要压缩、分层记忆、token 预算策略 |

## 总体方向

当前 Chat 已能跑通，会话与消息存在 FastAPI 进程内存中，服务重启后历史丢失。

本方案采用：PostgreSQL 保存已完成的对话；进程内 Message 对象承载正在生成的流式状态。不新建第二套 API，不引入 Redis 或 Kafka。配置 `CHAT_DATABASE_URL` 时走 PostgreSQL；未配置时继续使用现有内存仓库，供开发与 CI 降级。

## 项目架构

```text
Browser
   ↓
Next.js（features/chat → clients/backend）
   ↓
BFF（/api/v1，注入 owner，不传 Cookie）
   ↓
FastAPI（api/chat.py → services/chat.py）
   ↓
SessionRepository ──┬── PostgreSQL（历史）
                    └── 进程内 dict（生成中：Task / events / SSE）
```

身份由 BFF 注入，格式为 `user:{id}` 或 `anon:{uuid}`。Backend 不查询 Auth 用户表，仅将 owner 作为 TEXT 写入 PostgreSQL。

## 两种业务情况（写库心智模型）

Chat 库**不建用户表**。身份只体现在 `chat_sessions.owner`（`anon:…` / `user:…`）。Auth 库管「人是谁」；Chat 库管「这个人下面挂了哪些会话」。

```text
owner（匿名或登录）  1 ── N  Session（会话）  1 ── N  Message（消息）
```

| 情况 | 含义 | 实际写库动作 |
| --- | --- | --- |
| **情况二：该 owner 第一次 Chat** | 库里还没有他的任何 session | `INSERT` 第一条 `chat_sessions`（带 owner）+ 首条 `chat_messages` → 之后等同情况一 |
| **情况一：已聊过 / 已有会话** | 该 owner 下已有 session 行 | 新开话题：再 `INSERT` session+message；续问：只 `INSERT` message，挂在已有 session_id 下 |

**不要误解「第一次要构建基本数据库结构」**：

- **表结构**（`chat_sessions` / `chat_messages`）由 Alembic **部署时一次建好**，不是用户首次发问时建表。
- 用户首次 Chat 只是 **首次 INSERT 业务行**（第一条会话挂到该 owner）。

匿名注册成正式用户时（附图思路，2a 可后置）：**会话内容不动，只改归属**——`UPDATE chat_sessions SET owner = 'user:…' WHERE owner = 'anon:…'`。不做内容迁移、不重建消息。

## 各流程注入数据库的位置

只在下列节点写/读 PG；**流式 delta 不写库**。

```text
【部署一次】alembic upgrade head
    → 建表（情况二里说的「基本结构」在这里完成，不是运行时）

【请求入口】BFF 注入 owner（anon:{uuid} | user:{id}）
    → 后续所有写库都带这个 owner，实现「关联到用户」

① POST /chat/sessions          （新开话题 = 情况一或二）
    prepare_message
      └─ create(owner, …)       → INSERT chat_sessions（owner 关联）
      └─ add_message(…)         → INSERT chat_messages（status=streaming）
    ※ 情况二：这是该 owner 的第一行；情况一：又多一行 session

② POST /sessions/{id}/messages （同会话续问 = 情况一）
    prepare_message(已有 session)
      └─ add_message(…)         → 只 INSERT chat_messages

③ GET  /messages/{id}/stream   （SSE，启动 generate）
    delta / events              → 仅内存，不写 PG
    generate finally 终态       → persist_message（UPDATE 终态字段）
    stop / resume               → persist_message（stopped / 回到 streaming）

④ GET  /sessions、/sessions/{id}
    list / get                  → SELECT（按 owner）；生成中消息用内存覆盖

⑤ PATCH / DELETE session
    update / delete             → UPDATE 标题收藏 / DELETE session（级联消息）

⑥ 进程启动 lifespan
    recover                     → 残留 streaming → failed
```

一句话：**关联用户 = INSERT/UPDATE 时写 `owner`；新会话 = 插 session；新一轮问答 = 插 message；生成中 = 内存；说完 = UPDATE 终态。**

## Chat 完整输入输出流（现状梳理）

参与 Backend 改动前，先对齐端到端时序。代码入口见 `apps/backend/app/api/chat.py`、`services/chat.py`、`services/sessions.py`；前端见 `features/chat/hooks/use-chat-session.ts`。

### 首轮提问

```text
用户发送
  → Web: beginTurn → POST /chat/sessions（BFF 注入 owner）
  → Backend: prepare_message（同步）
       ├─ attachment_context（读内存 upload）
       ├─ repository.create（新 Session）
       └─ repository.add_message（新 Message，status=streaming，尚未调模型）
  → 立即返回 { session_id, message_id }          ← HTTP 在此结束，生成尚未开始

  → Web: GET /messages/{id}/stream（SSE）
  → Backend: stream_events
       ├─ 首个订阅者且 task 为空 → asyncio.create_task(generate)
       └─ 循环 yield message.events[cursor…]（heartbeat 保活）

  → generate（async Task，与 HTTP 请求并发）
       ├─ await knowledge_service.search / web_search
       ├─ model_messages（从 session.messages 拼多轮上下文）
       ├─ async for provider.stream → message.emit(delta)（仅写内存）
       ├─ await provider.followups
       └─ finally: status 终态 + emit(done) + repository.touch
```

### 续问 / 停止 / 恢复 / 读历史

| 动作 | HTTP | Backend 要点 |
| --- | --- | --- |
| 续问 | POST `/sessions/{id}/messages` | 同 prepare_message，禁止上一条仍为 streaming |
| 停止 | POST `/messages/{id}/stop` | cancel task → status=stopped → emit(done) |
| 恢复 | POST `/messages/{id}/resume` | 清 task、status 回 streaming；客户端带 last_event_id 重连 SSE |
| 列表/详情 | GET sessions | repository.list / get → Message.public() |
| 重命名/收藏/删 | PATCH/DELETE session | 纯 Repository CRUD；DELETE 会先 stop 各 message |

要点：**创建消息与启动生成是两步**。POST 只登记 Message；**第一个 SSE 连接**才 `create_task(generate)`。断开最后一个 SSE 订阅会 cancel 未完成的 generate。

### 输出形态

- **HTTP JSON**：`{code:0, data:…}`；创建/续问只给 id，不含正文。
- **SSE**：`meta → refs → meta → delta* → followups → done`（失败则 `error → done`）；`id` 为事件序号，供 `Last-Event-ID` 重连。
- **多轮上下文**：不在 POST body 里传 history；Backend 在 `model_messages` 内从 `session.messages` 读取已完成轮的 question/content。

## 同步 / 异步与持久化落点

现有流程**已是异步架构**（FastAPI + asyncio Task + async HTTP 调模型），但 **Repository 目前是同步内存 dict**。引入 PostgreSQL 后，若混用「同步写库」与「异步 generate」，容易出现：未 await 就返回、shutdown 丢写、读列表看到旧 status 等难查 bug。2a 约定如下。

### 各段性质（现状 → 2a）

| 阶段 | 现网 | 2a 持久化 |
| --- | --- | --- |
| prepare_message / add_message | **同步**，仅写内存 | **await** 事务 INSERT session+message（streaming）并注册同一 Message 对象 |
| generate 热路径（delta） | **async**，只改内存 + emit | **不变**，仍不写 PG（避免每 token 阻塞 event loop） |
| 终态（done/stopped/failed） | sync touch | **await persist_message**（在 generate/stop 的 finally 或等价路径） |
| resume | sync 改 status + 清 task | 改 status 后 **await persist_message**（仍为 streaming） |
| list / get | sync 读内存 | 读 PG；若 message_id 仍在 `repository.messages` 则**内存覆盖**行内 content/status |
| 启动 recover | 无 | **await** 将 PG 中残留 streaming → failed |

### 必须遵守的并发规则

1. **单一真相源（生成中）**：streaming 期间以进程内 `Message` 为准；PG 行在 streaming 期间可为空 content 或 2a.1 checkpoint，读路径不得仅用 PG 覆盖内存。
2. **状态变更才落库**：persist 只挂在 status 迁移点（create/resume/stop/generate 结束/recover），不在 `emit('delta')` 里写库。
3. **接口统一 async**：PG 实现下 `create`、`add_message`、`persist_message`、`recover`、`list`、`get` 等均为 `async`；Memory 实现用 async 空操作包装，避免 `if pg: await` 分支散落业务层。
4. **禁止 fire-and-forget**：`persist_message` 必须 await；进程退出前沿用现有 `repository.close()` cancel task，并在 lifespan shutdown 中 **await recover 未完成写**。
5. **幂等与竞态**：终态 UPDATE 带 `WHERE status='streaming'`；避免 recover 与迟到的 persist 互相覆盖（见附录 B）。

### 为何不在 POST 里同步等模型

POST 快速返回 id、SSE 懒启动 generate，是为让客户端尽早连流、支持 Last-Event-ID 重连。持久化**不改变**该时序：POST 只保证 DB 中已有 streaming 行 + 内存对象；generate 仍由 SSE 触发。

改动范围（仅 Backend）：

| 层 | 做什么 |
| --- | --- |
| services/sessions.py | 双实现 Repository；保留现有 dataclass |
| services/chat.py | 三处状态变更后 **await** persist_message（generate finally / stop / resume） |
| api/chat.py | ephemeral 字段跟随是否启用 PG |
| main.py | 启动时执行 recover |

## 技术栈

| 用途 | 选型 |
| --- | --- |
| 运行时 | FastAPI + Python 3.12+ |
| 持久化 | PostgreSQL |
| ORM / 迁移 | SQLAlchemy 2 async + asyncpg + Alembic |
| 配置 | CHAT_DATABASE_URL（Backend 专用，与 Web Auth 库分离） |
| 2a 部署 | 单 worker（流式生成绑定进程） |

## 实现方式

### 存储结构

两层存储，职责分离：

| 位置 | 内容 | 生命周期 |
| --- | --- | --- |
| PostgreSQL | 会话元数据、消息终态（content、refs、status 等） | 跨重启保留 |
| 进程内 dict | 生成中的 Message（Task、events、订阅者） | 本 worker；生成结束后清除 |

不新建 active_stream_cache 模块。现有 repository.messages 字典即为活跃缓存；PostgreSQL 实现只做镜像写库，保持对象身份不变（resume 与多轮上下文依赖对象引用比较）。

数据库两张表：chat_sessions（一个话题）、chat_messages（多轮问答）。2a 阶段不持久化附件原文件，解析后的文本随消息字段存储。

### 消息状态

不引入 pending 状态；创建消息时即为 streaming，与现有代码一致。

```text
streaming → done | stopped | failed
stopped / failed → streaming（resume，仅会话最后一条）
重启恢复：streaming → failed（保留已有 content，用户可 resume）
```

终态写入使用条件更新 `WHERE status = 'streaming'`，保证幂等，避免 done 被后续 recovery 覆盖。

### 工作流

写路径：

1. 建会话或发消息：事务内 INSERT session（如需）与 message（streaming），并注册进程内对象。
2. 客户端连接 SSE：generate 调用模型，events 仅写入内存。
3. 结束、停止、失败或 resume：persist_message 将终态或新状态镜像到 PostgreSQL。
4. 服务启动：recover 将残留的 streaming 标记为 failed。

读路径：

1. 侧栏列表与历史详情：按 owner 查询 PostgreSQL。
2. 若消息仍在进程内生成：以内存对象覆盖 PostgreSQL 行（返回最新 content 与 status）。
3. 已终态且不在内存：由 PostgreSQL 重建；SSE 无事件可重放，详情走 GET /sessions/{id}。此为 2a 已知边界，与当前前端行为一致。

不变部分：

- SSE 事件名：meta、delta、refs、followups、error、done。
- Repository 现有方法名与签名；仅新增 is_durable、persist_message、recover。

## 分阶段

| 阶段 | 交付 | 说明 |
| --- | --- | --- |
| 2a | PG、Repository、终态落库、启动 recovery | 本次交付；单 worker |
| 2a.1 | 可选 checkpoint（≥8 秒或 ≥4KB 节流写 content） | 缩小崩溃丢字窗口 |
| 2b | chat_message_events、多 worker SSE | 事件名仍用上述六种 |
| 2c | 附件元数据与对象存储 | 不阻塞 2a |

匿名 TTL、登录用户保留期等待产品确认，本方案不作硬性规定。

## 开发顺序

1. Alembic 建表，引入 sqlalchemy、asyncpg、alembic。
2. 实现 PostgresSessionRepository，与 Memory 实现跑契约测试。
3. 将 prepare_message 改为 async；chat.py 三处 await persist；main.py lifespan await recover；ephemeral 跟随 is_durable。
4. 本地配置 PostgreSQL，验证多轮对话后重启历史仍在。
5. 现有 16 项 Backend 测试与 Web 测试零改动通过后合入 dev。

## 2a 验收

- [x] Repository 双实现、async 接口、persist/recover 接入（代码已合入）
- [x] 未配置 CHAT_DATABASE_URL 时行为与当前一致（16 项测试通过）
- [x] 重启 / 清内存后侧栏与多轮内容完整（见 `ACCEPTANCE-2a.md` C-05）
- [x] 收藏、重命名、删除跨进程缓存有效（C-06 / C-07）
- [x] 不同 owner 互不可见；启用 PG 时 ephemeral 为 false（C-01 / C-08）

正式用例表与执行记录：`docs/chat/ACCEPTANCE-2a.md`。

## 一句话

PostgreSQL 存历史，内存跑流式；Repository 双实现。2a 先保证重启不丢历史，再考虑多 worker 与附件持久化。

---

## 附录 A：表结构

```sql
CREATE TABLE chat_sessions (
  id UUID PRIMARY KEY,
  owner TEXT NOT NULL,
  title TEXT NOT NULL,
  settings JSONB NOT NULL DEFAULT '{}',
  favorite BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chat_sessions_owner
  ON chat_sessions (owner, favorite DESC, updated_at DESC);

CREATE TABLE chat_messages (
  id UUID PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  settings JSONB NOT NULL DEFAULT '{}',
  attachment_context TEXT NOT NULL DEFAULT '',
  warnings JSONB NOT NULL DEFAULT '[]',
  content TEXT NOT NULL DEFAULT '',
  reasoning TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  message_refs JSONB NOT NULL DEFAULT '[]',
  followups JSONB NOT NULL DEFAULT '[]',
  duration_ms INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT chk_chat_messages_status
    CHECK (status IN ('streaming', 'done', 'stopped', 'failed'))
);
CREATE INDEX idx_chat_messages_session ON chat_messages (session_id, created_at);
CREATE UNIQUE INDEX uq_chat_messages_active
  ON chat_messages (session_id) WHERE status = 'streaming';
```

message_refs 对应代码中的 Message.references（references 为 PostgreSQL 保留字）。迁移文件放在 apps/backend/migrations/。

## 附录 B：persist 与 recover

```sql
UPDATE chat_messages
SET content = :content, reasoning = :reasoning, status = :status,
    message_refs = :message_refs, followups = :followups,
    duration_ms = :duration_ms, error = :error, completed_at = now()
WHERE id = :message_id AND status = 'streaming';
UPDATE chat_sessions SET updated_at = now() WHERE id = :session_id;

UPDATE chat_messages
SET status = 'failed', error = 'backend restarted while generating', completed_at = now()
WHERE status = 'streaming';
```

## 附录 C：Repository 接口

```python
repository = PostgresSessionRepository(...) if os.getenv("CHAT_DATABASE_URL") else MemorySessionRepository()
```

现有方法签名不变：create、get、list、update、delete、add_message、message、session_for_message、touch、save_upload、upload、prune、clear、close。

新增 / 变更成员（**建议全部为 async def**，Memory 内直接 return，避免 sync/async 混调）：

| 成员 | Memory | PG |
| --- | --- | --- |
| is_durable | False | True |
| persist_message | async no-op | 见附录 B |
| recover | async no-op | 见附录 B |
| create / add_message / list / get / … | async 包装现有 sync 逻辑 | async SQLAlchemy |

## 附录 D：测试要点

现有 16 项 Backend 测试与 Web protocol、bff-identity 测试须零改动通过。新增契约测试（配置 PG 时运行）：owner 隔离、状态机、finalize 幂等、重启恢复、首问事务、单流 20009。

## 附录 E：风险

| 风险 | 应对 |
| --- | --- |
| 崩溃丢失生成中内容 | 2a 接受；2a.1 加 checkpoint |
| done 被覆盖 | 条件更新 |
| 多 worker 冲突 | 2b 事件表；2a 保持单 worker |
| sync/async 混用丢写或脏读 | Repository 统一 async；persist 仅 await、仅状态迁移点 |
| 方案过重 | 2a 不引入 Redis、Kafka、分布式锁 |

2026-08-30（补充 I/O 流、同异步落点、能力分层）
