# Backend Client boundary

## Base (`clients/backend/`)

- `http.ts`：同源 `/api/v1`、请求头、匿名身份首次握手、统一错误。
- `sse.ts`：UTF-8、CRLF、多行数据与游标通信。
- `forward.ts` / `identity.ts`：仅 Next.js BFF 导入；Better Auth 身份注入、匿名/鉴权异常分界、去除 Cookie / 伪造身份头、取消上游连接。
- `types.ts`：仅维护 Backend transport 的通用协议类型。
- `index.ts`：仅 re-export 基础能力，不反向导出具体模块。

## Modules (`clients/backend/{module}/`)

- `chat/`：会话 CRUD、发送、停止、续写、产品 SSE 事件分发、上传。
- `profile/`：用户资料 API Client 与领域类型。
- `settings/`：用户偏好 API Client 与领域类型。

业务编排在 `features/{module}/services`，UI 状态在 `features/{module}/hooks` / `components`。
模块 Client 可以依赖 Backend 基础层；基础层不得反向依赖模块 Client。
`clients` 仅可依赖 `lib` 中的框架或基础设施能力，不得依赖 Feature、组件或 Store。
浏览器不得直连模型/搜索供应商。FastAPI 不读取 Better Auth 表，不创建第二套账号系统。
详见 [docs/chat](../../../../docs/chat/README.md)。
