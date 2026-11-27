# AI 回答选区引用 V1 验收

分支：`feat/agent-platform`。实际主对话 Feature 是 `apps/web/features/agent-chat/`，旧 `features/chat/` 已移除。

## 实现

- `components/selection-quote-action.tsx`：通过 `selectionchange` / `pointerup` 检测原生连续选区，检查 Range 两端属于同一个 `data-quote-source`，排除表单、按钮及可编辑区域；用消息 ID 与完整选中文本保存候选草稿。
- 按钮通过 Portal 使用固定定位，依据选区矩形计算位置并限制在视口内；滚动、缩放、外部 pointerdown、Escape、窗口失焦时隐藏。监听按帧合并，卸载时清理监听和待执行帧。
- 点击按钮前阻止 pointerdown 默认行为以保留选区；点击后使用保存的文本写入既有 `quote`，显示既有可取消引用条并聚焦 Composer，不发送消息。
- `shenzhi-ai-page.tsx`：移除自动写入引用草稿的 mouseup；回答标记携带当前 turn ID；复用现有 `send → runPrompt` 与会话 API。运行中的引用同样由既有 `steerAgentRun` 发送。引用文本完整传递，移除旧前端 2,000 字截断，不更改服务端输入限制。
- `tests/visual/agent-message-blocks.mjs`：沿用现有真实 Edge + Next + HTTP/SSE Backend 替身，增加交互及实际请求体断言。

## 检查结果

- `pnpm typecheck`：通过。
- `pnpm lint`：0 错误；原有 `lib/use-popover-placement.ts:37` 有一个 `anchorRef` 依赖警告。修改文件定向 ESLint 通过。
- `pnpm test`：491/491 通过。沙箱内首次运行有一项回环网络 EACCES；沙箱外重跑全部通过。
- `node tests/visual/agent-message-blocks.mjs --next http://127.0.0.1:3311 --out <临时输出目录>`：通过，浏览器异常为零。Next 和 Edge 因沙箱 junction / 调试管道限制在沙箱外运行。
- `git diff --check`：通过。

| 场景 | 结果与证据 |
| --- | --- |
| 选中文字不直接追问 | 通过；无引用条且请求数未增长 |
| 有效选区显示按钮 | 通过；选区几何位置及视口边界断言 |
| 按钮确认引用 | 通过；真实鼠标事件后引用条文本与原 Selection 一致，输入框获得焦点 |
| 连续多段 | 通过；两个段落全文进入引用草稿与最终 POST prompt |
| 选区变更、单字与键盘确认 | 通过；原生 Selection.modify 扩展触发更新，按钮 focus + 真实 Enter 激活；未依赖 mouseup |
| 跨当前消息边界 | 通过；Range 结束位置越过消息容器后按钮消失 |
| 点击外部 | 通过；外部 pointerdown 后按钮消失 |
| 清除选区 | 通过；removeAllRanges / collapse 后按钮消失 |
| 普通复制 | 复制快捷键事件未改变选中文本；实现未拦截 copy / Ctrl+C，未读取系统剪贴板 |
| 输入框选区 | 通过；Composer 及嵌入回答区域的 textarea 均不显示按钮 |
| 滚动 | 通过；捕获滚动事件后按钮隐藏 |
| 编辑、确认发送 | 通过；按钮确认不发送，输入问题后点击原发送按钮，替身收到完整引用 prompt |
| 多轮 | 通过；引用发送完成后再次发送普通问题，未携带旧引用 |
| 运行中引用 | 通过；原 steer 端点收到完整引用与追问，成功后引用条清除 |
| 移动端 | 390px 视口边界断言通过，截图人工检查按钮无溢出 |

不涉及后端、数据库、模型调用或 API 契约修改，也未新增依赖。浏览器闭环使用确定性 Backend 替身，未调用真实模型。系统剪贴板写入和不同浏览器的物理 Shift+方向键操作未手工验收；原生 selectionchange 更新及按钮键盘确认已覆盖。当前无已知功能阻塞。

## 后续调整：引用上下文与用户问题分开展示

用户反馈：发送后把内部拼接的 prompt 全部显示在用户气泡内，会把“这个如何理解”变成一长串技术性文本。

- 新增 `quoted-prompt.ts`，集中生成现有引用 prompt，并将其拆成展示用的 `question` 和 `quote`。该格式仍用于现有请求和历史存储，不更改 Backend / Agent API。
- 新增 `components/user-prompt.tsx`：气泡仅显示用户问题；引用以默认折叠的「1 个已选文本片段」呈现，原生 `details/summary` 支持鼠标及键盘展开，引用全文以纯文本显示，长片段限制高度并可滚动。
- 即时消息、历史恢复及插话共用该展示；“复制提问”仅复制原问题。提交未被接受时，输入框恢复问题和引用草稿，避免暴露内部 prompt。
- 保留原始 prompt 的完整存储与导出，模型仍收到引用上下文。历史兼容仅识别现有完整的固定引用格式，普通文本和不完整格式保持原样。
- 新增 `tests/agent/quoted-prompt.test.ts`：覆盖问题与引用拆分、多段文本、普通文本、不完整格式、引用包含旧分隔符、历史与导出上下文保留。
- 扩展真实 Edge 验收：气泡只显示原问题、默认折叠、展开原文、复制内容、刷新历史及完整请求体均通过；截图已检查 390px 展示。复制测试在页面内替换 Clipboard API 验证传入内容，不操作系统剪贴板。

调整后的检查结果：`pnpm typecheck` 通过；`pnpm test` **495/495 通过**；全量 Lint 仍只有原有的 `anchorRef` 警告；浏览器异常为零；`git diff --check` 通过。应用 React best-practices 检查，组件未引入新监听、请求、依赖或重复状态，引用使用原生可访问的折叠控件。

## 后续调整：悬停预览引用

按用户反馈，将已发送消息的引用条目改为悬停浮层，移开鼠标即隐藏，移入预览可继续阅读和滚动；去掉右侧展开图标，不再点击展开或占用消息布局。键盘聚焦时也可预览。发送与历史拆分逻辑保持原样。同步更新浏览器脚本预期，但按用户要求不运行完整测试，本次只执行修改组件的定向 ESLint、脚本语法及 Git Diff 检查。
