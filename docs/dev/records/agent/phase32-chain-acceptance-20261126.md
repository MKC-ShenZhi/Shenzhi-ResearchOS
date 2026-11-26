# Phase 3.2 双版本发布与结算验收

日期 2026-11-26。项目 `shenzhi-phase32-accept` 使用独立 Compose、两个 PostgreSQL 数据库和测试凭据。本轮复用已构建的 Admin、Backend、Agent 镜像。两个 Worker 挂载各自的只读配置制品。测试结束后停止隔离容器。

| 验收项 | 结果与边界 |
| --- | --- |
| 两个容器同时上报 | 两台 Worker 启动相同镜像，分别读取两份不可变配置，产生不同 Config Revision。Admin Fleet API 返回两份健康实例的实际 Manifest。 |
| 审批、发布及回滚 | 通过容器内 Backend 管理入口完成 A 激活、B 激活、回滚至 A。每步由指定 Worker 确认。Agent PostgreSQL 回执为 active、active、rolled_back，Backend 权益写入屏障最终无残留。 |
| Provider 验证 | 使用测试签名的网络证明，证据中的能力来自上述实际 Worker Manifest。Provider 地址为 example.invalid，未发送 Provider 请求。 |
| Task 版本和 Lease | 独立 PostgreSQL 的 7 个管理专项通过，包括错版本领取/接管拒绝、兼容接管、并发领取和回滚保持原任务约束。此专项使用测试 Task 和 Worker 证据。 |
| 结算与故障 | 两库 PostgreSQL 的 3 个专项通过，覆盖提交到结算、Outbox 确认丢失重投、过期 Lease 拒绝新调用而接受历史完成事实。HTTP 用例使用真实服务路由和受控 Provider 替身，运行于 ASGI 测试进程。 |
| 单条真实任务闭环 | 未完成。Compose 的 Agent 库核对为 0 条 Task。还需以同一条正式授权 Task 在两个 Worker 容器间触发故障接管，串联 Provider 请求、Outbox 与 Backend 结算。缺少专用非生产 Provider 与凭据轮换证据。 |

PostgreSQL 专项运行于单独的回环 Docker 实例，包含一个配置专项库与两个 A-line 测试库。运行命令如下。

~~~powershell
uv run --no-sync python -m pytest -q --tb=short tests/test_management_config.py tests/integration/test_a_line_postgres.py::PostgresALineTests::test_http_submit_permit_provider_delivery_close_and_trusted_query tests/integration/test_a_line_postgres.py::PostgresALineTests::test_outbox_ack_loss_retries_same_measurements tests/integration/test_a_line_postgres.py::PostgresALineTests::test_lease_takeover_blocks_new_start_but_accepts_historical_completion
~~~

生产配置写入与强制调度仅在隔离覆盖配置中开启，本轮不满足生产开放条件。

## 跨容器任务闭环补验

另建 `shenzhi-live-accept`，复用 Admin、Backend、Agent 镜像和独立双库。Provider 替身通过 Compose 私网 HTTPS 提供 OpenAI 兼容 SSE 帧，Worker 验证测试 CA。Backend 通过业务运行 API 创建正式授权 Task，Agent 保存修订约束和签名 Grant 绑定。测试使用两个配置修订、三台 Worker 实例和独立 Usage Worker。

| 场景 | 实测证据 |
| --- | --- |
| 正常到达 Provider 后强杀 Worker | Task `eb570b7daf5c4c85b04a6311ca057754`。Worker A 以 Lease 1 发出请求，替身挂起响应，随后强杀 A。Lease 自然过期，A 同版本 Worker 以 Lease 2 接管同一 Run 并完成任务，两条 Execution 都已封存。 |
| 可计量用量和重复投递 | 首个任务的全部 Outbox 记录均已投递，10 Token 可计量用量只产生一笔正向入账。在隔离库仅将该测量的投递状态恢复为 pending，保留原始测量 ID 和内容。实际 Usage Worker 重投获得 duplicate，账本仍为一笔 10 Token。 |
| 不同版本接管拒绝 | 第一轮 Lease 到期时测试环境曾重启，Worker B 掉线，因此另测 Task `dbb21c879e7d4e0880b3dc545920628f`。强杀 A 后将隔离库的 Lease 到期时间推进至过去。B 的心跳序号继续递增，连续 10 次请求领取均未拿到过期 Lease。启动兼容 Worker 后，以 Lease 2 接管并完成。 |
| 无故障关闭 | Task `597744c5a62e4964b7f1789d375241c4` 使用独立测试 Owner，实际 Worker 执行成功并由 Usage Worker 关闭 Grant。Backend 确认 closed / settled，账本一笔 10 Token。 |
| 未知用量保护 | 两个被强杀的原始调用都保留未知用量，相关 Grant 标为 reconciliation_required，未按零使用关闭。两个恢复完成调用共两笔 20 Token，另一个正常 Task 一笔 10 Token。 |
| 发布及回滚 | 三个 Task 完成后再激活 B 并回滚 A。核对三条 Task 仍绑定各自原始 A 修订，Outbox 8/8 已投递，账本仍是三笔合计 30 Token，权益写入屏障无残留。 |

跨容器业务闭环验收通过。真实外部 Provider 及凭据轮换仍需使用专用非生产凭据单独验收。
