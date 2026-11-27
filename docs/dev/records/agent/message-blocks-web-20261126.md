# Web 结构化消息数据层验证

日期：2026-11-26。分支：`feat/agent-message-blocks`。基线：`e40a3d0`。未 commit。

## 范围

接入 Client 协议类型与校验、六类 SSE 消息事件、Block/Reference 组装、最终快照校准及历史会话恢复。深知 AI 页面与论文问答共用纯组装器。页面 JSX、Renderer、正文与引用展示未改；没有定义其他具体 Block 类型，没有新增依赖或修改锁文件。

当前实现约定见 [消息 Blocks](../../../agent/message-blocks.md#web-数据层)。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| 新增协议、状态和 mock Client 测试 | 14 passed |
| `pnpm test` 完整 Web 测试 | 459 passed，0 failed，0 skipped |
| `pnpm typecheck` | 通过 |
| 本次改动 TS/TSX 文件的 ESLint | 通过 |
| `git diff --check` | 通过 |

首次在沙箱内执行完整测试时，原本的本地 HTTP mock 测试因 `connect EACCES 127.0.0.1` 失败；移到沙箱外运行后完整测试通过。没有调用真实 Agent、模型或知识服务。

## Mock 测试覆盖

`tests/agent/message-fixtures.ts` 提供与当前协议一致的 Metadata、两个顺序 Markdown 块、独立 References 及六类事件。fixture 包含重复引用、代码、表格、公式、中文、Unicode、CRLF、尾部空格、显式 null、可选字段缺失和嵌套 metadata。mock ReadableStream 将真实 UTF-8 字节切成 1–5 字节碎片，使用 CRLF、多行 SSE data 和心跳注释。

`tests/agent/message-blocks.test.ts` 验证：

- 协议校验与完整载荷保留；非法字段、版本、重复 ID 和悬空引用拒绝。
- 在 `message_end` 到来之前，Block 内容、顺序和 References 已正确组装。
- 相同事件 ID 及前缀重放不重复追加；重试切换 Run 不继承旧块。
- 引用更新保持位置；引用标记可跨 delta，来源可晚于正文到达。
- 错误关联和顺序保留有效内容，合法最终快照恢复一致状态。
- 五种终态快照替换部分状态；null/缺失的旧格式结果保留已有内容。
- 论文问答复用相同组装器，原正文逻辑保持原样。

`tests/agent/message-stream.test.ts` 验证：

- mock fetch → 通用 SSE 解析器 → Agent Client → Feature 状态的完整链路，覆盖 Session POST、GET 重放和无状态运行。
- SSE ID 保留，重复 delta 不重复追加，旧正文和思考事件不混入 Block。
- mock 历史 HTTP 响应恢复出与实时流一致的消息，旧会话 null/缺失字段兼容读取。
- EOF 或非法事件不会清空已组装的内容，只有 `result` 才结束产品流。
- 单独收到最终结果时仍可恢复完整消息，五种终态均保留原快照。
- API v2 事件外层版本不会改变内层消息。

未进行浏览器 Block 渲染或真实服务联调；它们不属于本轮测试目标。
