# ShenZhi Agent Management Phase 3.2 验收记录

后续证据见 [2026-11-26 跨容器闭环补验](../dev/records/agent/phase32-chain-acceptance-20261126.md#跨容器任务闭环补验)。该补验覆盖受控 Provider 替身下的多版本接管、Usage 重投去重及正常结算。下文保留当时的未完成事项，当前实现以 [管理控制台维护说明](agent-management-console.md) 为准。

工作区基线 `chore/docker-compose-infra` / `f04e01ac11f95e75f5c29bdfa0e6d4025c94dbc3` 加现有未提交改动。测试项目 `shenzhi-phase32-accept` 使用独立网络、卷和测试环境。生产开关保持默认关闭。

## 镜像与 Compose

- 替代基础镜像来自 Docker Official Images 的 Amazon ECR Public 镜像，Python 摘要 `sha256:44cf1793efa7c7a476bb0f2cff81443f4a072c90c1cb127e2924933daa3e8c64`。UV 0.13.6 使用 PyPI 发布 wheel，先校验 SHA-256 `22759b8895e1103578de6fb4cd27e94b4399d021023378d29f01333717751fba` 再生成本地工具镜像。Windows TLS 失败时通过隔离基础容器下载并继续验证证书。保留应用 Dockerfile 默认来源并增加可指定的 `PYTHON_IMAGE`、`UV_IMAGE`。
- 隔离构建副本使用 Engine 内置 Dockerfile frontend，避开外部 frontend manifest 的 EOF。Admin、Backend、Agent 均从 Phase 3.2 源码构建。Agent API、Worker 和 Usage Worker 共用一份镜像。使用 Compose `--no-build --pull never` 启动测试栈，覆盖配置移除开发源码挂载。首次编排结果为 Auth、Backend、Agent 三项迁移退出 0，PostgreSQL、Admin、Backend、Agent API 健康，Worker、Usage Worker 运行。
- 镜像摘要。Admin `sha256:f27016c21425d631961873f4f865693cdd6df33b0dc502af879bdf5b0e423827`，Backend `sha256:8cc353565ec23edfb570097da983029b43ec8360c5b9a933016fe8a226af6ed1`，Agent `sha256:52f353af2fe79d95f9958cd16fd630054c61071a0f4ce01fe0fb4914d508a8f1`。Fleet 接口联调发现 Backend 把直接字典交给只处理模型的响应函数，修复后仅重建 Backend；Admin 和 Agent 镜像复用。
- 最终复验通过 Admin 登录、未登录请求拒绝、配置 GET、默认写入关闭、原套餐 GET、Fleet 与 Manifest 查询。容器 inspect 确认应用直接运行新镜像，应用源码无宿主挂载。重启实际 Worker 后，PostgreSQL 同时保留重启前后的注册实例。重建过程中短暂出现代理连接拒绝，待 Backend 和 Admin 就绪后，同一测试通过。

## 权益并发边界

Backend `030_agent_config_barrier` 用 PostgreSQL 共享事务锁覆盖影响兼容性扫描的 Policy、Release、Owner 和 Grant 创建/修订写入。配置切换前取得排他锁并登记持久屏障，已在提交途中的相关写入使本次切换返回可重试冲突。登记后读取权益快照，留到 Agent 回执确认再解除。Usage Ledger、现有 Permit、结算及关闭 Grant 未纳入该屏障。未知网络结果保留屏障，独立 Reconciler 按原操作 ID 获取结果并补审计，已明确暂停的发布也可恢复屏障。没有可靠回执且发布继续挂起时，需要管理员暂停或按原请求对账。相关写操作在屏障期间返回冲突，可由调用方重试。

独立 PostgreSQL 测试验证在途写入阻挡切换、登记后的 Policy 写入受限、Ledger 可写、旧操作无法解除屏障、原操作成功解除和恢复写入。Backend 迁移完成 upgrade → downgrade → upgrade，测试中产生了合成 Policy。该保护针对切换瞬间的竞态，正常套餐与权益写入在屏障解除后仍沿用原业务规则。生产级并发、容器断网后的自动恢复和管理员处置仍需完整演练。

## Worker 历史与部署

新增 Agent `0007_worker_lifecycle`。认证 Worker 上报记录注册、上线、离线、健康变化、Manifest 变化和 Run 关联；迟到心跳恢复时记录曾发生的超时和恢复。尚无独立巡检器主动为静默 Worker 写超时事件，当前状态仍可通过最后心跳派生。历史事件与 Manifest 请求同权限，按 Worker 查询和分页。

运维 Compose 脚本支持独立本机 Docker 下显式 `--apply`。使用摘要镜像、隔离项目和 Worker 专用服务，核对发布标签、只读制品路径、配置 ID 和摘要；默认 Dry Run。Backend 无需 Docker Socket。实际旧/新配置的跨容器分批演练未完成。

## 回归与开放门槛

- Admin TypeScript/Vite 构建通过，Backend 原有 Admin、权益和 Gateway 回归 20 项通过。Agent 管理浏览器、Phase 1～3 回归 30 项通过，针对 Fleet HTTP 响应修复追加回归通过。
- 专用非生产 Provider 及凭据轮换证据、多版本 Worker 并行真实任务、Lease 故障接管、跨容器结算和 Usage Outbox 连续性仍待验收。Skill 脚本继续关闭。当前不具备 Production Readiness Candidate 条件。
