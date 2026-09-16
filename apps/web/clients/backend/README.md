# Backend Client boundary

- `http.ts`：同源 `/api/v1`、请求头、匿名身份首次握手、统一错误。
- `chat.ts`：会话 CRUD、发送、停止、续写和产品 SSE 事件分发。
- `sse.ts`：UTF-8、CRLF、多行数据与游标通信。
- `search.ts`：论文搜索。Chat 模型/模式/附件配置由 `chat.ts` 读取。
- `uploads.ts`：上传及状态，正文不返回浏览器。
- `forward.ts` / `identity.ts`：仅 Next.js BFF 导入；Better Auth 身份注入、匿名/鉴权异常分界、去除 Cookie / 伪造身份头、取消上游连接。

业务编排在 `features/chat/services`，UI 状态在 `features/chat/hooks`。
浏览器不得直连模型/搜索供应商。FastAPI 不读取 Better Auth 表，不创建第二套账号系统。
详见 [docs/chat](../../../../docs/chat/README.md)。
