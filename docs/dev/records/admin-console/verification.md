# Admin Console V1 验收记录

- 初始工作区干净，分支 feat/agent-m0-integration；未提交、推送或修改 remote。
- pnpm typecheck：通过。
- pnpm build：通过；Vite 生产产物成功生成。
- Backend uv run unittest：8 项通过，包含认证、Cookie 属性/篡改/过期/轮换、非 loopback、凭据缺失、Agent 故障、用户 Service 参数复用及旧 API 认证边界。
- Edge 实际浏览器：账号密码登录、刷新后恢复会话、用户/能力路由、退出通过；登录截图 login.png 已检查。
- 隔离验收 Backend 使用临时 8137（8000 已有服务，未打断），Admin 固定 3101；临时环境变量注入测试凭据，未覆盖用户 .env。测试进程已停止。
- 隔离环境未加载 CHAT_DATABASE_URL / Agent 地址凭据，因此用户页面实际验证了后端失败提示，能力页验证了配置缺失提示。真实数据库搜索/筛选/分页、多规则数据渲染、真实 Agent 返回仍需在配置完整环境验收；自动化接口测试使用明确标识的测试响应，不属于产品 Mock 数据。
- pnpm install 已生成锁文件；安装器报告 esbuild build script 未批准，但 typecheck/build 实际均通过。
- Windows 沙箱禁止 asyncio socketpair；Backend 测试经授权沙箱外运行通过。

新增文件：apps/admin 下 package.json、pnpm-lock.yaml、tsconfig.json、vite.config.ts、index.html、.gitignore、.env.example、README.md；src/main.tsx、api.ts、types.ts、useResource.ts、style.css、features/UsersPage.tsx、features/CapabilitiesPage.tsx。
Backend 新增 app/api/admin_console.py、app/core/admin_auth.py、app/schemas/admin_console.py、app/integrations/admin_console/capabilities.py、tests/test_admin_console.py。
修改 apps/backend/app/main.py、apps/backend/.env.example、docs/engineering/architecture-confirmation.md、docs/engineering/deployment.md。
本目录保存 browser-smoke.mjs、login.png 与本记录。

接口、最终结构、认证说明、启动步骤及未来能力授权边界参见 apps/admin/README.md。

## 后续清理旧管理入口与 API

按用户后续指令移除 Web 管理页面、Feature、专用 Client、菜单入口与权限探测，并删除 Backend app/api/admin.py 及其路由注册。清理本地 .env 和 .env.example 中 SHENZHI_ADMIN_USER_IDS；独立 Admin 认证配置、用户 Service 与响应 Schema 保留。同步当前架构与权益文档，旧验收段落为清理前历史记录。

Backend 管理回归 8 项通过，旧 access/users 路由确认 404。PostgreSQL 集成测试已迁移为独立管理会话，保留搜索、分页、筛选、统计及结算数据断言，语法检查通过；未配置隔离测试数据库，本轮未执行该数据库测试。Web 清理后的类型检查、定向 ESLint 和 9 项设置测试此前均通过。
