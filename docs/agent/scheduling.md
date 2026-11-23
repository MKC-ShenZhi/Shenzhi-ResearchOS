# 用户级调度契约

本文定义 Control 与 Execution 并行开发使用的目标契约。当前实现通过 PostgreSQL Outbox 和 Run 租约派发，尚无独立 Attempt 或跨 Worker 的用户并发限制。现有 /internal/v1 接口按共享契约中的当前行为运行。

## 责任与准入

- Backend 从可信身份解析 owner_id。用户与匿名主体沿用 user:<id> 和 anon:<id>；Worker 不提供或更改归属。引入租户后由 Backend 提供可信 tenant_id，缺失时不从用户 ID 推断。
- Backend 负责用户额度预留和 BudgetGrant；Agent Control 负责排队和执行槽位。预算授权与并发槽是独立条件。已有同键同请求先返回原 Task，不重复排队或占槽；同键不同请求返回 409。
- Scheduler 同时检查全局、owner、可用时的 tenant，以及任务类型上限。队列容量和执行并发分别配置。提交时若触及队列上限，可用 429 拒绝新任务且不创建记录；已经受理的任务遇到并发上限则保持排队。
- 同一主体内按可调度时间、入队顺序、稳定 ID 排序。跨主体优先选择最久未获派发且有可运行任务的主体；跳过达到上限或仍在退避的主体。限额数值及负载参数由部署配置决定。

## Control 与 Worker 的交接

| 操作 | 输入与结果 |
| --- | --- |
| 领取 | Worker 提供 worker_id；Control 选出兼容的 Run，在同一事务中检查并预留各级槽位、创建 Attempt、分配递增 fencing token。成功返回 RunRequest、attempt_id、lease_token、lease_expires_at 和可选 checkpoint_ref；当前无可领取任务时返回空结果。 |
| 续租 | Worker 提交 run_id、attempt_id、worker_id、lease_token；Control 使用数据库时间校验当前有效租约并返回 active、cancel_requested 和有效时的 lease_expires_at。失去执行权时 Worker 停止并丢弃后续写入。 |
| 事件、检查点与报告 | 每次执行写入均绑定同一 Attempt 与 token；持久化边界拒绝过期或非当前 Attempt 的写入。已受理的相同终态报告允许幂等确认，冲突报告返回 409。Worker 提交执行结果，由 Control 决定状态与是否重试。 |

并发计量以未过期的有效 Attempt 为准。领取检查与预留必须原子化，重复派发和并发领取不能重复占用槽位。队列通知仅表示有候选任务，不能授予执行权。

## 释放、取消与恢复

- 排队取消直接结束 Task 并使派发记录失效。执行中取消先记录意图，Worker 通过心跳感知；槽位保留至终态确认或租约过期。取消意图已经生效的 Run 不再派发新的 Attempt。已提交的终态保持不变。
- 完成、失败或进入等待用户输入时，Control 在状态更新事务中释放槽位。等待回答不占执行槽；有效回答只受理一次，原 Run 重新排队并重新竞争槽位。
- 租约到期后回收槽位并隔离旧 Attempt。可安全恢复且未超出重试限制时，原 Run 按退避重新排队，领取时生成新 Attempt。缺少安全恢复点或工具副作用未知时，进入明确的中断或人工处理状态。

验收应覆盖：多个 Worker 竞争最后一个槽位；达到用户上限时其他用户仍能领取；重复派发不创建第二个有效 Attempt；Worker 崩溃后槽位回收且旧 token 写入被拒绝；取消、完成和过期竞争时只释放一次；等待输入和退避不占槽。
