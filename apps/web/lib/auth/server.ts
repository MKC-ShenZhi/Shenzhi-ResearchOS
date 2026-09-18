import { betterAuth } from "better-auth";
import { createAuthMiddleware } from "better-auth/api";
import { emailOTP } from "better-auth/plugins";
import type { User } from "better-auth";

import {
  authConfig,
  getAuthEmailVerificationSettings,
} from "@/config/auth";
import { emailDeliveryConfigured } from "@/config/email";
import { configuredOAuthProviders } from "@/config/oauth";
import { turnstileConfig } from "@/config/turnstile";
import {
  createTurnstileClientId,
  getClientIP,
  isSecureCookieBaseURL,
  persistTurnstileClientCookie,
  shouldEnforceTurnstile,
  TURNSTILE_ANON_ID_COOKIE,
  TURNSTILE_CLIENT_ID_CONTEXT_KEY,
  verifyCloudflareTurnstileToken,
} from "@/lib/auth/captcha/turnstile";
import {
  isTurnstileVerified,
  markTurnstileVerified,
} from "@/lib/auth/captcha/verification-store";
import { createBetterAuthEmailCallbacks } from "@/lib/auth/email/callbacks";
import { EMAIL_OTP_OPTIONS } from "@/lib/auth/email/options";
import { requiresEmailDelivery } from "@/lib/auth/email/requirements";
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  validatePasswordComposition,
} from "@/lib/auth/policies/password";
import { postgresPool } from "@/lib/infrastructure/postgres";
import {
  createAuthEmailProvider,
  EMAIL_PROVIDER_NOT_CONFIGURED_CODE,
} from "@/lib/auth/providers/email";
import {
  generateRandomOAuthPassword,
  OAUTH_CREDENTIAL_PROVIDER_ID,
  OAUTH_PLACEHOLDER_SCOPE,
} from "@/lib/auth/providers/oauth/credential";
import { passwordStatus } from "@/lib/auth/plugins/password-status";
import { registrationEmailVerification } from "@/lib/auth/plugins/registration-email-verification";

const betterAuthConfig = authConfig;

const socialProviders = configuredOAuthProviders.length
  ? Object.fromEntries(
      configuredOAuthProviders.map(({ id, clientId, clientSecret }) => [
        id,
        { clientId, clientSecret },
      ]),
    )
  : undefined;
const emailVerificationSettings = getAuthEmailVerificationSettings();
const { requireEmailVerification } = emailVerificationSettings;
const emailCallbacks = createBetterAuthEmailCallbacks(
  createAuthEmailProvider(),
);
const sendChangeEmailConfirmation = async (
  data: {
    user: User;
    newEmail: string;
    url: string;
    token: string;
  },
  request?: Request,
) => {
  await emailCallbacks.sendVerificationEmail(
    {
      user: data.user,
      newEmail: data.newEmail,
      url: data.url,
      token: data.token,
    },
    request,
  );
};

export const auth = betterAuth({
  ...betterAuthConfig,
  database: postgresPool,
  ...(socialProviders ? { socialProviders } : {}),
  emailVerification: {
    sendVerificationEmail: emailCallbacks.sendVerificationEmail,
    sendOnSignUp: emailVerificationSettings.sendOnSignUp,
    autoSignInAfterVerification:
      emailVerificationSettings.autoSignInAfterVerification,
  },
  hooks: {
    before: createAuthMiddleware(async (ctx) => {
      let turnstileClientId: string | null = null;

      // 人机验证:发送验证码前需先通过 Turnstile。
      // 已验证状态保存在后端数据库,15 分钟内邮箱验证码与 GitHub OAuth 共享。
      if (shouldEnforceTurnstile(ctx.path, turnstileConfig.enabled)) {
        const turnstileSecretKey = turnstileConfig.secretKey;
        if (turnstileSecretKey) {
          const existingClientId = ctx.getCookie(TURNSTILE_ANON_ID_COOKIE);
          const clientId = existingClientId || createTurnstileClientId();
          const verified = await isTurnstileVerified(clientId);

          if (!verified) {
            const token = ctx.getHeader("x-captcha-response");
            if (!token) {
              return ctx.error("BAD_REQUEST", {
                code: "MISSING_RESPONSE",
                message: "Missing CAPTCHA response",
              });
            }

            const valid = await verifyCloudflareTurnstileToken({
              token,
              secretKey: turnstileSecretKey,
              remoteIP: getClientIP(ctx.request),
              expectedAction: turnstileConfig.expectedAction,
              allowedHostnames: turnstileConfig.allowedHostnames,
            });

            if (!valid) {
              return ctx.error("FORBIDDEN", {
                code: "VERIFICATION_FAILED",
                message: "Captcha verification failed",
              });
            }

            await markTurnstileVerified(clientId);

            // 立即写回匿名 id Cookie:若后续 before 钩子返回错误(如邮件未配置),
            // 该 Cookie 会随错误响应下发;成功路径的响应头会被端点替换,由 after 钩子补写。
            ctx.setCookie(TURNSTILE_ANON_ID_COOKIE, clientId, {
              httpOnly: true,
              sameSite: "Lax",
              secure: isSecureCookieBaseURL(ctx.context.baseURL),
              maxAge: 60 * 60 * 24 * 365,
              path: "/",
            });
          }

          // 验证通过后把匿名客户端 id 写回 Cookie(成功路径由 after hook 执行)。
          turnstileClientId = clientId;
        }
      }

      if (
        !emailDeliveryConfigured &&
        requiresEmailDelivery(ctx.path)
      ) {
        return ctx.error("BAD_REQUEST", {
          code: EMAIL_PROVIDER_NOT_CONFIGURED_CODE,
          message: "Email delivery is not configured.",
        });
      }

      const isSignUp = ctx.path === "/sign-up/email";
      const isNewPasswordOperation =
        ctx.path === "/reset-password" || ctx.path === "/change-password";

      if (!isSignUp && !isNewPasswordOperation) {
        return turnstileClientId
          ? {
              context: {
                [TURNSTILE_CLIENT_ID_CONTEXT_KEY]: turnstileClientId,
              },
            }
          : undefined;
      }

      const password = isSignUp
        ? ctx.body?.password
        : ctx.body?.newPassword;
      if (typeof password !== "string") return;

      if (!validatePasswordComposition(password).valid) {
        return ctx.error("BAD_REQUEST", {
          code: "PASSWORD_POLICY_VIOLATION",
          message: "Password must include uppercase, lowercase, and a number.",
        });
      }
    }),
    after: persistTurnstileClientCookie,
  },
  emailAndPassword: {
    enabled: true,
    minPasswordLength: PASSWORD_MIN_LENGTH,
    maxPasswordLength: PASSWORD_MAX_LENGTH,
    requireEmailVerification,
    sendResetPassword: emailCallbacks.sendResetPassword,
    revokeSessionsOnPasswordReset: true,
  },
  user: {
    changeEmail: {
      enabled: true,
      // Verified accounts must approve the request from their current mailbox
      // before Better Auth sends the verification link to the replacement one.
      sendChangeEmailConfirmation,
    },
    deleteUser: {
      enabled: true,
    },
  },
  databaseHooks: {
    user: {
      create: {
        after: async (user, context) => {
          // 仅在 OAuth 回调首次创建用户时补齐 credential 凭证。
          // 邮箱/密码注册路径由 sign-up/email 自行写入 credential,
          // 这里避免重复创建。
          if (!context?.path.startsWith("/callback/")) return;

          const password = generateRandomOAuthPassword();
          const hash = await context.context.password.hash(password);

          await context.context.internalAdapter.linkAccount({
            userId: user.id,
            providerId: OAUTH_CREDENTIAL_PROVIDER_ID,
            accountId: user.id,
            password: hash,
            scope: OAUTH_PLACEHOLDER_SCOPE,
          });
        },
      },
    },
  },
  plugins: [
    emailOTP({
      ...EMAIL_OTP_OPTIONS,
      sendVerificationOnSignUp:
        emailVerificationSettings.sendVerificationOnSignUp,
      overrideDefaultEmailVerification:
        emailVerificationSettings.overrideDefaultEmailVerification,
      sendVerificationOTP: emailCallbacks.sendVerificationOTP,
    }),
    registrationEmailVerification({
      sendVerificationOTP: emailCallbacks.sendVerificationOTP,
    }),
    passwordStatus(),
  ],
});
