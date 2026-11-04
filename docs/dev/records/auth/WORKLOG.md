# Authentication Worklog

## Stage 1 — Better Auth Foundation

Stage 1 已完成并通过真实 Runtime Acceptance：

- Better Auth `1.6.28`。
- PostgreSQL 与 `pg.Pool`。
- Better Auth 官方 CLI Migration。
- Email/password，密码长度 12–64。
- sign-up、sign-in、get-session、sign-out、wrong-password。

认证行为由 Better Auth 提供。项目没有恢复 SQLite、custom credential、自定义
password hash、JWT、Session、username login 或 phone/SMS。

## Stage 2 — Architecture Boundary

本阶段完成：

- 将 Better Auth server instance 整理到 `apps/web/lib/auth/server.ts`。
- 将 PostgreSQL Pool 抽离到 `apps/web/lib/infrastructure/postgres.ts`。
- 保持 `/api/auth/[...all]` 路径和当前 GET/POST 导出不变。
- 建立 `apps/web/lib/auth/providers/` 外部 Provider adapter 边界。
- 建立 `apps/web/services/backend/` 未来业务后端责任边界。
- 将正式认证文档纳入 `docs/auth/`。
- 清理已经废弃的 custom auth / SQLite 认证文档。
- 将 Better Auth 依赖固定为 `1.6.28`，避免未经单独审计的版本漂移。

## Stage 3A — Email Provider Boundary

本阶段完成：

- 审计本机 Better Auth `1.6.28` 的 Email Verification、Password Reset 和 Email OTP
  实际 API。
- 建立 `AuthEmailMessage` 与 `AuthEmailProvider` 契约。
- 建立未配置 Provider 时的明确配置错误，不提供 console/mock/fallback provider。
- 建立 Verification、Password Reset、Email OTP 的最小消息 builder。
- 确认 Email OTP 使用 core `verification` 存储，当前版本没有额外 Schema。
- 没有绑定任何第三方邮件服务或新增供应商特定环境变量。

## Frontend Auth v1

本阶段完成：

- LoginModal 的 Email/Password 登录接入 Better Auth `signIn.email`。
- 注册接入 Better Auth `signUp.email`，使用 email 作为唯一登录标识，`name` 作为展示名称。
- 新增纯密码策略模块，覆盖 12–64 位以及大写、小写、数字组合规则。
- 使用 Better Auth `1.6.28` 官方 `hooks.before` 校验注册入口；Better Auth 继续负责
  password hash、verify、credential storage 和 Session。
- Sidebar 接入真实 `useSession`，显示 `user.name` 或 email，并使用 `signOut`。
- 移除无有效引用的 Mock `apps/web/stores/auth.ts`，不保留第二套登录状态。

## Architecture Finalization

本阶段完成：

- 将唯一浏览器 Better Auth Client 移到 `apps/web/components/auth/auth-client.ts`，删除旧的
  `apps/web/lib/auth/client.ts`。
- 新增 `apps/web/config/env.ts`、`apps/web/config/auth.ts`、`apps/web/config/database.ts`、`apps/web/config/email.ts`、
  `apps/web/config/backend.ts` 和交接说明；外部部署配置集中从 `apps/web/config/` 进入服务端模块。
- 改为由 `apps/web/config/database.ts` 向 PostgreSQL Pool 提供 `DATABASE_URL`，并由
  `apps/web/config/auth.ts` 条件化提供 Better Auth secret、base URL 和 trusted origins。
- 收敛 `BUSINESS_BACKEND_URL` 的服务端业务后端边界；未实现假业务 API 或身份协议。
- 保持 Schema、Migration、Better Auth 版本和认证基础行为不变。

## Core User Authentication Flows

本阶段完成：

- 启用 Better Auth `1.6.28` 的 `emailOTP()` server plugin 与 `emailOTPClient()` browser
  plugin；LoginModal 的验证码发送和登录调用官方 API。
- 继续复用 provider-neutral Email Provider callback；Provider 未配置时只返回明确配置
  错误，不输出 OTP、token、reset URL 或 verification URL。
- 配置 Email Verification callback；本地未配置邮件 Provider 时保持不强制注册邮箱验证，
  现在该行为由 `AUTH_REQUIRE_EMAIL_VERIFICATION=false` 显式控制，生产环境可通过配置开启。
- 配置 Password Reset callback、`revokeSessionsOnPasswordReset`，并将真实
  `/reset-password` 页面接入 Better Auth request/reset API。
- 将同一纯 password policy 复用到注册、Reset Password 和 Change Password 的新密码入口；
  Better Auth 继续负责 hash、verify、credential storage 和 Session。
- Settings 接入真实 Session 的 name/email/验证状态、昵称更新、Change Password、列出会话
  和退出其他会话。
- 同步 `docs/auth/README.md`、`ARCHITECTURE.md`、`CONFIGURATION.md`、`EMAIL.md` 和本
  工作日志，明确区分代码已完成与真实邮件 Provider 待配置。

本阶段仍未完成：

- DirectMail 控制台 sender/domain 验证、部署 AK/SK、区域/endpoint 填写和真实邮件投递
  smoke test。
- 生产环境真实邮件 readiness、`AUTH_REQUIRE_EMAIL_VERIFICATION=true` 的部署设置与验收。
- 2FA、Passkey、RBAC、业务身份协议和多实例 shared rate-limit storage；GitHub OAuth 与
  Turnstile 在后续阶段完成代码接入。
- 如果未来启用 Set Password，仍需把该入口接入同一个 password policy。

## Alibaba Cloud DirectMail Provider

本阶段完成：

- 安装并固定官方 `@alicloud/dm20151123@1.10.2` SDK。
- 在 `apps/web/lib/auth/providers/email/alibaba-directmail.ts` 建立 Alibaba DirectMail
  `SingleSendMail` adapter。
- 在 `apps/web/config/email.ts` 集中读取 Provider、AccessKey、Region、Endpoint 和发信地址。
- 让 Email OTP、Email Verification、Password Reset 三个 Better Auth callback 共用
  `AuthEmailProvider`，不创建 OTP、verification token 或 reset token。
- 缺少邮件配置时保持开发服务器和 build 可用，仅在真实发送路径返回配置错误。
- `AUTH_REQUIRE_EMAIL_VERIFICATION=false` 映射为 `sendOnSignUp: false` 与
  `requireEmailVerification: false`；设置为 `true` 时同步启用 Better Auth 注册邮箱验证。
- 强制验证开启而 Provider 缺失时，在 `/sign-up/email` 写入用户前返回稳定的
  `EMAIL_PROVIDER_NOT_CONFIGURED`，不创建无法完成验证的用户。
- 增加 fake client 单元测试，覆盖请求映射、缺失配置和安全错误传播。

尚未完成：

- DirectMail 控制台 sender/domain、AK/SK、Region/Endpoint 的实际部署配置。
- 使用真实邮箱完成 OTP、Email Verification、Password Reset 投递验收。
- 真实投递验收通过后，将 `AUTH_REQUIRE_EMAIL_VERIFICATION=true` 注入生产环境。

## Production Handoff — Email Verification Configuration

代码侧已完成：

- Better Auth Email/Password、Email OTP、Email Verification、Password Reset、Session
  集成。
- 统一 `AuthEmailProvider` 和 Alibaba DirectMail adapter。
- 严格解析 `AUTH_REQUIRE_EMAIL_VERIFICATION`，默认关闭，非法值明确失败。
- 强制验证开关与 Better Auth `sendOnSignUp`、`requireEmailVerification` 同步。
- 强制验证且 Provider 缺失时，在用户持久化前安全失败。
- 不生成或保存自定义 OTP、verification token 或 reset token，不输出敏感认证值。

负责人部署时负责填写和完成：

- `BETTER_AUTH_SECRET`、`BETTER_AUTH_URL`、`BETTER_AUTH_TRUSTED_ORIGINS`、`DATABASE_URL`。
- `EMAIL_PROVIDER=aliyun-directmail`、Alibaba AK/SK、DirectMail region/endpoint、
  `AUTH_EMAIL_FROM`、`AUTH_EMAIL_FROM_ALIAS`。
- `AUTH_REQUIRE_EMAIL_VERIFICATION=true`（仅在真实邮件 readiness 通过后）。
- `BUSINESS_BACKEND_URL`、正式 PostgreSQL、正式域名、Trusted Origins、DirectMail 开通、
  发信域名验证、DNS/SPF/DKIM、sender address、RAM 权限和 Deployment Secrets。
- OTP、Verification、Password Reset 的真实投递 smoke test。

真实 DirectMail、PostgreSQL、DNS 和生产联调不属于本次代码实现；集成不使用真实
阿里云凭据，也不包含部署或向 `dev` 推送。

## GitHub OAuth 与 Cloudflare Turnstile

本阶段完成：

- 通过 Better Auth GitHub social provider 接入 OAuth 登录/注册，配置不完整时保持应用
  可启动并返回明确错误。
- 对 Email OTP 登录与注册验证码发送增加可选 Cloudflare Turnstile 挑战。
- 服务端校验 Turnstile token，并支持 action 与 hostname 约束；secret 不暴露给浏览器。
- 验证通过后使用 Better Auth 签名 Cookie 记录，避免同一浏览器重复挑战。

仍需部署负责人完成 GitHub OAuth App、Turnstile site key/secret、正式 hostname/action
配置与端到端验收。
