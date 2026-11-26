# Agent Management Console

## 当前入口与职责

Admin 的 `#/agent` 统一提供 Provider、Model、Tools、Skills、Worker、Task / Run、告警、配置和管理审计。旧 `#/capabilities` 映射至 Provider 目录。Backend `/api/v1/admin-console/capabilities` 继续服务既有套餐发布调用方。

Admin 只访问同源 Backend。Backend 负责管理员认证、审计、权益和跨服务调用。Agent 输出 Registry、Skill Store、运行数据库及 Worker 的真实证据。API Registry 与 Worker 进程分别展示来源和配置修订，多版本差异通过 Worker Manifest 核对。

## Provider / Model 表单

配置中心从完整 Spec 导入或基于已有修订创建候选。表单覆盖 Provider ID、协议、HTTPS 地址、Secret Reference、模型内部和上游 ID、名称、Brand、启停、默认用途及 Capabilities。JSON 高级入口保留。表单只更新目标字段，Tool / Skill 制品引用和未编辑字段随原 Spec 保留；服务端 Strict Contract 对不支持的字段明确拒绝。

先执行“检查依赖并预览”，核对新旧 Spec、默认用途、引用 Policy / Owner、未关闭 Grant 和持久化 Task 的模型引用，再创建不可变修订。当前部署之外的客户端引用显示 unknown。内部 Model ID 改名需要管理员迁移这些客户端，旧修订与旧 Worker 供存量任务使用。

发布继续要求隔离证明、审批、兼容性校验及指定 Worker 确认。已有配置写开关、CAS、fencing、权益屏障和对账机制继续生效。表单保存不会直接更改运行中的 Registry。

## 运行能力证据

Worker 在认证上报中提供指定 Run 的 enabled / latent 工具集合。Agent 只接受当前 Worker 持有有效 Run Lease 的运行投影，将 Run、Worker、实例、Manifest 和采样时间持久化。旧 Worker 未提供 latent 集合时保留 unknown。

Tool 详情可输入 Run ID。Loaded 来自新鲜运行上报。Run Callable 的肯定证据来自该 Run 当前 Execution 中已发生的调用 start，展示调用 ID 和观测时间；该结果表示观测时已获准启动。未来调用仍需现有 Permit / Start 门禁。未启用工具显示不可调用，陈旧证据和缺少调用授权事实时保持 unknown。

Skill 展示受控 Metadata、声明的 references / scripts / dependencies、资源完整性和当前资源版本对应的激活上下文。Worker 版本列表及 Manifest 比较用于定位差异。脚本和第一方工厂执行资格分别处理，检查接口不执行任意 Skill 脚本。

## 健康检查

`POST /agent/checks/summary` 批量读取已保存检查。Backend 一次查询目标集合，Agent 一次提供当前身份摘要。版本不匹配或检查过期显示 stale，缺少证据显示 unknown。查询本身不会触发 Provider 请求。

检查继续采用 pass / fail / unknown / unsupported。`coverage` 补充 complete / partial / unknown，历史结果缺省为 unknown。静态检查通过且存在缺少声明、无新鲜 Worker 等未知步骤时，页面说明覆盖不完整。

Provider / Model 检查支持静态、网络、Completion、Streaming 和 Tool Calling。在线检查使用独立探测 Key，结果只证明对应探测凭据。Tool 检查验证 Schema、工作区可读、搜索配置或 Skill Store 等安全依赖。科研上游未实际验证时保留 unknown，需要请求上下文或业务副作用的探测返回 unsupported。

## Worker 巡检与 Drain

迁移 `0008_management_operations` 添加运行证据、Worker 控制、告警和幂等操作四张表。API 进程配置 `AGENT_MANAGEMENT_INSPECTOR_ENABLED=true` 后每十秒检查心跳。阈值沿用已有 stale / offline 配置。

失联事件和告警按 Worker、实例和最后上报序号去重。恢复或新实例上报更新恢复证据。管理员可以确认告警，恢复后的告警可关闭。历史生命周期和操作审计保留各自证据。

Drain 在服务端领取事务中检查，覆盖新任务和过期 Lease 接管；已运行任务继续执行。状态包括 accepting、draining、drained 和 timed_out。超时后保持拒绝领取，需要管理员显式恢复。已过期但尚未结束的 Run 继续计入存量运行，避免过早宣布排空。

PostgreSQL 使用按 Worker 的事务锁串行化 Drain 与领取，巡检、上报及幂等操作另以共享的管理写锁协调。恢复接收任务和 Drain 均走独立配置管理凭据及管理员审计。

## Task / Run 控制

管理员取消请求经 Backend 核对目标 Task 和可信 Owner，再调用既有 Agent Gateway v2 取消接口。Run 控制仅允许当前 Run。Queued 可直接进入取消终态，运行任务等待 Worker 心跳和停止流程确认。接口成功表示请求被接收，页面以 Task 终态、Execution 和用量结算确认结果。

请求携带操作 ID 和原因。网络结果不明时沿用原请求重试。取消不释放未知用量，不新建执行或重置计量事实。awaiting_input 状态在既有取消协议中结束 Task，保留已封闭 checkpoint Run 的原始报告。

人工失败重试暂不开放。已有自动重试属于原执行协议。未来人工重试应创建新的提交身份并重新授权，明确副作用、Owner 幂等键、Grant、旧 Execution 密封和未决用量，禁止重置旧 Run 或复用已消费 Permit。接口设计应包含 source_task_id、expected_terminal_revision、operation_id、reason，并在重试资格响应中逐项说明未决结算及副作用证据。当前管理接口无 retry 动作。

## 独立审批

生产继续启用 `AGENT_CONFIG_REQUIRE_SEPARATE_APPROVAL=true`。单个 SSH 管理员提交独立审批者签名的 `external_proof`，Agent 使用部署固定的 Ed25519 公钥验证。签名绑定目标修订、validation ID、validation digest、审批身份和时间，一小时有效。审批记录分别保留签名者和提交者。

`AGENT_CONFIG_APPROVER_PUBLIC_KEYS` 为审批者 ID 到只读公钥文件的 JSON 映射。审批私钥由独立审批者在独立设备保管，使用 `apps/agent/scripts/sign_config_approval.py` 对已审阅的验证摘要签名。管理端只接收证明，Agent 仅部署公钥。部署人员仍需落实私钥保管与人员独立性。

## 迁移与回滚

先部署迁移 0008，再启动新版 API、Worker 和巡检器。旧 Worker 可继续上报，新字段缺省不改变历史请求摘要。旧审批请求未带外部证明时保留原序列化形式。

回退应用前停止新的运行管理操作和巡检，显式解除仍需保留的 Drain 控制并导出管理证据。确认新版进程全部退出后，可 `alembic downgrade 0007_worker_lifecycle`。该降级移除四张管理表，原 Task、Run、Execution、调用和用量表保持。重新升级可恢复结构，已删除管理历史需由备份恢复。

生产入口、SSH、Secret 注入和轮换见 [部署说明](../../infra/docker/ADMIN.md)。一次性验证结果置于 `docs/dev/records/agent/`。
