# Agent 论文检索响应契约修复

日期：2026-11-19。

## 原因

原查询 `knowledge editing large language models`、`topK=10` 经运行中的 Backend 内部检索接口返回 500。单独调用现有 Knowledge Service 成功返回 10 篇论文；将其结果交给 `KnowledgeSearchResponseWire` 校验时，每条结果的 `topics` 均触发 `extra_forbidden`。产品论文 Schema 已包含主题导航信息，而 Agent Wire 尚不包含该字段。论文详情存在同一契约差异。

## 修改与验证

- Backend 的 Agent 内部检索和详情接口在序列化时显式排除 `topics`，保留严格 Wire 校验及产品知识库的主题字段。
- 新增搜索和详情两个 HTTP 契约回归，使用带非空主题的真实产品 Schema，检查响应可通过 Agent Wire 校验、分页与论文信息保留、产品对象未被修改。
- `uv run --locked --no-sync python -m unittest tests.test_agent_knowledge_contract tests.test_agent_api -q`：16 项通过。
- Backend 既有热重载生效后，经运行中的内部检索接口复测原查询：HTTP 200，返回 10 篇论文；首篇为 `Should We Really Edit Language Models? On the Evaluation of Edited Language Models`。

## 独立的任务终止原因

只读核对最近两次失败任务的持久调用记录，最后一笔模型调用均被拒绝，Permit 响应的 `reason_code` 为 `QUOTA_EXHAUSTED`。这与论文检索契约错误不同；当前 Worker 将该类门禁异常统一显示为“调用授权或启动未获可信回执”。本次没有更改配额、Policy、授权规则、Agent 实现或错误展示。未发起新的模型任务，不声称完整对话已重新验收。

没有新增代理配置、手动重启服务或启动隐藏进程。
