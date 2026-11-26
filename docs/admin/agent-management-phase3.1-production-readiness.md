# ShenZhi Agent Management Phase 3.1 生产就绪验收

## 1. 基线与工作区保护

本次继续使用 `chore/docker-compose-infra`，HEAD 为 `f04e01ac11f95e75f5c29bdfa0e6d4025c94dbc3`，包含设计基线 `60188121277bdeb738f19e6e414d82e386533b6c`。工作区保留 Phase 1～3 的未提交文件和历史迁移。未切分支、提交、推送或连接生产数据库。PowerShell 执行本地开发与测试，按用户说明通过 WSL 调用现有 Docker CLI。

## 2. 真实镜像构建结果

Admin 使用隔离源码副本和仓库开发目标重新构建，Image Tag 为 `shenzhi-phase31-828762ea/admin:source-dev`，镜像摘要为 `sha256:e7014886d9eec9edb8eb271216280a4fc12ca6347a4410b84856c82aa23e43e7`，构建时间为 2026-11-25 23:47:13 +08:00。Build 基线为本节 HEAD 和当时的未提交源码副本，容器内验证包含新增 Artifact History 和 Fleet 页面。

Backend 与共供 Agent API、Worker 和 Usage Worker 的 Agent 镜像未生成。Engine 29.1.3、Compose 2.40.3。PowerShell 能解析 Docker Hub 并通过 TLS 获得 Docker Hub、GHCR 匿名令牌端点的 200。Docker Engine 两次 Compose 构建和两次直接拉取都在 Docker Hub Python 镜像或 GHCR UV 的令牌和 manifest 请求遇到 EOF。独立 Admin 构建成功，Backend/Agent 没有用缓存应用镜像替代。

## 3. Docker Compose 部署结果

独立项目使用单独生成的环境和测试凭据，`docker compose config --quiet` 通过。Backend/Agent 镜像受仓库访问失败阻断，完整栈未启动。Admin 新镜像以无网络容器核对源文件，不能作为同源登录端到端验收。

## 4. PostgreSQL 验收结果

独立 Docker PostgreSQL 16，随机测试密钥、回环动态测试端口范围，库名 `phase3accept`。Windows Agent 进程使用测试 DSN 执行 `alembic upgrade head → downgrade 0004_agent_management → upgrade head` 成功，包括新增 `0006_config_fencing`。Phase 3.1 管理配置 7 个测试在 PostgreSQL 通过，覆盖审批、fence、Prepare、旧版本接管、发布回滚和并发领取。该轮迁移往返使用空表，存量行保留需追加专项；应用桥接以合成行核验业务表内容。测试数据库容器已停止。

## 5. Provider 真实诊断及凭据轮换

缺少可确认归属的专用非生产诊断及轮换凭据。测试使用 Phase 2 注入的受控 Provider 替身，验证固定请求、响应及异常处理、预算、凭据脱敏和审计。本次未调用真实 Provider，未执行凭据轮换。

## 6. 新旧 Worker 并行运行

独立 PG 验证匹配和不匹配的 Worker 证据、版本分组、新旧 Task、过期恢复与并发领取。Worker 进程跨容器并行、各自独立的工具/技能制品、网络恢复和重启后的真实上报均待新 Agent 镜像构建后验证。

## 7. Worker 故障恢复与结算连续性

独立 PG 验证模拟 Lease 到期、旧 Execution 密封、兼容 Worker 接管、Worker 失联阻断以及发布和回滚对账。Backend/Agent/Usage 跨容器重启、网络断开、完整 Usage Outbox 恢复和 Token 不重复结算仍缺部署证据。

## 8. 跨服务发布协调

Agent 现有 CAS、配置指针和操作回执继续保留。新发布递增 fence，持久化全局准入暂停及归属，Stage 完成后 Backend 重新读取权益影响。Backend 在独立 HMAC 审计中封存 Prepare，包含发布 ID、对账请求 ID、目标、fence、验证和影响摘要、时间。Agent 同事务校验 Prepare 绑定和有效期、暂停、存量任务及新鲜 Worker 证据，持久化本次 Prepare 和切换回执。失败保持可查询状态。没有分布式事务。

部分完成。Backend 的 Prepare 保护重放和操作归属，Agent 暂停保护新 Task。套餐发布和权益数据库仍可能并发推进，Backend 预检之前已进入的请求仍可能产生 Grant。缺少跨进程准入屏障和权益写入快照版本，不能声称消除所有快照竞态。

## 9. Fencing Token 与 Reconciler

`0006_config_fencing` 保存单调递增令牌、暂停操作 ID 和原因。只有当前发布及令牌可以确认、暂停或切换。合法终态只释放本次发布拥有的暂停。持久化暂停可跨重启恢复。原操作 ID 的回执可重查，未知结果保留，证据变动可由下一次新对账请求复核同一发布。升级前遗留的无令牌发布须先暂停，再重新发起。

独立 `app.services.agent_config_reconciler` 轮询 Agent 状态和 Backend 封存审计并报告不一致。它是只读观察器，实际复查与恢复由管理入口触发。Worker Manifest 沿用可验的精确版本证据，尚缺逐次发布 nonce 的 Worker 上报协议和自动恢复。

## 10. 多阶段审批

新增 Admin 审批入口和回执，记录创建者、审批身份、发布身份、审批依据、时刻、验证摘要和目标修订。开启 `AGENT_CONFIG_REQUIRE_SEPARATE_APPROVAL` 后，审批者必须与创建和发布主体分离，重新验证或改修订需重新审批。生产示例开启该约束。现有生产部署约定为单人 SSH 入口，需要部署具备彼此独立且可验证的现有 Admin 主体后再启用高风险写入。

## 11. Tool 历史 Schema 对比

修订可绑定内容寻址的 Tool 元数据。经摘要认证后提供历史 Schema、Description、实现和依赖摘要。修订页可比较两个版本的参数新增、删除、类型、required、默认值、枚举、约束和描述变化。没有历史制品的版本显示 unavailable。未执行历史构建批量导出或回填，版本发现仍通过修订列表。

## 12. Skill 历史预览

只读取修订登记的 Skill ID 和摘要目录，完整复核资源集。SKILL.md 与 references 作为纯文本展示。Scripts 只列文件名、大小及哈希。浏览器使用资源摘要选择文件，禁止任意路径、链接和超限资源，支持文件变化比较。Worker 加载证据沿用 Manifest 视图。

## 13. Skill 脚本执行

实际执行阻断。已有 Skill 资源清单、静态大小/路径/摘要检查和只读文本，未接入具备安全保证的独立执行器。未来执行入口应提交签名制品摘要、脚本摘要、操作身份和限额给独立执行服务。其宿主应隔离网络、凭据、挂载与 Docker Socket，限制 CPU、内存、进程、时间和输出，结束后销毁运行环境并返回脱敏回执。现有 Runtime 的动态加载和工作区工具不作为这类执行的隔离边界。

## 14. Worker Fleet 历史

新增保留 Manifest 的分页视图，按 Worker、Build、配置修订和最近观察时间筛选，可比较两条 Manifest 的能力变化。显示可关联的当前实例、健康和 Run，沿用 Phase 2 清理期限。完整历史实例首次注册、上下线/故障事件和历史 Run 关系尚未持久化。

## 15. Deployment Adapter

新增 Compose 发布计划适配器，限定隔离项目和明确的独立 Worker 服务，提供验证、Prepare、部署命令预览、状态命令、对账、暂停和回滚计划。当前为 Dry Run。实际挂载制品、分批部署和超时恢复由部署人员执行，Runtime 与 Admin 进程没有部署执行权限。

## 16. 两条历史基线失败

- 模型预算断言在原行为下失败。提交 `b96bbd4` 明确移除额外单次输入门槛。原用例输入估算 300005、可用额度 200000，应返回 `QUOTA_EXHAUSTED`，请求仍在预留前被拒。
- 同步结算用例的“未收到确认即全局拒绝下次调用”断言与 `d85b0f6` 已明确取消的 Owner 串行门禁冲突。保留首次未确认用量的原 Outbox 和预留，后续调用仍按现有 Permit 预算准入。新断言检查未确认时 used/held、两次重放原观察后仅入账一次，并确认新 Permit 仍按余额拒绝超额度请求。两项均只修正测试，不改变权益与结算业务逻辑。真实跨容器恢复仍为上线门槛。

## 17. 回归

- Windows Admin `pnpm run build` 通过，包括 tsc。
- Backend `uv run --locked --with pytest --with aiosqlite python -m pytest` 运行 Admin、审计、权益及 Gateway transport，共 20 项通过。
- Agent 管理、Chromium、套餐和 A-line 持久化综合运行 77 通过、1 失败，另有 9 个子用例通过。唯一失败是测试新增的额度边界断言。修正后，两个基线专项重跑 2 通过。PostgreSQL 专项 7 项通过。
- 原 Admin 登录、原能力和用户接口、套餐预览/发布/分配、迁移预览、审计和模拟计量沿用现有测试。真实历史数据和完整跨容器结算没有获验收。

## 18. 安全审查

Admin 继续使用 Cookie、CSRF、独立角色和同源代理。配置写入与报告凭据分离，候选进程拒绝正式 Task，历史制品预览纯文本，普通请求无法提供宿主文件路径。HMAC 审计、幂等冲突及旧发布拒绝均经过代码或测试检查。生产配置未接触。四项写入、准入预检和强制调度默认值在源码示例中为 false/false/false/off。

## 19. 变更

- 契约、Agent 协调与配置 API、Backend Prepare 和管理审计、独立观察器。
- Agent 新迁移 `0006_config_fencing`、Artifact History、Fleet History。
- Admin 配置管理中心、制品浏览、Fleet 浏览、审批和暂停状态。
- 隔离 Compose Dry Run 部署计划、两处环境示例、专项回归与本报告。

## 20. 未完成项与阻断

Docker Engine 能访问部分 Docker Hub 镜像。当前 GHCR UV 和 Docker Hub Python 拉取仍出现 EOF。真实 Provider 与凭据轮换缺专用凭据。完整跨容器故障注入与生产多主体审批部署缺环境证据。仍有权益快照竞态、定期观察后自动恢复、Fleet 历史事件和安全脚本执行缺口。

## 21. 生产开放门槛矩阵

| 门槛 | 结果 |
| --- | --- |
| 新源码镜像、完整 Compose | Admin 构建通过，Backend/Agent 与完整部署阻断 |
| PostgreSQL 与迁移 | 通过专项及空库迁移往返 |
| 真实诊断、凭据轮换 | 待专用测试凭据 |
| 跨容器新旧 Worker、故障恢复 | 待新 Agent 镜像 |
| Task、Lease、发布及回滚 | 独立 PostgreSQL 专项通过 |
| Usage Outbox、Token 结算 | 合成服务验证；真实跨容器证据待补 |
| 跨服务发布、部分成功与对账 | 代码和部分故障验证，隔离栈与跨库快照竞态未关闭 |
| 独立审计 | 桥接和篡改检测通过 |
| 原 Admin 回归 | 原接口测试通过，真实部署全量待验 |
| 历史两条失败 | 溯源为测试预期过时，已更新 |
| 生产安全开关 | 源码示例默认关闭 |

## 22. 最终验收结论

四项收尾工作尚未全部完成。发布协调具备可恢复的手动对账路径，Tool/Skill 历史预览与对比已接入，Fleet 历史为保留 Manifest 版本投影。脚本执行、跨容器多 Worker 和完整结算连续性未获得证据。当前未达到 Production Readiness Candidate，生产写入与强制兼容调度继续关闭。
