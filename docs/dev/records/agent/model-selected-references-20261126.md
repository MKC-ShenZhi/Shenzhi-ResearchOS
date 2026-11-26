# 模型选择来源与 JSON 输出拆分（2026-11-26）

分支：`feat/agent-message-blocks`。本轮不提交代码，不修改检索策略、Backend 数据库或 AIMessage/SSE 公共协议。

## 行为

- 模型直接输出 Markdown 正文，用局部 `[[cite:r1]]` 标记实际引用；末尾通过 `<references_json>` / `</references_json>` 包裹独立 JSON 数组。
- Agent Service 流式拆分正文和 JSON，校验 Reference 字段，生成正式来源 ID，映射正文标记、去重和补全来源。只接受正文实际引用的 JSON 记录。
- 工具结果仍是证据输入，不自动决定参考列表；历史资料可由模型在当前输出中明确声明引用。
- 正文 delta、MarkdownBlock、final_text 不包含来源 JSON。Provider transcript 保留原始模型输出供上下文使用。
- Web 跨 Block 按正文首次引用编号。JSON 晚到时显示待补全数字角标，来源到达后可跳转；未引用来源不展示。
- JSON 格式错误、缺失、截断、超限或引用无法解析时保留有效正文，最终快照将无效引用降级并记录诊断。终态快照可校准流式引用别名合并结果。

模型声明引用与程序结构校验不等于自动核实论文真实性或论点支持度；本轮不新增该类审查。

## 验证

- Agent 本次相关的 24 项测试在只读挂载源码、无网络的 Linux 隔离容器中通过。
- 同组测试加并行执行耗时断言在 Windows 单独复测：25 passed，5 subtests passed。
- Web 全量测试、类型检查、相关 ESLint 通过，覆盖首次引用排序、来源反序到达、待补全角标、未引用来源过滤及嵌套列表。
- 无头 Edge 浏览器联调通过：来源晚于正文、来源数组与正文顺序不同、未引用条目、角标跳转、历史刷新、390px 布局及兼容降级。浏览器运行时错误为 0。
- 使用脚本化 Provider 和 mock Backend/SSE，未调用真实模型。

## 全量 Agent 基线

HEAD `5ba7a3a` 的未修改快照与当前代码均执行测试，以区分已有问题：

- Linux 单元测试：HEAD 239 项与当前 248 项具有相同的 6 个 failure / 5 个 error 记录，涉及旧模式预算预期与租约接管。当前新增的 9 项无新增失败。
- Windows 全量 pytest：HEAD 为 13 failed / 279 passed / 59 skipped；当前为 14 failed / 287 passed / 59 skipped。共同失败涉及预算、租约与计量；额外的并行耗时断言单独复测通过。
- Linux 只读挂载最初还导致演示报告无法写入；将测试工作区指向容器 `/tmp` 后按相同配置完成上述基线对比，未修改业务代码。

测试日志和浏览器截图保留为本地验证产物；运行脚本与输出格式见 [结构化消息维护说明](../../../agent/message-blocks.md)。
