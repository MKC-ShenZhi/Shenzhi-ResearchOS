# Backend Client boundary

## Base (`clients/backend/`)

- `http.ts`：同源 `/api/v1`、请求头、匿名身份首次握手、统一错误。
- `sse.ts`：UTF-8、CRLF、多行数据与游标通信。
- `forward.ts` / `identity.ts`：仅 Next.js BFF 导入；Better Auth 身份注入、匿名/鉴权异常分界、去除 Cookie / 伪造身份头、取消上游连接。
- `index.ts`：仅 re-export 基类能力。

## Modules (`clients/backend/{module}/`)

- `chat/`：会话 CRUD、发送、停止、续写、产品 SSE 事件分发、上传。
- `profile/`：用户资料 API Client 与领域类型。

业务编排在 `features/{module}/services`，UI 状态在 `features/{module}/hooks` / `components`。
浏览器不得直连模型/搜索供应商。FastAPI 不读取 Better Auth 表，不创建第二套账号系统。
详见 [docs/chat](../../../../docs/chat/README.md)。
