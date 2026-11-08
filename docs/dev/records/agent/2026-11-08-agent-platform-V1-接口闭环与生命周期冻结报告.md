# 2026-11-08 Agent Platform V1 接口闭环与生命周期冻结报告

## 范围与文件

修改 `apps/backend/app/services/agent_workers/executor.py`、`agent/execution/runtime.py`、`agent/execution/types.py`、`agent_contracts/runs.py`、`apps/backend/app/integrations/llm/agent_stream.py`、`apps/backend/tests/test_agent_contracts.py`，以及 `docs/agent/contracts.md`、`development.md`、`lifecycle.md`。Provider 解析器位于原任务允许目录以外；修改原因是其缺失 usage 字段被转成 0，会污染共享用量报告。只改变不完整 usage 的处理，完整用量仍按原有数值返回；无第三方依赖变更。

## 四个问题

1. **事件**：原先 Worker 不接 EventSink。现在同步回调排队，单一发布协程按 Runtime seq 发送 PlatformEvent；等待发布完成后才返回报告，发布失败会停止 Runtime 并使执行抛错。原始 `turn/name/data` 和 `(run_id, seq)` 保留。接收端持久幂等与重试尚未实现。
2. **报告**：契约明确唯一链路 `execute → Worker Host → RunReporter → TaskManager.record_report → BudgetManager.record_usage`。Fake Control 测相同报告幂等及冲突拒绝。本分支没有生产 Control、Host 和数据库事务，不能宣称生产报告交付闭环。
3. **生命周期**：`lifecycle.md` 冻结排队暂停/恢复、运行中暂停拒绝、等待输入、取消/完成竞争、超时与重试、Run/Turn Lease 权威边界。现有 Session/Turn 一次用户输入对应 Turn；推荐后续回答创建新 Task 并加 continuation，待负责人确认。状态机和 Run Lease 生产实现留给 Control。
4. **预算**：Worker 将显式时长接入 Runtime 单调钟 deadline，禁用宽限窗口；显式工具次数接入 Runtime 派发前预留，严格模式不允许交付工具越额。真实派发次数进入 RunResult/UsageReport，模型用量仅在所有调用均有 Provider usage 时报告。模型 Token 预算因无法可靠预扣而执行前拒绝。完整计费、预算结算和跨进程执行不在本轮。

## 接口变化

`RuntimeDriver.run` 增加同步 `on_event`；`ApplicationWorkerExecutor` 可注入 `EventSink`。`RunResult` 追加 `tool_calls` 与 `usage_measured`，保留原字段与默认值以兼容旧构造调用。`report_from_result` 对未测量 token 写 `None`。无新增公共 Protocol；现有 `RunReporter` 与 `TaskManager` 分工在文档冻结。

## 检查

- `uv run python -m unittest -q tests.test_agent_contracts`：17 项通过。
- `uv run python -m unittest -q tests.test_agent tests.test_agent_contracts`：96 项通过。
- `uv run python -m compileall -q app`：通过。
- `uv run python -m unittest discover -q tests`：641 项，1 失败、7 错误、75 跳过。7 个模型路由错误与本地模型注册表配置有关；深度研究断言的 CRLF/LF 不一致。未据此宣称完整后端通过。

## 尚存风险及并行开发

事件发布没有持久缓冲，网络失败需上层重试整个 Run 或引入可恢复交付协议；内存队列无背压上限。Host、Control 事务幂等、事件唯一约束、Run Lease fencing、状态机与 Session/Task 关联尚未实现。Execution 分支应补强事件传输、Provider 用量完整性、严格预算边界测试；Control 分支应实现报告与用量同事务结算、Run/事件唯一约束、Lease 与状态条件更新。共享接口和职责已足以让两人并行开发，但不满足生产级平台验收。

