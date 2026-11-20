# ShenZhi Admin Console V1

独立 Vite / React 19 / TypeScript / Tailwind CSS 4 / lucide-react 前端，固定开发端口 3101。无 Web 内部依赖，无独立业务后端。

## 结构与 API

- `src/main.tsx`：登录、会话检查、管理布局与 hash 路由（总览、用户、能力）。
- `src/features/`：只读用户与能力页面。
- `src/api.ts`、`useResource.ts`：同源 Cookie 请求、错误与可取消加载。
- `src/types.ts`：管理用户 API 类型；统计口径由 Backend Service 维护。
- `vite.config.ts`：开发反向代理；`pnpm-lock.yaml` 独立锁定依赖。

浏览器 → `/api/v1/admin-console/*` → Backend → 用户 Service / Agent 内部配置。
不经过 Web BFF、Better Auth，也不允许浏览器携带 Agent 密钥。

| 方法 | 相对 API 路径 | 认证 |
|---|---|---|
| POST | /auth/login | 本地账号密码 |
| POST | /auth/logout | 管理会话 |
| GET | /auth/me | 管理会话 |
| GET | /users | 管理会话；page/page_size/search/plan_id |
| GET | /capabilities | 管理会话 |

统一 code/data 或 code/message 响应；成功、认证失败、校验失败响应均 no-store。

## 本地配置与启动

Backend `.env` 添加（不要提交真实凭据）：

```env
ADMIN_AUTH_MODE=local_password
ADMIN_LOCAL_USERNAME=admin
ADMIN_LOCAL_PASSWORD=CHANGE_ME
ADMIN_SESSION_SECRET=
ADMIN_SESSION_TTL_SECONDS=28800
ADMIN_AUTH_LOCAL_ONLY=true
AGENT_INTERNAL_URL=<AGENT_INTERNAL_URL>
AGENT_SERVICE_TOKEN=<AGENT_SERVICE_TOKEN>
```

本地测试将密码改为任务指定的 `123456`；使用 `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成 Session Secret，至少 32 字符。TTL 默认 8 小时，允许范围 1–86400 秒。缺失配置、CHANGE_ME、非 loopback 均拒绝访问。

终端一：

```powershell
cd apps/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env --no-proxy-headers
```

终端二：

```powershell
cd apps/admin
pnpm install
pnpm dev --host 127.0.0.1 --port 3101
```

访问 http://127.0.0.1:3101 。Admin `.env.local` 可配置服务端 `ADMIN_BACKEND_ORIGIN`（默认 http://127.0.0.1:8000），没有 VITE_ 前缀，不暴露到浏览器。检查：`pnpm typecheck`、`pnpm build`。Backend：`uv run python -m unittest discover -s tests -p test_admin_console.py`。

## 认证与部署边界

认证独立封装于 Backend `core/admin_auth.py`。常量时间比较账号密码；会话包含签发时间、随机 nonce 与 HMAC-SHA256 签名；校验签名、时间及配置。轮换密码或密钥使已有会话失效。退出清除浏览器 Cookie；V1 无服务端撤销列表，被复制的已签发 Cookie 在过期或密钥轮换前仍有效。

Cookie 为 HttpOnly、SameSite=Strict，Path 限制 `/api/v1/admin-console`，HTTPS 请求设置 Secure，不写入 localStorage。不信任管理员身份 Header。登录通过凭据校验，其余路由通过管理会话校验。

生产构建 `dist/` 由 Nginx 提供，`/api/v1/admin-console/` 同源代理至 Backend，SPA 回退到 index.html。必须使用 HTTPS，正确传递受信任的 scheme，禁止将任意客户端转发头作为身份来源；Backend 不得公网暴露。当前 local_password 仅供本机，代理也必须限制为本机访问，不能用 loopback 代理把远程访问转换成本地身份。上线远程管理需先替换独立认证适配层（未来 mTLS / 客户端证书），本次未实现；不能关闭 local-only 绕过限制。无需开放 CORS。

## 数据与后续边界

用户查询复用 `admin_users.list_users` 与 `AdminUsersResponse`，多规则 Token 单列显示，不相加；缺失权益为未知，Partial 为已知下界，预留不等同于实际消耗。

Model/Skill 来自 Agent `/internal/v1/config`（10 秒超时，不继承环境 HTTP 代理），字段仅使用实际响应；Agent demo 配置会如实展示其 Mock 标签。Tool 目录尚未接入；配置不可用返回 503，不伪装为空。运行配置视图不是授权视图。

未来开关需要可信的版本化能力目录（identity/digest）、PermissionSnapshot 版本与发布接口、权益 Policy 分配与批准边界、Agent Runtime 执行校验、变更审计及回滚契约。未建立这些边界前不提供启停或权限编辑；请求期间不执行离线 export_capabilities 脚本。原 Web 用户管理页面及菜单入口已移除，管理界面统一使用本工程；旧 Backend `/api/v1/admin/*` API 与 `SHENZHI_ADMIN_USER_IDS` 配置已移除。
