# M0/M1 合并前集成审查与修复

日期：2026-11-18。起点：`feat/agent-m0-integration` / `1ac47929b2f8510cd3a767c1a115433ea4327d49`，工作区干净；远程功能分支一致，远程 dev 为 `5faee7e71bb14e7d6943dab1e2e342af61bd7581`。未切分支、创建 Worktree、合并、Force Push 或修改 remote；未迁移、重建数据库或卷，无付费模型/搜索调用。

## 修复与证据

| 级别 | 根因与修复 | 主要文件 | 回归证据 |
| --- | --- | --- | --- |
| P1 | SSE 缓存仅检查缓存 owner，删除/认领后仍可读取旧内容；现在重新验证数据库归属和最新 Turn | Backend `api/agent.py` | `test_cached_stream_is_revoked_after_delete_or_claim` |
| P1 | HTML inline 无 CSP，SVG 仅 assets 入口有保护；两个文件入口统一 sandbox CSP，保留图片展示 | Backend `api/agent.py` | `test_active_artifacts_are_sandboxed_on_both_file_routes`，HTML/SVG/下载均覆盖 |
| P1 | 读取 Agent 出错被当作执行失败，允许用户再提交，而旧 Worker 仍运行；现在无伪造 result、保留 running、清除坏缓存并 fenced 释放投影租约 | Backend `agent_sessions/{service,live,repository,postgres_repository}.py` | 断流、再次恢复失败、恢复成功、禁止重复提交；PG `test_projection_release_is_fenced_and_immediately_recoverable` |
| P1 | 取消 Task 先锁 Task 再锁 Run，报告反向锁定导致 PostgreSQL 死锁；统一 Task→Run；取消后的失败/超时不再创建重试，接管保留 cancelling | Agent `control/repository.py` | 真实 PG `test_cancel_and_report_lock_order_and_no_retry_after_cancel`；SQLite 取消/超时/接管覆盖 |
| P1 | DemoRuntime 只在已领取后拒绝正式任务，正式队列也没有 Mock 过滤；API 拒绝混用，SQL 领取区分模型，Worker 声明模式并防御拒绝 Mock | Agent `api/routes.py`、`control/repository.py`、`worker/host.py` | 单元 API 模式/首次领取/租约接管；真实 PG `test_mock_and_real_claims_are_separate_on_postgres` |
| P2 | Session 缓存和恢复忽略幂等键关联 Turn，旧请求返回最新答案；现在按指定 Turn 回放且不污染最新缓存 | Backend `agent_sessions/service.py` | `test_old_idempotency_key_replays_its_own_turn_and_preserves_latest_stream`，含缓存丢失 |
| P2 | Agent 并发同键提交先查后插，唯一键竞争产生 500；回滚后复用已提交记录并重新核对请求 | Agent `control/repository.py` | 真实 PG 并发同请求一条 Task/Run，不同请求 409 |
| P2 | 空 Session 无目录导致认领被过滤；认领后 Agent 历史仍属匿名 owner 导致回放失败；空目录准备视为成功，保存内部原执行身份并在认领事务补齐旧 Turn | Agent `extensions/workspace.py`；Backend `agent_sessions/{entities,service,postgres_repository}.py` | 空目录单测、产品认领回放、旧 Turn PG 认领、原 owner 404、内部字段不出 Web |

## 验证结果

- Agent：205 项单元测试通过，另 109 个 subtests 通过；仅 Fake Provider/Mock/SQLite。
- Backend：63 项定向测试，60 通过、3 个需数据库的附件测试跳过；Agent Session PostgreSQL 套件另外实际运行，12 项全部通过。
- Agent PostgreSQL：新增 4 项全部通过，包含真实唯一键竞争和行锁；仅现有 loopback 55432 的 M0-C1 Agent 库。Backend PG 用随机测试 owner，避免固定 owner 清理影响原验收数据。
- Web：`pnpm typecheck` 通过；`pnpm test` 443/443；`pnpm lint` 0 error，1 条既有 `lib/use-popover-placement.ts:37` Hook 依赖 warning。本轮未改 Web。
- 沙箱内异步 Python 测试卡住，Web 本机 HTTP 测试 EACCES；使用现有解释器、仓库内 uv cache，解除沙箱后完成上述验证，未安装或升级依赖。
- 原演示端口有既有用户服务，未停止。最后 HTTP 联调改用本轮 Backend 19000 / Agent API 19101 / Mock Worker，以 BFF 测试身份复用现有隔离双库；不宣称重新启动了 Web BFF。原 Mock Worker 也在同一验收队列，执行归属需结合 worker 日志；SQL 并发测试在此联调前已独立完成。
- HTTP 联调三场景全部通过：done（1 Run、5 事件、报告文件一致）、timeout（3 Run、6 事件）、stopped（1 Run、2 事件）；三者均验证重连、连续游标、唯一 result、同键幂等、双库终态一致，另验证其他 owner 404。本轮三个服务已停止；脱敏结果在本地忽略的 `apps/backend/.venv/review-live/smoke.json`。复用脚本的固定 PASS 文案提到 Web BFF，但本轮实际覆盖边界以本记录为准。
- 迁移静态审查：Backend/Agent 仍独立使用 CHAT_DATABASE_URL / AGENT_DATABASE_URL，迁移未变更；本轮真实 PG 用例已在既有 schema 执行。未对旧数据库执行升级/降级；先前双库迁移、角色 CONNECT 边界证据保留。

## 剩余限制与合并建议

- 旧版本已完成认领、缺少原执行身份的历史记录无法安全猜测 owner；需受控核对和定向数据修复，本轮不改既有数据。
- Worker 接管仍从头执行 Runtime，工具副作用可能重复；没有新增 checkpoint/副作用去重架构。
- 本轮不含付费真实模型/检索、正式登录浏览器认领、跨主机共享卷故障或长时故障矩阵；M0 整体仍 PARTIAL，Mock 通过不代表科研能力生产验收完成。
- 建议修复进入 dev 的 PR 合并审查；合并前复核本轮身份委托、投影租约和 PG 行锁变更。生产发布仍需完成上述真实环境验收。原 M0/M1 证据与用户服务均保留。
