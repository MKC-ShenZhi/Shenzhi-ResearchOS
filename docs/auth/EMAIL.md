# Better Auth 1.6.28 Email Capabilities

本文件只记录当前项目实际安装的 Better Auth `1.6.28` API 和 ShenZhi 的责任边界，
不复制上游完整文档。

## Email Verification

Better Auth core option：

```ts
emailVerification: {
  sendVerificationEmail: async ({ user, url, token }, request?) => {},
  sendOnSignUp?: boolean,
  sendOnSignIn?: boolean,
  autoSignInAfterVerification?: boolean,
  expiresIn?: number,
}
```

当前 1.6.28 的实际责任划分：

- callback data 是 `{ user, url, token }`，第二个参数是可选 `Request`。
- Better Auth 创建 verification token 和 URL，并负责点击后的验证。
- `AUTH_REQUIRE_EMAIL_VERIFICATION=false` 时，项目显式设置
  `sendOnSignUp: false` 和 `emailAndPassword.requireEmailVerification: false`。
- `AUTH_REQUIRE_EMAIL_VERIFICATION=true` 时，两个 Better Auth 选项同步为 `true`：注册
  会发送验证邮件，注册响应返回 `token: null`，未验证用户不能通过 Email/Password
  登录。
- `autoSignInAfterVerification` 没有显式启用；验证后的 Session 行为继续遵循
  Better Auth 默认行为。
- 强制验证开启但 AuthEmailProvider 未配置时，项目在 `/sign-up/email` 的 Better Auth
  `before` hook 中先返回 `EMAIL_PROVIDER_NOT_CONFIGURED`，不会先写入用户。
- Provider 配置完成并通过真实投递验收后，负责人只需设置环境变量，不需要修改
  `server.ts`。

ShenZhi 只将 callback 提供的 URL 转换为邮件消息并交给 `AuthEmailProvider`，不生成、
存储或校验 token。

## Password Reset

Better Auth core option：

```ts
emailAndPassword: {
  sendResetPassword: async ({ user, url, token }, request?) => {},
  resetPasswordTokenExpiresIn?: number,
  onPasswordReset?: async ({ user }, request?) => {},
  revokeSessionsOnPasswordReset?: boolean,
}
```

当前 1.6.28 的责任划分：

- `POST /request-password-reset` 接收 email 和可选 `redirectTo`。
- Better Auth 生成 reset token，并使用 core `verification` 存储。
- `sendResetPassword` 收到 `{ user, url, token }`，只负责把已准备的内容交给邮件
  Provider。
- 默认 reset token 有效期为 3600 秒。
- 当前项目配置 `revokeSessionsOnPasswordReset: true`，成功重置后由 Better Auth 撤销
  该用户的现有 Session。
- `GET /reset-password/:token` 处理邮件链接并重定向到 callback URL；随后
  `POST /reset-password` 完成密码更新。
- `app/reset-password/page.tsx` 只收集 email 或新密码，并调用 Better Auth 官方
  request/reset API；不读取 verification 表、不校验 token、不更新 account 表。
- 请求页面使用不暴露账户存在性的成功提示；Provider 未配置时显示明确配置错误。

Reset Password 的新密码在 Better Auth 官方 `hooks.before` 中复用
`apps/web/lib/auth/policies/password.ts`。Better Auth 仍负责长度、hash、verify 和存储。

## Email OTP

### Import paths

当前版本公开导出：

```ts
import { emailOTP } from "better-auth/plugins";
import { emailOTPClient } from "better-auth/client/plugins";
```

Server plugin 的核心 callback：

```ts
sendVerificationOTP: async ({ email, otp, type }, context?) => {}
```

其中 `type` 当前为：

```text
sign-in | email-verification | forget-password | change-email
```

### 当前配置

- `otpLength`: 6。
- `expiresIn`: 300 秒，即 5 分钟。
- `allowedAttempts`: 3。
- Email OTP endpoint rate limit：60 秒窗口、最多 3 次。
- `storeOTP`: `hashed`；Better Auth 的核心 `verification` 表只保存 OTP hash 和尝试次数，
  不保存活动 OTP 明文。
- Better Auth 生成、存储、过期、限制尝试次数并验证 OTP；LoginModal 的 60 秒倒计时
  只是 UX。
- LoginModal 调用 `emailOtp.sendVerificationOtp({ email, type: "sign-in" })`，登录
  调用 `signIn.emailOtp({ email, otp })`。
- Browser client 通过 `emailOTPClient()` 暴露这些官方 API。

Provider 未配置时，应用仍可启动，实际邮件发送请求会进入 `AuthEmailProvider` 的配置
错误；强制 Email/Password 注册会在用户写入前返回
`EMAIL_PROVIDER_NOT_CONFIGURED`。不会假装发送成功，也不会在日志输出 OTP。

Email OTP 是独立的 Better Auth plugin 路径，不由
`emailAndPassword.requireEmailVerification` 控制。Password Reset 也继续使用独立的
`sendResetPassword` callback；两者仍与 Verification 共用同一个 `AuthEmailProvider`。

### Schema 结论

当前 `emailOTP()` plugin 没有额外 `schema`；OTP 记录通过 Better Auth core
`verification` adapter 保存。因此当前 1.6.28 配置不需要第二张 OTP 表或额外字段。
启用新的 Better Auth plugin 或升级版本时，仍必须重新做官方 CLI migration review；若
官方明确产生 Schema diff，才生成官方 migration，不能手写平行认证 Schema。

## ShenZhi Email Provider boundary

```text
Better Auth callback
  ↓
apps/web/lib/auth/email/callbacks.ts
  ↓
apps/web/lib/auth/email/messages.ts
  ↓
AuthEmailProvider.send(message)
  ↓
apps/web/lib/auth/providers/email/factory.ts
  ↓
AlibabaDirectMailProvider
  ↓
Alibaba Cloud DirectMail `SingleSendMail`
```

Verification、OTP、Password Reset 共用一个 `AuthEmailProvider`；Change Email 的当前邮箱
确认（`sendChangeEmailConfirmation` 复用 verification callback）和 Set Password 验证码
（`/api/auth/password/send-otp`，ShenZhi 自有 `type: "set-password"`）也走同一条链路。Provider adapter 将
统一消息映射为 DirectMail `SingleSendMailRequest`：`AddressType=1`、
`ReplyToAddress=false`、`ClickTrace="0"`，并使用已验证的 `AccountName`。

Better Auth 仍生成、存储和验证 OTP、verification token/URL 以及 reset token/URL。
AlibabaDirectMailProvider 只负责发送，不重新实现任何 Better Auth 认证机制。阿里云
调用失败时只保留安全的 error code/RequestId，不保留邮件正文或敏感认证值。

真实 Provider 已有代码条件，但实际投递仍依赖负责人完成 DirectMail 控制台配置和
真实邮箱 smoke test。当前不会输出 OTP、token、reset URL 或 verification URL 日志。
