# Auto Research 用户取消修复验收

## 修改

- `apps/agent/src/agent_app/api/routes.py`：controls 返回取消状态；有效 Worker 可在 cancelling 阶段写入收尾事件。
- `apps/agent/src/agent_app/control/metering.py`：保留租约、身份、fencing 校验，单独区分 `TASK_CANCELLED`，新调用授权和启动仍被拒绝。
- `apps/agent/src/agent_app/execution/runtime.py`：统一监听停止信号，中断并等待模型／工具协程退出；保留已完成的并发结果，为未完成调用写入带 `cancelled` 标记的结束事件。沿用此前的持久化 run_id 对齐改动。
- `apps/agent/src/agent_app/execution/metering.py`：分别记录真实门禁失败与取消，保留既有 Observation / Spool 用量收尾。
- `apps/agent/src/agent_app/worker/host.py`：通过现有 0.5 秒 controls 轮询接收取消；不再把所有 stop 信号归类为 authorization_denied。
- `apps/backend/app/services/agent_sessions/timeline.py`、`service.py`：持久化和回放工具取消标记。
- `apps/web/clients/backend/agent.ts`、`features/agent-chat/timeline.ts`：接收工具取消标记。
- `apps/web/features/agent-chat/shenzhi-ai-page.tsx`、`timeline-view.tsx`：正在停止状态、取消完成提示和中性工具取消样式；保留已完成内容。
- `docs/agent/lifecycle.md`：同步 V2 取消约定。

测试文件：`apps/agent/tests/unit/test_agent.py`、`test_worker_takeover.py`，`apps/backend/tests/test_agent_timeline.py`，`apps/web/tests/agent/client-protocol.test.ts`。

## 自动测试

- Agent：`uv run --locked pytest tests/unit -q`，243 passed，122 subtests passed。
- Backend：`uv run --locked python -m unittest tests.test_agent_timeline tests.test_agent_sessions tests.test_agent_contracts -q`，31 tests，OK。
- Web：测试 TypeScript 编译及 client-protocol / timeline 两组测试，15 tests passed。
- Web：`pnpm typecheck`、修改文件的 ESLint、`git diff --check` 通过。

定向覆盖：静默模型流中停止及部分内容保留；顺序工具停止；多个并发工具停止及清理等待；已完成并发工具结果保留；完成事件与取消同时发生；Control 取消后拒绝新授权但允许有效 Worker 收尾；旧 Worker／终态后事件拒绝；冲突终态报告拒绝；真实授权拒绝仍失败；Worker 后台协程退出；工具取消状态持久化及 SSE 恢复。

## 本地真实页面与数据库

验收会话：`ses_6cd860b13f7240a99715d25b42103c78`。

- 三次 paper_search 完成后停止后续模型处理：页面立即出现“正在停止…”，最终显示“已手动停止”，已完成检索结果保留。
- 两个 read_paper 在途时停止：两项均显示“已取消”，没有红色任务失败；刷新并展开过程后状态一致。
- 产品数据库两轮均为 `stopped / cancelled`，error 为空。
- Agent 数据库两轮均为 `cancelled`，error_code 为空；tool_call / tool_end 数量分别为 3/3 与 2/2，均有一个 run_end。
- 产品时间线未完成工具数为 0；检查时没有 queued、running、cancelling 任务。
- 三个 Agent 服务已重启，Web 源码同步已确认。

## 限制

- 取消本地协程不保证撤销上游已接受的请求；已发生和未知的用量继续按既有协议结算，不能视为零。
- 0.5 秒是 controls 轮询间隔，实际停止耗时还包括网络和资源清理；阻塞或不响应取消的上游／同步代码不能保证即时退出。
- 四类停止场景及终态竞争有确定性测试；真实 PostgreSQL 同时事务的锁竞争未单独验收。创建隔离测试数据库被自动审批拒绝，未执行建库或绕过；竞争测试使用 SQLite / ASGI，真实页面测试走当前本地 PostgreSQL。
- 历史错误终态未改写；此前失败记录保持原样。
