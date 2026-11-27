# Agent 消息 Block 展示验证（2026-11-26）

分支：`feat/agent-message-blocks`。本次仅实现 Web 的 MarkdownBlock、消息元数据和参考来源展示，未实现其他具体 Block，未提交代码。

## 实现范围

- MessageRenderer 处理消息组织、秒级时间戳转换和状态；BlockRenderer 分发类型，未知类型保留前后正文并显示占位。
- MarkdownBlock 适配已有消息协议，调用迁入 Agent Feature 的 StreamdownRenderer。全局 Markdown/LaTeX 工具继续复用。
- 通过 Markdown AST 将正文 `[[cite:id]]` 转为数字角标，与本消息内来源条目关联。保留代码、公式和原链接语义，处理 Streamdown 的安全锚点前缀与未闭合链接修复，避免分片 ID 闪现。
- 来源列表显示已有标题、类型、作者、年份、venue、DOI、URL；缺失作者不补造，来源网址可提供域名说明。外链限制为 HTTP(S)，缺失字段省略。
- 深知 AI 和论文问答接入共用消息组件，结构化回复隐藏旧正文与旧来源的重复展示；思考、工具、报告、反问和旧会话仍走现有路径。
- Client 对未来未知 Block 保留原始字段并安全降级，已知 Markdown 仍严格校验。

## 验证结果

- Web 全量测试：465 项通过，0 失败；包括协议、SSE 解析、会话组装及 6 项展示规则测试。
- `pnpm typecheck` 与改动 Web 文件的 ESLint 通过。
- 独立 Next 开发服务 + 本机无头 Edge + mock Backend 的真实 HTTP/SSE 浏览器联调通过：
  - 引用跨 delta 尚未闭合时隐藏，完整后显示对应角标。
  - message_end 前已能显示正文、表格、公式和未闭合代码块。
  - 最终快照不重复追加正文，来源字段与角标跳转正确，内部标识不显示。
  - 刷新页面恢复同一历史消息，无需重新运行 Agent。
  - 390px 手机布局无页面/消息水平溢出。
  - 旧会话可读，未知 Block 不影响前后正文，不安全来源链接与 HTML 不执行。
  - 浏览器运行时错误为 0。

浏览器脚本为 `tests/visual/agent-message-blocks.mjs`，生成 `result.json`、`message-streaming.png`、`message-desktop.png`、`message-mobile.png`，保留隔离浏览器目录。运行方式见 [消息协议维护说明](../../../agent/message-blocks.md#验证)。

本次浏览器联调验证真实 Web Client → SSE → 状态 → DOM 和历史读取，Backend 响应由可复现 mock 提供，未调用真实模型，不代表生产环境验收。
