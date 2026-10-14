# Authentication Configuration

## Configuration flow

Deployment values are read and normalized in `apps/web/config/`; authentication and
infrastructure modules do not scatter direct `process.env` access:

```text
.env / deployment secrets
        ↓
      apps/web/config/
        ↓
    apps/web/lib / apps/web/services
```

`apps/web/config/` does not implement authentication, create database connections,
send email, or implement business services. Do not import server configuration
from Client Components. No provider-specific secret is stored in this
repository.

## Current environment variables

| 变量 | 配置模块 | 用途 | 当前要求 |
| --- | --- | --- | --- |
| `DATABASE_URL` | `apps/web/config/database.ts` | `pg.Pool` 与 Better Auth 的 PostgreSQL 连接地址 | 当前必须；服务端变量，不提交真实地址或密码 |
| `BETTER_AUTH_SECRET` | `apps/web/config/auth.ts` | Better Auth 服务端加密、签名与认证安全所需 secret | 当前必须；高熵值，正式环境单独配置 |
| `BETTER_AUTH_URL` | `apps/web/config/auth.ts` | Better Auth 应用基础地址 | 当前必须；生产使用实际 HTTPS 地址 |
| `BETTER_AUTH_TRUSTED_ORIGINS` | `apps/web/config/auth.ts` | 可选的逗号分隔 trusted origins | 正式跨域部署前配置；空值不产生 `['']` |
| `AUTH_REQUIRE_EMAIL_VERIFICATION` | `apps/web/config/auth.ts` | 是否强制 Email/Password 注册完成邮箱验证 | 默认 `false`；真实邮件 readiness 通过后生产设置为 `true` |
| `BUSINESS_BACKEND_URL` | `apps/web/config/backend.ts` | FastAPI 业务后端的服务端地址 | 使用 Chat / Search 时必须；不暴露给浏览器 |
| `BACKEND_BFF_SECRET` | `apps/web/config/backend.ts` | Next.js BFF 调用 FastAPI 的内部凭据 | 默认必须；两端配置相同高熵值 |
| `BACKEND_ALLOW_INSECURE_LOCAL_BFF` | `apps/web/config/backend.ts` / Backend | 无 Secret 的本地开发逃生开关 | 默认 `false`；仅两端显式为 `true` 且 loopback 时生效 |
| `EMAIL_PROVIDER` | `apps/web/config/email.ts` | 当前 Provider 选择；使用 `aliyun-directmail` | 配置 DirectMail 发送前填写 |
| `ALIBABA_CLOUD_ACCESS_KEY_ID` | `apps/web/config/email.ts` | DirectMail API AccessKey ID | 仅由 Deployment Secrets 注入 |
| `ALIBABA_CLOUD_ACCESS_KEY_SECRET` | `apps/web/config/email.ts` | DirectMail API AccessKey Secret | 仅由 Deployment Secrets 注入，不提交 Git |
| `ALIYUN_DIRECTMAIL_REGION_ID` | `apps/web/config/email.ts` | DirectMail 区域 | 必须与发信地址所在区域匹配 |
| `ALIYUN_DIRECTMAIL_ENDPOINT` | `apps/web/config/email.ts` | DirectMail OpenAPI endpoint | 显式配置，不依赖模糊默认值 |
| `AUTH_EMAIL_FROM` | `apps/web/config/email.ts` | DirectMail `AccountName` 发信地址 | 必须是阿里云控制台已验证地址 |
| `AUTH_EMAIL_FROM_ALIAS` | `apps/web/config/email.ts` | DirectMail `FromAlias` | 可选 |
| `GITHUB_CLIENT_ID` | `apps/web/config/oauth.ts` | GitHub OAuth App Client ID | 启用 GitHub 登录时填写 |
| `GITHUB_CLIENT_SECRET` | `apps/web/config/oauth.ts` | GitHub OAuth App Client Secret | 仅由 Deployment Secrets 注入，不提交 Git |
| `TURNSTILE_ENABLED` | `apps/web/config/turnstile.ts` | 是否在发送 Email OTP 前强制人机验证 | 默认 `false`；启用时必须同时配置 site key 与 secret |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | Client Component | 浏览器渲染 Turnstile 的公开 site key | 可公开，但必须与 secret 对应 |
| `TURNSTILE_SECRET_KEY` | `apps/web/config/turnstile.ts` | 服务端校验 Turnstile token | 仅由 Deployment Secrets 注入 |
| `TURNSTILE_EXPECTED_ACTION` | `apps/web/config/turnstile.ts` | 可选的 token action 约束 | 与 Cloudflare Widget 配置一致时填写；OAuth 验证页会自动使用该值 |
| `TURNSTILE_ALLOWED_HOSTNAMES` | `apps/web/config/turnstile.ts` | 可选的逗号分隔 hostname 白名单 | 生产建议配置正式域名 |

`BETTER_AUTH_TRUSTED_ORIGINS` 会被裁剪并过滤空项，例如：

```text
https://example.com, https://admin.example.com
```

会规范化为两个 origin。未配置时不显式传入 Better Auth，以保持当前默认
行为。`BUSINESS_BACKEND_URL`（兼容旧名 `API_URL`）由
`apps/web/app/api/v1/[...path]/route.ts` 作为 Chat / Search 的同源 BFF 使用，浏览器不会直接请求
`BUSINESS_BACKEND_URL`。未配置 `BACKEND_BFF_SECRET` 时默认拒绝转发；只有显式开启本地逃生开关且地址为
loopback 时才允许无 Secret 运行。

`AUTH_REQUIRE_EMAIL_VERIFICATION` 由通用 boolean parser 严格解析：未设置为 `false`，
首尾空格会被忽略，`true`/`false` 不区分大小写；空字符串及其他值会产生明确配置错误，
不会静默转换为 `true`。

## Email Provider configuration boundary

当前 Provider 已确定为 Alibaba Cloud DirectMail，代码使用官方
`@alicloud/dm20151123@1.10.2` SDK 的 `SingleSendMail` API（版本
`2015-11-23`）。

所有邮件发送配置从 `apps/web/config/email.ts` 进入运行时代码：

- `EMAIL_PROVIDER=aliyun-directmail`：选择 Provider。
- `ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET`：只从部署
  Secret 注入，不能进入源码、日志或 Git。
- `ALIYUN_DIRECTMAIL_REGION_ID` / `ALIYUN_DIRECTMAIL_ENDPOINT`：显式指定区域与
  endpoint，必须与发信地址所在区域一致。
- `AUTH_EMAIL_FROM`：映射到 `AccountName`，必须是 DirectMail 控制台已验证的发信地址。
- `AUTH_EMAIL_FROM_ALIAS`：可选，映射到 `FromAlias`。

配置不完整时 `createAuthEmailProvider()` 返回未配置状态，不会让开发服务器或 build
失败；只有触发 OTP、Verification 或 Reset 邮件发送时才返回配置错误。若
`AUTH_REQUIRE_EMAIL_VERIFICATION=true` 且 Provider 缺失，`/sign-up/email` 会在 Better
Auth 写入用户前返回 `EMAIL_PROVIDER_NOT_CONFIGURED`。Provider 不会输出 AccessKey、
邮件正文、OTP、token 或认证 URL。

`AUTH_REQUIRE_EMAIL_VERIFICATION=false` 映射为 `sendOnSignUp: false` 和
`requireEmailVerification: false`；设置为 `true` 时两个 Better Auth 选项同步为 `true`。
真实邮件联调和验收通过后，负责人只需修改 Deployment Secret，不需要修改认证源码。

## Current Better Auth configuration

`apps/web/lib/auth/server.ts` 当前配置：

- `database`：来自 `apps/web/lib/infrastructure/postgres.ts` 的 `pg.Pool`。
- 条件化的 `secret`、`baseURL` 和可选 `trustedOrigins`。
- `emailAndPassword.enabled`：`true`。
- `emailAndPassword.minPasswordLength`：`12`。
- `emailAndPassword.maxPasswordLength`：`64`。
- password hash/verify、Session、Cookie：Better Auth 默认实现。
- 注册、Reset Password、Change Password 的新密码组合规则：纯 policy 和 Better Auth
  官方 `hooks.before`。
- `emailVerification.sendVerificationEmail`、`emailVerification.sendOnSignUp`、
  `emailAndPassword.requireEmailVerification`、`emailAndPassword.sendResetPassword`、
  `emailOTP()` 以及浏览器 `emailOTPClient()`：均使用 Better Auth 官方 API；邮件发送
  由 Provider abstraction 承接。
- Email OTP：6 位、300 秒有效、3 次尝试，发送 rate limit 为 60 秒窗口最多 3 次；OTP
  在 Better Auth 的 `verification` 表中以 hash 保存。
- Reset Password：`revokeSessionsOnPasswordReset: true`。

Email Verification 强制注册默认关闭，由 `AUTH_REQUIRE_EMAIL_VERIFICATION` 控制。
OAuth 仅接入 GitHub，凭据从 `apps/web/config/oauth.ts` 读取，未配置时应用照常启动。
Email OTP 发送可通过 `TURNSTILE_ENABLED` 启用 Cloudflare Turnstile；2FA、Passkey、
RBAC、Redis 和业务身份协议仍未实现。

## 官方 Migration

- 文件：`apps/web/db/migrations/001_better_auth.sql`
- 数据库：PostgreSQL
- 来源：Better Auth `1.6.28` 官方 CLI Migration
- 核心表：`user`、`account`、`session`、`verification`
- Email OTP 复用 `verification`，本阶段没有修改 Schema，也没有手写新的 auth
  migration。

## 后续配置类别

下一阶段在启用对应能力前，需要负责人确定：

- 正式 Web URL/domain 与 `BETTER_AUTH_TRUSTED_ORIGINS`。
- DirectMail 控制台的 sender/domain 验证、AK/SK、sender/from、endpoint/region，并完成
  OTP/Verification/Reset 的真实邮件投递验收。
- 生产设置 `AUTH_REQUIRE_EMAIL_VERIFICATION=true`，并完成 OTP/Verification/Reset 邮件的
  真实投递验收；代码实现已完成，真实环境联调不属于本次代码实现。
- GitHub OAuth App 的 Client ID/Secret 与回调地址
  `<BETTER_AUTH_URL>/api/auth/callback/github`；OAuth 首次登录会自动为账号写入随机
  占位密码的 credential 凭证，无需用户设置密码。
- shared rate-limit storage（如果部署为多实例）。
- Turnstile 正式 site key/secret、action/hostname 约束与端到端验收。
- 未来业务后端服务地址 `BUSINESS_BACKEND_URL` 和语言无关的身份协议。

未来可选能力包括更多 OAuth Provider、2FA 和 Passkey。若未来启用 Set Password 或其他
创建新密码入口，必须继续复用同一个 password policy。
