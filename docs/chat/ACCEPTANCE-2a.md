# Chat 持久化 2a · 验收用例表

基线：Backend 配置 `CHAT_DATABASE_URL`，单 worker；表已 `alembic upgrade head`。  
判定：Pass / Fail / Skip；Fail 须附现象与复现步骤。

| ID | 前置 | 步骤 | 期望 | 等级 |
| --- | --- | --- | --- | --- |
| E-01 | 本机 PG 可连 | `pg_isready`；`psql` 连 `shenzhi_chat` | 服务就绪；库存在 | P0 |
| E-02 | 已 upgrade | `\dt`；`alembic_version` | 有 `chat_sessions`/`chat_messages`；版本 `002_anon_expiry_idx`，且匿名过期索引存在 | P0 |
| C-01 | PG 模式 | `GET /chat/sessions` | `ephemeral=false`；`code=0` | P0 |
| C-02 | 无会话 owner | `POST /chat/sessions` 首问 | 返回 session_id/message_id；DB 有 1 session + 1 message(streaming→终态) | P0 |
| C-03 | C-02 完成 | SSE 跑完；`GET /sessions/{id}` | content/status=done；refs/followups 可空非必失败 | P0 |
| C-04 | 已有会话 | 同 session 续问 + SSE | 第 2 条 message；`model_messages` 含上一轮 | P0 |
| C-05 | 多轮完成 | 停 Backend 进程内缓存（新进程/clear 内存后仍读 PG）或重启后 `GET` 列表与详情 | 历史仍在；标题/内容一致 | P0 |
| C-06 | 有会话 | PATCH 收藏+重命名；重启/重读 | favorite/title 仍在 | P0 |
| C-07 | 有会话 | DELETE；再 GET/stream | 404；库中无该 session | P0 |
| C-08 | owner A 有数据 | owner B 访问 A 的 session/message | 全部 404；B 列表为空 | P0 |
| C-09 | streaming 行 | 调 `recover()` 或模拟重启 | status=failed；content 保留 | P0 |
| C-10 | 已 done | 再 `persist_message` 改 content | DB content 不变（幂等） | P0 |
| C-11 | 未配 CHAT_DATABASE_URL | 跑 Chat API 与匿名清理单元测试 | 14 项全过；`ephemeral=true` | P0 |
| C-12 | PG 模式 | 单元/契约 `test_persistence` | 契约项全过 | P0 |
| M-01 | 可选 | 匿名→登录改 owner | 会话内容不变仅 owner 变更 | P2（2a 后置） |

验收测试使用 `purge_owner`，**禁止**对共享开发库调用全库 `clear()`，以免清空浏览器联调数据。

## 执行记录

| 批次 | 环境 | 结果汇总 | 备注 |
| --- | --- | --- | --- |
| 2026-09-01 | 本机 PG 16.15（LocalAppData binaries）+ `shenzhi_chat` / Alembic `001_chat_tables` | **E-01～E-02 Pass；C-01～C-10 Pass（10/10）；C-11 Pass（9 Chat API + services 基线）** | 修复：SSE 结束后勿 cancel 已终态的 generate，否则打断 `persist_message`。匿名→登录改归属（M-01）未测（P2） |

### 逐条判定（本批次）

| ID | 结果 |
| --- | --- |
| E-01 | Pass |
| E-02 | Pass |
| C-01 | Pass |
| C-02 / C-03 | Pass |
| C-04 | Pass |
| C-05 | Pass |
| C-06 | Pass |
| C-07 | Pass |
| C-08 | Pass |
| C-09 | Pass |
| C-10 | Pass |
| C-11 | Pass |
| C-12 | Pass（`tests.test_persistence` + 上表） |
| M-01 | Skip（2a 后置） |

### 2026-09-02 · 方向三 PostgreSQL 认领验收

环境：本机 PostgreSQL 16，`shenzhi_chat`，Alembic `001_chat_tables`。测试仅使用本机开发数据库，不记录连接凭据。

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| E-01 / E-02 | Pass | PostgreSQL 接受连接；`alembic_version=001_chat_tables`；存在 `chat_sessions`、`chat_messages`。 |
| M-01 匿名→账号 owner 切换 | Pass | `tests.test_persistence` 7/7：完成会话仅更新 owner，Message/Session ID 保持；streaming 跳过、完成后重试成功；并发调用只有一次移动。 |
| Chat API（PostgreSQL 模式） | Pass | `tests.test_chat_api` 10/10；claim 结果正确反映 `durable=true`。 |
| Chat API（内存模式） | Pass | `tests.test_chat_api` 10/10；claim 保持 `durable=false`，临时容量限制保持有效。 |
| 2a 持久化验收 | Pass | `tests.test_acceptance_2a` 11/11。Windows asyncio 关闭连接时输出资源清理告警，但没有测试失败或数据库断言失败。 |

说明：本批次验证了后端持久化链路与匿名认领事务。Better Auth 登录后的实际浏览器页面联调仍需在启动 Web/Backend 后单独验收。

### 2026-09-05 · 持久化、匿名生命周期与迁移确认补测

环境：本机 PostgreSQL 16 测试库；Alembic 已从 `001_chat_tables` 升级至 `002_anon_expiry_idx`。测试仅使用本机开发数据库，不记录连接凭据。

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| E-01 / E-02 | Pass | PostgreSQL 端口可连；Alembic 成功应用 `002_anon_expiry_idx`，匿名 session 过期 partial index 已建立。 |
| 终态写库失败语义 | Pass | 内存模式 Chat API 测试验证：`persist_message` 抛错时先发送 SSE `error`，最后 `done.status=failed`，不会先向客户端确认成功。 |
| 匿名生命周期与清理 | Pass | PostgreSQL 契约测试覆盖：只清理过期匿名终态 session、保留 user 数据和 active streaming session；匿名历史成功列表读取会续期同一匿名 owner 的全部 session。 |
| Web 弹窗与认领服务 | Pass（自动化） | Web 类型检查与 117 项测试通过；预览只返回 durable 匿名会话数，用户确认后才发送认领请求。 |
| PostgreSQL 自动化验收 | Pass | `tests.test_persistence`（7 项）与 `tests.test_acceptance_2a`（11 项）通过；Windows asyncio/asyncpg 在多事件循环收尾时仍会输出资源关闭告警，但进程以成功状态结束，所有数据库断言通过。 |
| 浏览器 P0 | Blocked | 已启动本地页面，但当前会话未完成真实账号登录；匿名→账号确认弹窗需要在持久化后端和已登录测试账号下做实际 UI 操作，不能以自动化结果替代。 |

### 复跑命令

```powershell
# 启动本机 PG（若未运行）
& "$env:LOCALAPPDATA\shenzhi-postgresql\pgsql\bin\pg_ctl.exe" `
  -D "$env:LOCALAPPDATA\shenzhi-postgresql\data" `
  -l "$env:LOCALAPPDATA\shenzhi-postgresql\logfile.txt" `
  -o "-p 5432" start

cd apps/backend
$env:CHAT_DATABASE_URL = "postgresql://shenzhi:shenzhi_dev@127.0.0.1:5432/shenzhi_chat"
uv run python -m unittest tests.test_acceptance_2a -v

# 内存降级基线（勿设置 CHAT_DATABASE_URL）
Remove-Item Env:CHAT_DATABASE_URL -ErrorAction SilentlyContinue
uv run python -m unittest tests.test_chat_api tests.test_services -v
```

