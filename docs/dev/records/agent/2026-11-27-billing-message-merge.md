# Billing 与消息 Blocks 合并

将远程 Agent Platform 消息 Blocks 提交 `555e4634` 合入已包含订阅功能的本地分支。

## 合并处理

- Runtime 保留用户停止的正常返回、工具取消标志及 transcript 闭合；外部取消先封存消息和 run_end，再传播 CancelledError。正常执行与超时交付窗口采用相同语义。
- 新增交付窗口内用户停止及外部取消的回归用例，验证部分正文和终态消息均保留。
- 保留已存在的两个 029 revision，以空 DDL 的 `030_merge_billing_message` 收敛迁移图，兼容任一分支已经执行过迁移的数据库。

## 验证

- Agent Runtime、消息 Blocks、模型输出及 Worker 接管：120 passed，19 subtests passed。
- Backend 消息投影、Session、Timeline、契约及支付 Provider：54 tests，OK。
- Web 类型检查通过；独立编译目录运行完整测试：487 passed。
- Alembic heads 仅返回 `030_merge_billing_message`。

默认 Web 测试目录存在已删除源码对应的旧编译测试；独立 `.next/merge-test-output` 编译后重跑排除了旧产物。沙箱限制了本机 HTTP 和部分 Python 测试，相关测试在授权的沙箱外执行后通过。未执行真实数据库迁移、支付调用、浏览器视觉验收或远程推送。
