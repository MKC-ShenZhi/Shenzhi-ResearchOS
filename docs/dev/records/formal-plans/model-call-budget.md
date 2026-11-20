# 单次模型调用预算改造交付（2026-11-20）

## 实现与边界

正式套餐生成器移除 --call-upper-bound，改为可选 --model-budgets 部署审批文件。Basic/Pro/Research 仍只区分每日额度与既定 deep-research 权限；每日规则兼容字段 reservation_units/call_upper_bound 写0，dynamic_model_budget=true 时不将0解释为免费，而由模型预算协商产生正数 Token 预留。历史 Policy 不原地更新。

共享协议新增可选 ModelCallBudgetRequest/Approval，贯穿 Worker CallIntent、Control CallPermitRequest、Backend Permit、Control 唯一 start 回执。请求携带完整正文 input_bytes、请求输出上限、Agent 模型输出上限/上下文（未知为null）及明确风险 basis。Backend 在既有 owner→grant 锁下读取共享每日余额，验证原风险 profile 与逐模型审批约束，计算输入风险预算 I，再批准 O=min(请求输出、Agent模型输出、审批模型输出、上下文余量、每日余额-I)，O必须大于0，原子预留I+O。申请、批准和持有量保存在原 CallPermit JSON 与追加账本，无新数据库表/迁移。

输入风险策略 risk_assessed_utf8_v1 使用完整正文（消息、工具Schema、思考参数等，不含协商max_tokens）的UTF-8字节数加审批封装余量；它不是严格Token上界，也不伪造 input_bound_evidence_ref。没有独立 model_risk_profile/审批仍是 TOKEN_BOUND_UNPROVEN；缺逐模型约束拒绝 MODEL_BUDGET_UNCONFIGURED，输入预算装不下则 MODEL_INPUT_BUDGET_EXHAUSTED。启用风险 profile 时生成器要求所有公开模型均有审核后的约束。

只支持被部署负责人确认 max_tokens 覆盖所有 completion（含思考Token）的 Provider。不能确认此语义时，不得配置该模型的预算审批。模型上下文没有编造默认值；Registry 可选 context_window_tokens，未知时以审核配置为限制。字节估算/Provider不遵守限制仍存在超额风险，沿用完整记录、保留Unknown/Partial与record_and_block；不承诺数学意义的绝不超额。

Worker 先核对 Permit 批准结果再 start，Provider 将 max_tokens 设为批准O；发送前 guard 再核对请求正文摘要、实际max_tokens与唯一发送权。动态摘要定义为 body_without_max_tokens，正文摘要和批准O共同绑定最终请求。外层重试、参数降级及摘要都经过同一发送边界，构造新Intent/Permit，不复用发送权。审批后的参数不一致则拒绝，不能靠Provider重试绕过。

历史模式通过签名 Grant.execution_constraints 区分；仅新Grant含 model_call_budget=dynamic_v1。旧Grant仍使用原固定预算与原风险语义，不提升授权，也不原地换成新模式；旧模式不具备新动态保障。新字段为None时从序列化中省略，保存的历史Intent/Permit/Usage不重写。部署需排空旧任务或保留对应Worker版本，最终源码变化后重新导出能力身份并发布新的不可变版本。

## 本次实际修改文件（此前工作区改动保留）

- packages/agent-contracts/src/agent_contracts/v2.py
- packages/agent-contracts/src/agent_contracts/execution_v2.py
- apps/backend/app/services/agent_entitlements/policy.py
- apps/backend/app/services/agent_entitlements/service.py
- apps/backend/app/services/agent_entitlements/plans.py
- apps/backend/app/services/agent_entitlements/admin.py
- apps/agent/src/agent_app/api/v2.py
- apps/agent/src/agent_app/control/metering.py
- apps/agent/src/agent_app/execution/metering.py
- apps/agent/src/agent_app/integrations/llm/registry.py
- apps/agent/src/agent_app/integrations/llm/agent_stream.py
- apps/agent/src/agent_app/worker/host.py
- apps/agent/tests/unit/test_metering_boundaries.py
- apps/agent/tests/test_a_line_persistence.py
- apps/agent/tests/test_formal_plans.py
- apps/agent/tests/integration/test_formal_plans_postgres.py（仅同步动态请求fixture，本次未执行PG）
- apps/admin/README.md
- docs/agent/entitlements.md
- 本记录

## 直接相关测试结果

在 apps/agent 执行：

```powershell
uv --cache-dir .uv-cache run --no-sync python -m pytest tests/unit/test_metering_boundaries.py tests/test_formal_plans.py tests/test_a_line_persistence.py -k "MeteringBoundaryTests or FormalPlanTests or http_submit_permit or http_dynamic_budget" -q
```

25 passed, 29 deselected。包括动态实际HTTP MockTransport输出参数、重试/参数降级/摘要逐次授权、无审批/缺模型配置拒绝、超过16K调用、剩余额度缩减、Unknown/Partial保留、历史HTTP链路与套餐权限。

```powershell
uv --cache-dir .uv-cache run --no-sync python -m pytest ../../packages/agent-contracts/tests -q
```

15 passed，19 subtests passed。

最后收紧生成器要求风险profile覆盖所有模型，并使历史HTTP fixture显式沿用签名模式后，仅重跑套餐与HTTP子集：14 passed, 29 deselected（与25项重叠，不累计）。命令为上面第一条去掉unit文件，-k使用 "FormalPlanTests or http_submit_permit or http_dynamic_budget"。git diff --check通过，仅已有换行提示。没有运行全仓库测试或真实Provider；本次没有重跑PostgreSQL集成。

## 发布验收结论

可进入功能发布验收；不能直接视为生产授权已获批准。上线前须提供真实逐模型预算风险约束和批准引用，确认Provider的上下文/max_tokens/思考计量语义，在最终Worker版本重新导出能力、以新revision经Admin发布并在受控环境验收。未完成这些条件时模型门禁保持拒绝。未修改真实用户权益、未发布Policy、未提交或推送代码。
