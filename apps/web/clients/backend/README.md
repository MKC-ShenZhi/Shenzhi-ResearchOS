# Backend Client boundary

基础层（不依赖具体模块）：

- `http.ts`：同源 `/api/v1`、请求头、匿名身份首次握手、统一错误。
- `sse.ts`：UTF-8、CRLF、多行数据与游标通信。
- `types.ts`、`model-types.ts`：通用响应与模型类型。
- `forward.ts` / `identity.ts`：仅 Next.js BFF 导入；Better Auth 身份注入、匿名/鉴权异常分界、去除 Cookie / 伪造身份头、取消上游连接。

模块 Client：

- `agent.ts`：深知 AI（Agent）会话、运行、续流、停止与事件协议。
- `chat.ts`、`chat/`：Chat 配置（匿名身份初始化与模型目录）及旧 Chat 会话接口。
- `uploads.ts`：上传及状态（Agent 附件与旧 Chat 附件），正文不返回浏览器。
- `discovery.ts`、`recommendations.ts`、`behavior.ts`：首页论文 Feed、个人推荐与行为事件上报。
- `interactions.ts`、`read-status.ts`、`private-papers.ts`：收藏/点赞/关注、已读状态、私有论文。
- `conferences.ts`：会议截稿与分类。

业务编排在对应 `features/{module}/services` 或 Feature hook 中。
浏览器不得直连模型/搜索供应商。FastAPI 不读取 Better Auth 表，不创建第二套账号系统。
详见 [docs/agent](../../../../docs/agent/README.md) 与 [docs/chat](../../../../docs/chat/README.md)。
