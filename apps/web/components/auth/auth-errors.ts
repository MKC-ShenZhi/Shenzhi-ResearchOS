export const PASSWORD_POLICY_MESSAGE =
  "密码需为12–64位，且至少包含大写字母、小写字母和数字";

export const EMAIL_PROVIDER_MESSAGE = "邮件服务尚未配置，暂时无法发送邮件";

type AuthErrorKind =
  | "login"
  | "otp"
  | "register"
  | "reset"
  | "change-email"
  | "change-password"
  | "delete-user"
  | "profile"
  | "session";

function getAuthErrorDetails(error: unknown) {
  if (!error || typeof error !== "object") {
    return { code: undefined, message: undefined, status: undefined };
  }

  const details = error as Record<string, unknown>;
  return {
    code: typeof details.code === "string" ? details.code : undefined,
    message:
      typeof details.message === "string" ? details.message : undefined,
    status:
      typeof details.status === "number"
        ? details.status
        : typeof details.statusCode === "number"
          ? details.statusCode
          : undefined,
  };
}

export function isAuthErrorCode(error: unknown, expectedCode: string) {
  return getAuthErrorDetails(error).code === expectedCode;
}

export function getAuthErrorMessage(
  error: unknown,
  fallback: string,
  kind: AuthErrorKind,
) {
  const { code, message, status } = getAuthErrorDetails(error);

  if (
    code === "EMAIL_PROVIDER_NOT_CONFIGURED" ||
    code === "RESET_PASSWORD_DISABLED" ||
    code === "VERIFICATION_EMAIL_NOT_ENABLED" ||
    message === "Auth email provider is not configured." ||
    message === "Email delivery is not configured." ||
    message === "send email verification is not implemented" ||
    message === "Verification email isn't enabled"
  ) {
    return EMAIL_PROVIDER_MESSAGE;
  }

  if (
    code === "MISSING_RESPONSE" ||
    code === "VERIFICATION_FAILED" ||
    message === "Missing CAPTCHA response" ||
    message === "Captcha verification failed"
  ) {
    return "人机验证未通过，请重试";
  }

  if (code === "PROVIDER_NOT_FOUND") {
    return "该登录方式尚未配置";
  }

  if (code === "PASSWORD_POLICY_VIOLATION") return PASSWORD_POLICY_MESSAGE;
  if (code === "EMAIL_ALREADY_REGISTERED") {
    return "该邮箱已注册，请直接登录";
  }
  if (code === "REGISTRATION_EMAIL_NOT_VERIFIED") {
    return "邮箱验证已失效，请重新验证";
  }
  if (code === "INVALID_EMAIL") return "请输入有效邮箱";
  if (code === "PASSWORD_TOO_SHORT" || code === "PASSWORD_TOO_LONG") {
    return PASSWORD_POLICY_MESSAGE;
  }

  if (
    kind === "login" &&
    (status === 401 ||
      code === "INVALID_EMAIL_OR_PASSWORD" ||
      code === "INVALID_PASSWORD")
  ) {
    return "邮箱或密码错误";
  }

  if (kind === "otp" && code === "OTP_EXPIRED") {
    return "验证码已过期，请重新获取";
  }
  if (kind === "otp" && code === "TOO_MANY_ATTEMPTS") {
    return "验证码尝试次数过多，请重新获取";
  }
  if (kind === "otp" && code === "INVALID_OTP") {
    return "验证码错误，请检查后重试";
  }

  if (kind === "reset" && (code === "INVALID_TOKEN" || status === 401)) {
    return "重置链接已失效，请重新申请";
  }

  if (kind === "change-password" && code === "INVALID_PASSWORD") {
    return "当前密码错误";
  }

  if (kind === "change-email" && code === "SENSITIVE_SESSION_REQUIRED") {
    return "登录状态需要重新验证，请重新登录后再试";
  }

  if (kind === "delete-user" && code === "SESSION_EXPIRED") {
    return "登录状态需要重新验证，请重新登录后再试";
  }

  if (code === "EMAIL_NOT_VERIFIED") {
    return "请先完成邮箱验证";
  }

  return fallback;
}
