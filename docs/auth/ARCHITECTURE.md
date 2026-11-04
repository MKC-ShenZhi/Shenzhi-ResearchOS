# Authentication Architecture

## Ownership boundary

ShenZhi keeps Better Auth `1.6.28` as its only authentication kernel. The
repository separates the browser UI, the Next.js/Better Auth server boundary,
the future business backend, and deployment configuration:

```text
User
 ↓
apps/web/components/
  Frontend UI
 ↓
apps/web/components/auth/auth-client.ts
  Browser Better Auth Client
 ↓
/api/auth/*
 ↓
apps/web/app/api/auth/[...all]/route.ts
  HTTP boundary only
 ↓
apps/web/lib/auth/server.ts
  Better Auth server instance
 ↓
Better Auth
 ├─ apps/web/lib/infrastructure/postgres.ts
 │    ↓
 │  PostgreSQL
 │
 └─ apps/web/lib/auth/email/callbacks.ts
      ↓
   AuthEmailProvider
      ↓
   apps/web/lib/auth/providers/email/factory.ts
       ↓
   AlibabaDirectMailProvider
       ↓
   Alibaba Cloud DirectMail SingleSendMail
```

External deployment values flow separately:

```text
.env / deployment secrets
        ↓
      apps/web/config/
       ├─ auth.ts
       ├─ database.ts
       ├─ email.ts
       ├─ oauth.ts
       ├─ turnstile.ts
       └─ backend.ts
        ↓
    apps/web/lib / apps/web/clients / apps/web/app/api
```

`apps/web/components/` never imports `apps/web/lib/auth/server.ts`, PostgreSQL infrastructure,
or server-side configuration. The only shared exception is the pure password
policy module, which has no secrets, database, Better Auth, or UI dependencies.
The server side does not import browser Client modules.

## Frontend boundary

- `apps/web/components/auth/login-modal.tsx` owns the current LoginModal UI.
- `apps/web/components/common/layout/app-sidebar.tsx` owns Session-driven identity display and
  logout UI.
- `apps/web/components/auth/auth-client.ts` is the single `createAuthClient()` export.
  It is a Client Component module and talks to the Better Auth HTTP API.
- Login and registration use Better Auth `signIn.email` and `signUp.email`.
- The OTP UI uses the official `emailOTPClient()` methods for sending and
  signing in. The client-side 60-second countdown is UX only; Better Auth
  remains responsible for OTP generation, expiry, attempts, and rate limits.
- The forgot-password control opens the real `/reset-password` flow, which
  calls Better Auth request/reset endpoints without reading the verification
  table in application code.
- Settings uses the Better Auth session for profile display, `updateUser`,
  `changePassword`, `changeEmail`, `listSessions`, and `revokeOtherSessions`.
  OAuth 用户的 Set Password 走 `/api/auth/password/*`，账号注销走
  `/api/auth/account-deletion`（见下文 [Account deletion](#account-deletion)）。
- GitHub 登录使用 Better Auth `signIn.social()`；浏览器不读取 OAuth secret。
- OAuth 登录默认走跳转式人机验证：点击 Provider 图标后先进入 `/login/[provider]`
  独立验证页，完成 Cloudflare Turnstile 后由 `POST /api/auth/oauth/verify` 校验 token
  并生成授权 URL，浏览器再跳转到对应 Provider 授权页。
- Email OTP 登录与注册发送验证码时，先不带 token 尝试发送；后端判定需要人机验证时
  再渲染 Cloudflare Turnstile 并把一次性 token 交给服务端验证。
- 找回密码发送重置邮件（`/request-password-reset`）同样在发送前校验人机验证，并与
  邮箱验证码、OAuth 登录一致：先不带 token 尝试，需要验证时再弹出 Turnstile。
- 邮箱验证码、发送重置邮件、OAuth 登录共享后端“已通过验证”状态：任一功能通过后
  15 分钟内，触发另一功能不再弹验证。

## Better Auth backend boundary

- `apps/web/app/api/auth/[...all]/route.ts` only mounts
  `toNextJsHandler(auth)` and keeps the current GET/POST exports.
- `apps/web/lib/auth/server.ts` is the only Better Auth server instance. It owns
  Email/Password, Email OTP, Email Verification and Password Reset callbacks,
  Session, Cookie, Better Auth lifecycle behavior, and the deployment-controlled
  email-verification requirement.
- `AUTH_REQUIRE_EMAIL_VERIFICATION` is parsed in `apps/web/config/auth.ts` and mapped to
  both Better Auth `emailVerification.sendOnSignUp` and
  `emailAndPassword.requireEmailVerification`. `server.ts` does not read
  `process.env` directly.
- `apps/web/lib/auth/policies/password.ts` is a pure product rule. The official
  `hooks.before` checks new passwords at `/sign-up/email`, `/reset-password`,
  and `/change-password`; Better Auth still owns password length enforcement,
  hash, verify, credential storage, and Session.
- `apps/web/lib/infrastructure/postgres.ts` only creates/exports the authentication
  `pg.Pool` using `apps/web/config/database.ts`.
- `apps/web/lib/auth/providers/` contains server-side external Provider contracts. It
  does not contain token, OTP, reset, verification, or Session logic.
- GitHub OAuth provider 仅在 client ID/secret 同时存在时启用；未配置不会阻止应用启动。
- `apps/web/lib/auth/captcha/turnstile.ts` 只在显式启用且存在 secret 时保护 Email OTP
  发送（`/email-otp/send-verification-otp`）、注册验证码发送
  （`/registration-email/send-otp`）和找回密码（`/request-password-reset`）端点，并在
  Cloudflare 校验失败时 fail closed；同时负责匿名客户端 id Cookie 的
  下发(只承载随机 id,不承载验证状态)。
- `apps/web/lib/auth/captcha/verification-store.ts` 把“已通过验证”状态写入 PostgreSQL
  `turnstile_verification` 表，15 分钟有效；数据库不可用时按未通过处理(fail closed)。
- OAuth 登录的跳转式验证入口是 `apps/web/app/api/auth/oauth/verify/route.ts`
  （`?provider=github`），它复用 `verifyCloudflareTurnstileToken` 并调用
  `auth.api.signInSocial()` 生成授权 URL。
- `user.changeEmail`（先由当前邮箱确认，再向新邮箱发验证链接）与 `user.deleteUser`
  在 `server.ts` 中启用；`databaseHooks.user.delete.before` 删除用户前清理
  `set-password-otp:<userId>` verification 记录。

Authentication model:

- `user.email` is the only login identifier.
- `user.name` is a display name.
- There is no username plugin, username credential, phone login, or SMS flow.
- Better Auth owns the `user`, `account`, `session`, and `verification` tables.
- No second auth API, repository, hash implementation, Session store, or
  migration exists. The narrow custom routes (`/api/auth/oauth/verify`,
  `/api/auth/password/*`, `/api/auth/account-deletion`) reuse `auth.api`, the
  Better Auth internal adapter, and its password hasher.

## Password policy boundary

The composition rule is shared by the registration, Reset Password, and Change
Password UI and the server hook, but remains independent of Better Auth and the
database. It checks for at least one uppercase letter, lowercase letter, and
digit. Better Auth continues to enforce the 12–64 length range and all password
cryptography/storage.

OAuth 用户的 Set Password（`apps/web/app/api/auth/password/set/route.ts`）在路由内直接
调用同一 `validatePasswordComposition` 与 12–64 长度约束，并通过 Better Auth 的
password hasher 写入 credential、清除 `oauth-placeholder` 标记。今后任何新的创建密码
入口也必须复用这一 policy。No database hook or custom password implementation is
used as a replacement for the official authentication entry-point hook.

## Email capability boundary

邮件调用链（callback → messages → `AuthEmailProvider` → DirectMail adapter）见
[EMAIL.md](./EMAIL.md#shenzhi-email-provider-boundary)。

Better Auth creates and validates verification/reset tokens and OTP values.
ShenZhi only maps callback data to a small email message and delegates sending
to a provider. The official Email OTP server/client plugins are enabled, and
the Alibaba DirectMail adapter is selected only when all required deployment
configuration is present. An unconfigured provider leaves application startup
and build available, then raises a clear configuration error when a delivery
path is invoked. When `AUTH_REQUIRE_EMAIL_VERIFICATION=true`, the additional
`/sign-up/email` guard runs before Better Auth persists a user. It never logs a
token, OTP, or complete authentication URL.

`apps/web/lib/auth/server.ts` depends only on `createAuthEmailProvider()` and the
provider-neutral callbacks. It does not import `SingleSendMailRequest`, access
keys, endpoint values, or any Alibaba SDK type. This keeps a future SES,
Resend, or other adapter replacement outside Better Auth configuration.

Email Verification remains an explicit Better Auth capability. The default
configuration is `AUTH_REQUIRE_EMAIL_VERIFICATION=false`, which keeps both
`sendOnSignUp` and `requireEmailVerification` false. Production can set the
flag to `true` after successful real-mail readiness and smoke testing. This
switch only changes Email/Password registration and sign-in enforcement;
Email OTP continues to use its official plugin path, and Password Reset keeps
its independent callback.

## Account deletion

```text
Browser (features/settings/services/account-deletion.ts)
  ↓
POST /api/auth/account-deletion   (apps/web/app/api/auth/account-deletion/route.ts)
  ↓ 1. auth.api.getSession() 取得 user id
  ↓ 2. 服务端直连 BUSINESS_BACKEND_URL，带 X-ShenZhi-User-Id、
  ↓    X-ShenZhi-Account-Deletion: 1 与 BFF secret
POST /api/v1/account-deletion/cleanup   (apps/backend/app/api/account_deletion.py)
  ↓    AccountDeletionService（services/user/account_deletion.py）单事务删除业务数据
  ↓ 3. 清理成功后 auth.api.deleteUser()
Better Auth 删除 user / account / session
```

- cleanup 端点不经通用 `/api/v1` BFF 暴露给浏览器：通用 BFF 只转发 allowlist 头，
  不会带上 `X-ShenZhi-Account-Deletion`，FastAPI 缺少该标记时返回 403。
- 业务清理幂等；若清理成功但 Better Auth 删除失败，路由返回 409，用户重新登录后可
  重试。被清理的业务数据范围见 [`docs/settings/README.md`](../settings/README.md)。
- Better Auth 仍执行自身的 fresh/sensitive session 策略；`verification` 表无用户外键，
  ShenZhi 的 `set-password-otp:<userId>` 记录由 `databaseHooks.user.delete.before` 清理。

## Future business backend boundary

```text
Authenticated identity
  ↓
Next.js /api/v1 BFF  (apps/web/clients/backend/forward.ts)
  ↓
X-ShenZhi-User-Id（已登录）/ X-ShenZhi-Anonymous-Id（匿名）
  ↓
BUSINESS_BACKEND_URL
  ↓
Python FastAPI  (apps/backend)
```

The browser must not call FastAPI directly. FastAPI must not read Better Auth `user`, `account`, `session`, or `verification` tables, and must not depend on `pg.Pool` or `apps/web/lib/auth/server.ts`. See `docs/dev/项目介绍.md`.

The BFF and FastAPI use the same `BACKEND_BFF_SECRET` and fail closed when it is
missing. Secretless development requires `BACKEND_ALLOW_INSECURE_LOCAL_BFF=true`
on both sides and is restricted to loopback. A normal empty Better Auth session
uses the anonymous identity (`X-ShenZhi-Anonymous-Id`); a Better Auth exception returns 503 and is not
silently downgraded to anonymous access.

Authentication and Authorization/RBAC remain separate concerns. RBAC is a
future product decision; this stage adds no role table, admin plugin, or
permission service.

## Schema and runtime boundary

The current core schema remains the official Better Auth migration at
`apps/web/db/migrations/001_better_auth.sql`. Email OTP reuses Better Auth's core
`verification` storage and does not add a second OTP table. The current stage
adds one small non-authentication table for the shared Turnstile verification
state: `apps/web/db/migrations/002_turnstile_verification.sql`(`turnstile_verification`,
keyed by anonymous client id, 15 minute expiry).
`apps/web/db/migrations/003_oauth_placeholder_scope.sql` 是数据迁移，不改 Schema：把
既有 GitHub 用户自动补写的随机占位 credential 的 `account.scope` 标记为
`oauth-placeholder`，使 `hasPassword` 判定其尚未设置真实密码。
