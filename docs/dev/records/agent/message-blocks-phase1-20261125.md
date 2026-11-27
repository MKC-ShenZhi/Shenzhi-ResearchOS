# Agent 消息 Blocks 第一阶段验证

日期：2026-11-25。工作分支：`feat/agent-message-blocks`；修改前 HEAD：`f04e01a`。未 commit。

## 范围

实现 Metadata、MarkdownBlock、References 及六类结构化事件。协议模型、消息组装和来源注册分别维护；Worker 保存 `result.message`。当前实现约定见 [消息 Blocks](../../../agent/message-blocks.md)。本轮未接入产品前端渲染。

## 通过的检查

使用 Agent 现有 `uv.lock` 创建独立测试环境（Python 3.14.6），未改依赖清单或锁文件。Windows 沙箱内 asyncio 的 socketpair 创建阻塞，因此异步测试在沙箱外执行；Provider 和外部服务使用 FakeProvider / MockTransport，没有调用真实模型或知识服务。

| 检查 | 结果 |
| --- | --- |
| Agent 新增与直接相关回归 | 109 passed，16 subtests passed |
| 共享契约全部测试 | 32 passed，19 subtests passed |
| Backend Gateway 契约及本地 HTTP 测试 | 7 passed，2 subtests passed |
| `git diff --check` | 通过 |

Agent 检查包含 `test_message_blocks.py`、`test_agent.py`、`test_agent_knowledge_tools.py`、`test_agent_memory.py`、`test_worker_heartbeat.py`、`test_demo_worker.py`，以及 `test_worker_takeover.py::WorkerTakeoverTests::test_normal_worker_starts_at_one_and_completes`。后者经过真实 Agent API、Control SQL 与 Worker，核对持久事件的 `message_end` 和报告中的 `message` 相同。SQLite 不验证 PostgreSQL 并发锁。

新用例检查只允许 Markdown 类型、字段与关联校验、任意字符处引用分片、无效引用降级、搜索/详情来源复用、多个顺序块、事件重建与重复事件去重、最终快照、异常/停止/超时/外部取消、反问、空响应、Checkpoint 恢复及错误来源回喂。

## 全量回归中的既有失败

首次扩大 Agent 回归得到 277 passed、59 skipped、13 failed（含三个子测试失败）。随后将 HEAD 的相关目录用 `git archive` 导出到独立目录，使用相同解释器、依赖与同名测试复跑，以下 13 个失败全部复现；未为修复这些失败修改无关逻辑：

- 快速模式预算/时长：`test_agent_fast_search.py` 的 `test_fast_tools_and_prompt`、`test_mode_budgets`，及 `test_other_modes_keep_full_tools_and_budget` 的 deep/idea/doubt 三个子测试。
- 租约接管：`test_worker_takeover.py` 的 `test_cancel_intent_survives_takeover`、`test_repeated_takeovers_and_heartbeats_do_not_regress_or_duplicate`、`test_stale_token_cannot_publish_renew_or_finish_new_lease`、`test_takeover_uses_max_sequence_instead_of_event_count`、`test_takeover_worker_continues_sequence_and_completes`。
- 任务领取：`test_task_runs.py::TaskRunHistoryTests::test_claim_filters_mock_and_real_runs_including_expired_leases`。
- 结算：`test_a_line_persistence.py::ALinePersistenceTests::test_sync_settlement_requires_backend_ack_and_keeps_original_outbox`。
- 模型输入预算：`test_formal_plans.py::FormalPlanTests::test_dynamic_missing_profile_or_input_room_fails_before_reservation`。

尚未执行真实 LLM、生产数据库与浏览器端验收。
