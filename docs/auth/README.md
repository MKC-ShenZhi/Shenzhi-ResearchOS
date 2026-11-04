# ShenZhi 认证

`docs/auth/` 是 ShenZhi 认证实现的正式文档目录。

## 当前决策

- Better Auth `1.6.28` 是唯一认证内核。
- 数据库使用 PostgreSQL，通过 `pg.Pool` 和 Better Auth 接入。
- 当前登录标识只有 email。
- `user.name` 只表示昵称/展示名称，不是 username credential。
- 不支持 username login、phone 或 SMS。
- 不自建 User、Credential、Session、Cookie、password hash、verification 或 OTP
  认证实现。

## 当前已完成

### Better Auth 基础设施

- Better Auth server instance、Next.js HTTP Handler 和唯一浏览器 Client。
- Email/Password，密码长度 12–64。
- Better Auth 默认 password hash/verify、Session 和 Cookie。
- PostgreSQL 与 Better Auth 官方 CLI Migration。
- sign-up、sign-in、get-session、sign-out、wrong-password 的 Runtime Acceptance。

### Frontend Auth v1

- LoginModal 的 Email/Password 登录调用 Better Auth `signIn.email`。
- 注册调用 Better Auth `signUp.email`，只提交 `name`、`email` 和 `password`。
- `apps/web/lib/auth/policies/password.ts` 提供前后端共用的密码组合规则；服务端通过 Better
  Auth 官方 `hooks.before` 校验注册、Reset Password 和 Change Password 的新密码。
- Sidebar 使用真实 Better Auth Session 显示 `user.name` 或 email，并使用 `signOut`。
- 已移除没有有效引用的 Mock `apps/web/stores/auth.ts`。

### Architecture Finalization

- `apps/web/components/` 表示前端 UI 与浏览器认证适配器。
- `apps/web/app/api/auth/[...all]/route.ts` 只表示 Next.js HTTP boundary。
- `apps/web/lib/` 表示 Better Auth/server 侧集成、策略、Provider boundary 和基础设施。
- `apps/web/config/` 统一读取和规范化外部部署配置。
- `apps/web/clients/backend/` 是调用 FastAPI 业务后端的 BFF/Client 边界（`forward.ts` 转发，`identity.ts` 注入可信身份头）。

### Core User Authentication Flows

- 已启用 Better Auth `emailOTP()` server plugin 和 `emailOTPClient()` browser plugin。
- LoginModal 的验证码发送和登录调用官方 Email OTP API；Better Auth 负责 OTP 生成、
  存储、过期、尝试次数和服务端 rate limit，前端 60 秒倒计时仅是 UX。
- 已配置 Email Verification callback 和 Password Reset callback；真实邮件发送仍统一
  经过 provider-neutral `AuthEmailProvider`。
- `AUTH_REQUIRE_EMAIL_VERIFICATION` 已接入配置体系；默认 `false` 保持开发环境注册行为，
  设置为 `true` 时由 Better Auth 强制 Email/Password 注册邮箱验证。
- 已接入真实 `/reset-password` 请求/重置流程，以及 Settings 的真实昵称、email/验证
  状态、Change Password、Change Email、OAuth 用户的 Set Password、基础会话管理和
  账号注销。
- Reset Password 和 Change Password 复用同一纯 password policy；Better Auth 继续负责
  hash、verify 和 credential storage。

### Alibaba Cloud DirectMail

- 已接入官方 `@alicloud/dm20151123@1.10.2` SDK 的 DirectMail
  `SingleSendMail` adapter。
- Email OTP、Email Verification 和 Password Reset 三条邮件路径共用同一个
  `AuthEmailProvider`，由 Better Auth callback 准备内容，DirectMail 只负责发送。
- 未配置阿里云环境变量时，应用和 build 仍可启动；实际邮件路径或强制验证注册触发时
  返回配置错误。
- `AUTH_REQUIRE_EMAIL_VERIFICATION=false` 时保持 `sendOnSignUp: false` 和
  `requireEmailVerification: false`；设置为 `true` 时两个 Better Auth 开关同步启用。
- 强制验证开启但 Provider 缺失时，`/sign-up/email` 在用户写入数据库前返回稳定的
  `EMAIL_PROVIDER_NOT_CONFIGURED` 错误，不创建无法完成验证的用户。

### GitHub OAuth 与 Turnstile

- GitHub OAuth 通过 Better Auth `socialProviders.github` 接入；凭据不完整时应用仍可启动。
- GitHub 登录采用跳转式人机验证：点击 GitHub 图标先跳转到 `/login/github`
  （`app/login/[provider]`）独立验证页，完成 Turnstile 后由
  `POST /api/auth/oauth/verify?provider=github` 校验 token 并生成授权 URL，再跳转
  GitHub 授权页。
- Email OTP 登录、注册验证码发送和找回密码（`/request-password-reset`）可启用
  Cloudflare Turnstile；浏览器只接收公开 site key，secret 仅在服务端校验。
- Turnstile token 由服务端向 Cloudflare 验证，并可约束 action/hostname；验证状态保存在
  后端 `turnstile_verification` 表(15 分钟有效)，邮箱验证码、找回密码与 GitHub OAuth
  共享，任一入口通过后 15 分钟内不再重复挑战。

### Set Password 与账号注销

- OAuth 首次登录会写入带 `scope=oauth-placeholder` 标记的随机占位 credential；
  `apps/web/db/migrations/003_oauth_placeholder_scope.sql` 为既有 GitHub 用户补写该标记，
  使其被识别为“尚未设置真实密码”。
- Set Password 由 `apps/web/app/api/auth/password/send-otp` 与 `.../password/set` 承接：
  要求已登录，以发往本人邮箱的验证码证明邮箱所有权，新密码复用同一 password policy。
- 账号注销由 `apps/web/app/api/auth/account-deletion/route.ts` 编排：先由 FastAPI
  清理该用户全部业务数据，成功后再调用 Better Auth `deleteUser` 删除认证数据，详见
  [ARCHITECTURE.md](./ARCHITECTURE.md#account-deletion)。

## 尚未完成

- 生产环境的 DirectMail sender/domain、AK/SK、endpoint/region 配置和真实邮件投递验收。
- 生产环境真实邮件投递验收后，将 `AUTH_REQUIRE_EMAIL_VERIFICATION` 设置为 `true`。
  代码侧的强制验证配置和 Provider 缺失保护已经完成。
- OTP、Verification、Reset 邮件的真实投递验收。
- trusted origins、GitHub OAuth、Turnstile 的正式部署值与端到端验收，以及多实例
  shared rate-limit storage。
- 未来业务后端的稳定身份协议以及 Authorization/RBAC 产品决策。
- 生产 PostgreSQL、Web 域名和业务后端地址配置。

详细内容见：

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [CONFIGURATION.md](./CONFIGURATION.md)
- [EMAIL.md](./EMAIL.md)
- [WORKLOG.md](../dev/records/auth/WORKLOG.md)（历史工作日志）
