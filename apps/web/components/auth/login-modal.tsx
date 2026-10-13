"use client";

import * as React from "react";
import Link from "next/link";
import { Check, CheckCircle2, Circle, X } from "lucide-react";
import { authClient } from "@/components/auth/auth-client";
import {
  sendRegistrationEmailOtp,
  verifyRegistrationEmailOtp,
} from "@/components/auth/registration-client";
import { listSocialProviders } from "@/components/auth/social-providers";
import { CloudflareTurnstile } from "@/components/auth/turnstile";
import {
  getAuthErrorMessage,
  PASSWORD_POLICY_MESSAGE,
} from "@/components/auth/auth-errors";
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  validatePasswordPolicy,
} from "@/lib/auth/policies/password";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;

export interface LoginModalProps {
  open: boolean;
  notice?: string | null;
  onClose: () => void;
  onSuccess?: () => void | Promise<void>;
}

type AuthTab = "login" | "register";
type LoginMethod = "password" | "code";
type RegisterStage = "email" | "verify-email" | "credentials";
type RegisterOtpIntent = "initial" | "resend";
type Submission =
  | "login"
  | "otp-send"
  | "otp-login"
  | "register-send"
  | "register-resend"
  | "register-verify"
  | "register"
  | null;

type SendOtpResult = "sent" | "captcha-required" | "error";

function Field({
  label,
  ...props
}: React.ComponentProps<"input"> & { label: string }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[13px] font-medium text-ink-2">{label}</span>
      <Input {...props} />
    </label>
  );
}

function PasswordRule({
  label,
  valid,
  started,
}: {
  label: string;
  valid: boolean;
  started: boolean;
}) {
  const state = !started ? "neutral" : valid ? "valid" : "invalid";

  return (
    <li
      className={cn(
        "flex items-center gap-2 text-xs transition-colors",
        state === "neutral" && "text-faint",
        state === "valid" && "text-success",
        state === "invalid" && "text-danger",
      )}
    >
      {state === "neutral" ? (
        <Circle className="size-4 shrink-0" aria-hidden="true" />
      ) : (
        <span
          className="flex size-4 shrink-0 items-center justify-center rounded-full border border-current"
          aria-hidden="true"
        >
          {state === "valid" ? (
            <Check className="size-2.5" strokeWidth={2.5} />
          ) : (
            <X className="size-2.5" strokeWidth={2.5} />
          )}
        </span>
      )}
      <span>{label}</span>
    </li>
  );
}

function PasswordRequirements({
  password,
  started,
}: {
  password: string;
  started: boolean;
}) {
  const result = validatePasswordPolicy(password);

  return (
    <div
      id="registration-password-requirements"
      className="mt-2 w-full rounded-xl border border-line bg-popover p-3 shadow-pop lg:absolute lg:left-[calc(100%+0.75rem)] lg:top-6 lg:z-20 lg:mt-0 lg:w-64"
    >
      <p className="text-xs font-medium text-ink-2">密码需满足以下条件</p>
      <ul className="mt-2.5 flex flex-col gap-2">
        <PasswordRule
          label={`${PASSWORD_MIN_LENGTH}–${PASSWORD_MAX_LENGTH} 位`}
          valid={result.lengthValid}
          started={started}
        />
        <PasswordRule
          label="包含大写字母"
          valid={!result.missing.includes("uppercase")}
          started={started}
        />
        <PasswordRule
          label="包含小写字母"
          valid={!result.missing.includes("lowercase")}
          started={started}
        />
        <PasswordRule
          label="包含数字"
          valid={!result.missing.includes("digit")}
          started={started}
        />
      </ul>
    </div>
  );
}

function normalizeEmail(email: string) {
  return email.trim().toLowerCase();
}

function errorCodeOf(error: unknown): string | undefined {
  if (!error || typeof error !== "object") return undefined;
  const code = (error as { code?: unknown }).code;
  return typeof code === "string" ? code : undefined;
}

export function LoginModal({
  open,
  notice,
  onClose,
  onSuccess,
}: LoginModalProps) {
  const { refetch: refetchSession } = authClient.useSession();
  const pendingEmailRef = React.useRef<string | null>(null);
  const registerPendingEmailRef = React.useRef<string | null>(null);
  const registerPendingIntentRef = React.useRef<RegisterOtpIntent>("initial");
  const [showTurnstile, setShowTurnstile] = React.useState(false);
  const [registerShowTurnstile, setRegisterShowTurnstile] =
    React.useState(false);
  const [authTab, setAuthTab] = React.useState<AuthTab>("login");
  const [loginMethod, setLoginMethod] =
    React.useState<LoginMethod>("password");
  const [submission, setSubmission] = React.useState<Submission>(null);

  const [loginEmail, setLoginEmail] = React.useState("");
  const [loginPassword, setLoginPassword] = React.useState("");
  const [loginError, setLoginError] = React.useState<string | null>(null);
  const [code, setCode] = React.useState("");
  const [codeError, setCodeError] = React.useState<string | null>(null);
  const [codeNotice, setCodeNotice] = React.useState<string | null>(null);
  const [codeCooldown, setCodeCooldown] = React.useState(0);

  const [registerStage, setRegisterStage] =
    React.useState<RegisterStage>("email");
  const [registerEmail, setRegisterEmail] = React.useState("");
  const [registerChallengeId, setRegisterChallengeId] = React.useState("");
  const [registerEmailError, setRegisterEmailError] = React.useState<
    string | null
  >(null);
  const [registerEmailNotice, setRegisterEmailNotice] = React.useState<
    string | null
  >(null);
  const [registerCode, setRegisterCode] = React.useState("");
  const [registerCodeError, setRegisterCodeError] =
    React.useState<string | null>(null);
  const [registerCodeNotice, setRegisterCodeNotice] =
    React.useState<string | null>(null);
  const [registerCodeCooldown, setRegisterCodeCooldown] = React.useState(0);
  const [registerName, setRegisterName] = React.useState("");
  const [registerPassword, setRegisterPassword] = React.useState("");
  const [registerPasswordConfirm, setRegisterPasswordConfirm] =
    React.useState("");
  const [registerPasswordFocused, setRegisterPasswordFocused] =
    React.useState(false);
  const [registerPasswordTouched, setRegisterPasswordTouched] =
    React.useState(false);
  const [registerPasswordStarted, setRegisterPasswordStarted] =
    React.useState(false);
  const [registerError, setRegisterError] = React.useState<string | null>(null);
  const [socialError, setSocialError] = React.useState<string | null>(null);
  const [socialSubmitting, setSocialSubmitting] = React.useState(false);

  const registerPasswordValidation = validatePasswordPolicy(registerPassword);
  const showRegisterPasswordResult =
    registerPasswordTouched && !registerPasswordFocused;

  const resetForm = React.useCallback(() => {
    setAuthTab("login");
    setLoginMethod("password");
    setSubmission(null);
    setShowTurnstile(false);
    pendingEmailRef.current = null;
    setLoginEmail("");
    setLoginPassword("");
    setLoginError(null);
    setCode("");
    setCodeError(null);
    setCodeNotice(null);
    setCodeCooldown(0);
    setRegisterStage("email");
    setRegisterEmail("");
    setRegisterChallengeId("");
    setRegisterEmailError(null);
    setRegisterEmailNotice(null);
    setRegisterCode("");
    setRegisterCodeError(null);
    setRegisterCodeNotice(null);
    setRegisterCodeCooldown(0);
    setRegisterName("");
    setRegisterPassword("");
    setRegisterPasswordConfirm("");
    setRegisterPasswordFocused(false);
    setRegisterPasswordTouched(false);
    setRegisterPasswordStarted(false);
    setRegisterError(null);
    setRegisterShowTurnstile(false);
    registerPendingEmailRef.current = null;
    registerPendingIntentRef.current = "initial";
    setSocialError(null);
    setSocialSubmitting(false);
  }, []);

  const handleClose = React.useCallback(() => {
    resetForm();
    onClose();
  }, [onClose, resetForm]);

  const handleAuthSuccess = React.useCallback(async () => {
    await refetchSession();
    if (onSuccess) {
      try {
        await onSuccess();
      } catch (error) {
        console.error("登录成功后的操作执行失败", error);
      }
    }
    handleClose();
  }, [handleClose, onSuccess, refetchSession]);

  React.useEffect(() => {
    if (codeCooldown <= 0) return;

    const timer = window.setInterval(() => {
      setCodeCooldown((value) => Math.max(0, value - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [codeCooldown]);

  React.useEffect(() => {
    if (registerCodeCooldown <= 0) return;

    const timer = window.setInterval(() => {
      setRegisterCodeCooldown((value) => Math.max(0, value - 1));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [registerCodeCooldown]);

  const handleAuthTabChange = (value: string) => {
    if (submission || socialSubmitting) return;
    setAuthTab(value as AuthTab);
    setShowTurnstile(false);
    setRegisterShowTurnstile(false);
    pendingEmailRef.current = null;
    registerPendingEmailRef.current = null;
    setLoginError(null);
    setCodeError(null);
    setCodeNotice(null);
    setRegisterEmailError(null);
    setRegisterEmailNotice(null);
    setRegisterCodeError(null);
    setRegisterCodeNotice(null);
    setRegisterError(null);
    setSocialError(null);
  };

  const handleLoginMethodChange = (method: LoginMethod) => {
    if (submission) return;
    setLoginMethod(method);
    setShowTurnstile(false);
    pendingEmailRef.current = null;
    setLoginError(null);
    setCodeError(null);
    setCodeNotice(null);
  };

  const sendOtp = React.useCallback(
    async (
      email: string,
      turnstileToken?: string,
    ): Promise<SendOtpResult> => {
      setSubmission("otp-send");
      try {
        const { error } = await authClient.emailOtp.sendVerificationOtp(
          { email, type: "sign-in" },
          turnstileToken
            ? { headers: { "x-captcha-response": turnstileToken } }
            : {},
        );

        if (error) {
          if (
            !turnstileToken &&
            (errorCodeOf(error) === "MISSING_RESPONSE" ||
              errorCodeOf(error) === "VERIFICATION_FAILED")
          ) {
            return "captcha-required";
          }

          setCodeError(
            getAuthErrorMessage(error, "验证码发送失败，请稍后重试", "otp"),
          );
          return "error";
        }

        setCodeCooldown(60);
        setCodeNotice("验证码已发送，请查收邮件");
        return "sent";
      } catch (error) {
        setCodeError(
          getAuthErrorMessage(error, "验证码发送失败，请稍后重试", "otp"),
        );
        return "error";
      } finally {
        setSubmission(null);
      }
    },
    [],
  );

  const handleTurnstileToken = React.useCallback(
    async (token: string) => {
      setShowTurnstile(false);
      setCodeNotice(null);

      const email = pendingEmailRef.current;
      pendingEmailRef.current = null;
      if (!email) return;
      await sendOtp(email, token);
    },
    [sendOtp],
  );

  const handleTurnstileError = React.useCallback(() => {
    setShowTurnstile(false);
    setCodeError("人机验证失败，请重试");
  }, []);

  const handleSendOtp = async () => {
    setCodeError(null);
    setCodeNotice(null);

    const email = normalizeEmail(loginEmail);
    if (!email) {
      setCodeError("请输入邮箱");
      return;
    }
    if (codeCooldown > 0) return;

    // 先不带 token 尝试发送;后端若判定需要人机验证则弹出 Turnstile。
    const result = await sendOtp(email);
    if (result === "captcha-required") {
      pendingEmailRef.current = email;
      setShowTurnstile(true);
      setCodeNotice("请先完成上方人机验证");
    }
  };

  const sendRegisterOtp = React.useCallback(
    async (
      email: string,
      intent: RegisterOtpIntent,
      turnstileToken?: string,
    ): Promise<SendOtpResult> => {
      setSubmission(intent === "initial" ? "register-send" : "register-resend");
      if (intent === "initial") {
        setRegisterEmailError(null);
        setRegisterEmailNotice(null);
      } else {
        setRegisterCodeError(null);
        setRegisterCodeNotice(null);
      }

      try {
        const { data, error } = await sendRegistrationEmailOtp(
          email,
          turnstileToken,
        );

        if (error || !data?.challengeId) {
          if (
            !turnstileToken &&
            (errorCodeOf(error) === "MISSING_RESPONSE" ||
              errorCodeOf(error) === "VERIFICATION_FAILED")
          ) {
            return "captcha-required";
          }

          const message = getAuthErrorMessage(
            error,
            "验证码发送失败，请稍后重试",
            "otp",
          );
          if (intent === "initial") setRegisterEmailError(message);
          else setRegisterCodeError(message);
          return "error";
        }

        setRegisterEmail(email);
        setRegisterChallengeId(data.challengeId);
        setRegisterCode("");
        setRegisterCodeCooldown(60);
        setRegisterStage("verify-email");
        setRegisterEmailNotice(null);
        setRegisterCodeNotice("验证码已发送，请查收邮件");
        return "sent";
      } catch (error) {
        const message = getAuthErrorMessage(
          error,
          "验证码发送失败，请稍后重试",
          "otp",
        );
        if (intent === "initial") setRegisterEmailError(message);
        else setRegisterCodeError(message);
        return "error";
      } finally {
        setSubmission(null);
      }
    },
    [],
  );

  const handleRegisterTurnstileToken = React.useCallback(
    async (token: string) => {
      setRegisterShowTurnstile(false);

      const email = registerPendingEmailRef.current;
      const intent = registerPendingIntentRef.current;
      registerPendingEmailRef.current = null;
      if (!email) return;
      await sendRegisterOtp(email, intent, token);
    },
    [sendRegisterOtp],
  );

  const handleRegisterTurnstileError = React.useCallback(() => {
    setRegisterShowTurnstile(false);
    if (registerPendingIntentRef.current === "initial") {
      setRegisterEmailNotice(null);
      setRegisterEmailError("人机验证失败，请重试");
    } else {
      setRegisterCodeNotice(null);
      setRegisterCodeError("人机验证失败，请重试");
    }
  }, []);

  const handleBeginRegistration = async (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();
    setRegisterEmailError(null);
    setRegisterEmailNotice(null);

    const email = normalizeEmail(registerEmail);
    if (!email) {
      setRegisterEmailError("请输入邮箱");
      return;
    }

    const result = await sendRegisterOtp(email, "initial");
    if (result === "captcha-required") {
      registerPendingEmailRef.current = email;
      registerPendingIntentRef.current = "initial";
      setRegisterShowTurnstile(true);
      setRegisterEmailNotice("请先完成上方人机验证");
    }
  };

  const handleResendRegisterOtp = async () => {
    setRegisterCodeError(null);
    setRegisterCodeNotice(null);
    if (registerCodeCooldown > 0) return;

    const email = normalizeEmail(registerEmail);
    if (!email) {
      setRegisterCodeError("请输入邮箱");
      return;
    }

    const result = await sendRegisterOtp(email, "resend");
    if (result === "captcha-required") {
      registerPendingEmailRef.current = email;
      registerPendingIntentRef.current = "resend";
      setRegisterShowTurnstile(true);
      setRegisterCodeNotice("请先完成上方人机验证");
    }
  };

  const handleOtpLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCodeError(null);
    setCodeNotice(null);

    const email = normalizeEmail(loginEmail);
    const otp = code.trim();
    if (!email) {
      setCodeError("请输入邮箱");
      return;
    }
    if (!/^\d{6}$/.test(otp)) {
      setCodeError("请输入6位数字验证码");
      return;
    }

    setSubmission("otp-login");
    try {
      const { error } = await authClient.signIn.emailOtp({ email, otp });

      if (error) {
        setCodeError(
          getAuthErrorMessage(error, "验证码登录失败，请稍后重试", "otp"),
        );
        return;
      }

      await handleAuthSuccess();
    } catch (error) {
      setCodeError(
        getAuthErrorMessage(error, "验证码登录失败，请稍后重试", "otp"),
      );
    } finally {
      setSubmission(null);
    }
  };

  const handlePasswordLogin = async (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();
    setLoginError(null);

    const email = normalizeEmail(loginEmail);
    if (!email) {
      setLoginError("请输入邮箱");
      return;
    }
    if (!loginPassword) {
      setLoginError("请输入密码");
      return;
    }

    setSubmission("login");
    try {
      const { error } = await authClient.signIn.email({
        email,
        password: loginPassword,
      });

      if (error) {
        setLoginError(
          getAuthErrorMessage(error, "登录失败，请稍后重试", "login"),
        );
        return;
      }

      await handleAuthSuccess();
    } catch (error) {
      setLoginError(getAuthErrorMessage(error, "登录失败，请稍后重试", "login"));
    } finally {
      setSubmission(null);
    }
  };

  const handleRegisterEmailVerification = async (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();
    setRegisterCodeError(null);
    setRegisterCodeNotice(null);

    const otp = registerCode.trim();
    if (!/^\d{6}$/.test(otp)) {
      setRegisterCodeError("请输入6位数字验证码");
      return;
    }
    if (!registerChallengeId) {
      setRegisterCodeError("验证码已失效，请重新获取");
      return;
    }

    setSubmission("register-verify");
    try {
      const { error } = await verifyRegistrationEmailOtp({
        email: normalizeEmail(registerEmail),
        otp,
        challengeId: registerChallengeId,
      });

      if (error) {
        setRegisterCodeError(
          getAuthErrorMessage(error, "邮箱验证失败，请稍后重试", "otp"),
        );
        return;
      }

      setRegisterCodeNotice(null);
      setRegisterStage("credentials");
    } catch (error) {
      setRegisterCodeError(
        getAuthErrorMessage(error, "邮箱验证失败，请稍后重试", "otp"),
      );
    } finally {
      setSubmission(null);
    }
  };

  const handleChangeRegisterEmail = () => {
    if (submission) return;
    setRegisterStage("email");
    setRegisterChallengeId("");
    setRegisterCode("");
    setRegisterCodeError(null);
    setRegisterCodeNotice(null);
    setRegisterCodeCooldown(0);
    setRegisterShowTurnstile(false);
    registerPendingEmailRef.current = null;
  };

  const handleRegistration = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setRegisterError(null);
    setRegisterPasswordTouched(true);

    const name = registerName.trim();
    const email = normalizeEmail(registerEmail);
    if (!name) {
      setRegisterError("请输入昵称");
      return;
    }
    if (!email) {
      setRegisterError("请输入邮箱");
      return;
    }
    if (!registerPassword) {
      setRegisterError("请输入密码");
      return;
    }
    if (!registerPasswordValidation.valid) {
      setRegisterError(PASSWORD_POLICY_MESSAGE);
      return;
    }
    if (registerPassword !== registerPasswordConfirm) {
      setRegisterError("两次输入的密码不一致");
      return;
    }

    setSubmission("register");
    try {
      const { data, error } = await authClient.signUp.email({
        name,
        email,
        password: registerPassword,
      });

      if (error || !data) {
        setRegisterError(
          getAuthErrorMessage(error, "注册失败，请稍后重试", "register"),
        );
        return;
      }

      if (data.token === null) {
        const { error: signInError } = await authClient.signIn.email({
          email,
          password: registerPassword,
        });

        if (signInError) {
          setLoginEmail(email);
          setLoginPassword(registerPassword);
          setLoginMethod("password");
          setAuthTab("login");
          setLoginError("注册成功，但自动登录失败，请手动登录");
          return;
        }
      }

      await handleAuthSuccess();
    } catch (error) {
      setRegisterError(
        getAuthErrorMessage(error, "注册失败，请稍后重试", "register"),
      );
    } finally {
      setSubmission(null);
    }
  };

  const handleSocialLogin = async (providerId: string) => {
    if (submission || socialSubmitting) return;

    // 跳转式人机验证:先进入独立验证页,完成 Turnstile 后由后端发起 OAuth。
    if (TURNSTILE_SITE_KEY) {
      window.location.assign(`/login/${providerId}`);
      return;
    }

    setSocialSubmitting(true);
    setSocialError(null);

    try {
      const { error } = await authClient.signIn.social({
        provider: providerId,
        callbackURL: "/",
      });

      if (error) {
        setSocialError(
          getAuthErrorMessage(error, "登录失败，请稍后重试", "login"),
        );
        setSocialSubmitting(false);
      }
    } catch (error) {
      setSocialError(
        getAuthErrorMessage(error, "登录失败，请稍后重试", "login"),
      );
      setSocialSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-overlay/40 p-4"
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={authTab === "login" ? "登录" : "注册"}
        className="max-h-[calc(100dvh-2rem)] w-full max-w-sm overflow-y-auto rounded-2xl bg-popover p-6 shadow-card lg:max-h-none lg:overflow-visible"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-ink">
            {authTab === "login" ? "登录深知" : "注册深知"}
          </h2>
          <button
            type="button"
            aria-label="关闭"
            className="rounded-md p-1 text-faint hover:bg-chip hover:text-ink"
            onClick={handleClose}
            disabled={Boolean(submission)}
          >
            <X className="size-4" />
          </button>
        </div>

        {notice && (
          <div
            className="mt-4 flex items-start gap-2 rounded-xl bg-success-soft px-3 py-2.5 text-[13px] leading-5 text-success"
            role="status"
            aria-live="polite"
          >
            <CheckCircle2
              className="mt-0.5 size-4 shrink-0"
              aria-hidden="true"
            />
            <span>{notice}</span>
          </div>
        )}

        <Tabs
          value={authTab}
          onValueChange={handleAuthTabChange}
          className={notice ? "mt-3" : "mt-4"}
        >
          <TabsList className="grid w-full grid-cols-2 gap-0 border-b border-line">
            <TabsTrigger
              value="login"
              className="rounded-none border-b-2 border-transparent py-2 data-[state=active]:border-primary"
              disabled={Boolean(submission) || socialSubmitting}
            >
              登录
            </TabsTrigger>
            <TabsTrigger
              value="register"
              className="rounded-none border-b-2 border-transparent py-2 data-[state=active]:border-primary"
              disabled={Boolean(submission) || socialSubmitting}
            >
              注册
            </TabsTrigger>
          </TabsList>

          <TabsContent value="login">
            <form
              className="mt-5 flex flex-col gap-4"
              onSubmit={
                loginMethod === "password"
                  ? handlePasswordLogin
                  : handleOtpLogin
              }
              noValidate
            >
              <Field
                label="邮箱"
                type="email"
                placeholder="请输入邮箱"
                autoComplete="email"
                value={loginEmail}
                onChange={(event) => setLoginEmail(event.target.value)}
                disabled={Boolean(submission)}
              />

              {loginMethod === "password" ? (
                <Field
                  label="密码"
                  type="password"
                  placeholder="请输入密码"
                  autoComplete="current-password"
                  value={loginPassword}
                  onChange={(event) => setLoginPassword(event.target.value)}
                  disabled={Boolean(submission)}
                />
              ) : (
                <>
                  {showTurnstile && TURNSTILE_SITE_KEY && (
                    <CloudflareTurnstile
                      siteKey={TURNSTILE_SITE_KEY}
                      onToken={handleTurnstileToken}
                      onError={handleTurnstileError}
                    />
                  )}
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[13px] font-medium text-ink-2">
                      验证码
                    </span>
                    <div className="flex gap-2">
                      <Input
                        placeholder="请输入6位验证码"
                        className="min-w-0 flex-1"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        maxLength={6}
                        value={code}
                        onChange={(event) =>
                          setCode(event.target.value.replace(/\D/g, ""))
                        }
                        disabled={Boolean(submission)}
                      />
                      <Button
                        variant="outline"
                        type="button"
                        className="shrink-0"
                        disabled={Boolean(submission) || codeCooldown > 0}
                        onClick={handleSendOtp}
                        aria-busy={submission === "otp-send"}
                      >
                        {submission === "otp-send"
                          ? "发送中..."
                          : codeCooldown > 0
                            ? `${codeCooldown}s后重发`
                            : "获取验证码"}
                      </Button>
                    </div>
                  </div>
                </>
              )}

              <div className="-mt-1.5 flex items-center justify-between">
                <button
                  type="button"
                  disabled={Boolean(submission)}
                  onClick={() =>
                    handleLoginMethodChange(
                      loginMethod === "password" ? "code" : "password",
                    )
                  }
                  className="text-[13px] font-medium text-primary hover:underline disabled:pointer-events-none disabled:opacity-50"
                >
                  {loginMethod === "password" ? "验证码登录" : "密码登录"}
                </button>
                <Link
                  href="/reset-password"
                  aria-disabled={Boolean(submission)}
                  onClick={(event) => {
                    if (submission) event.preventDefault();
                  }}
                  className="text-[13px] font-medium text-primary hover:underline aria-disabled:pointer-events-none aria-disabled:opacity-50"
                >
                  忘记密码?
                </Link>
              </div>

              {loginMethod === "code" && codeNotice && (
                <p className="-mt-2 text-xs leading-5 text-muted" role="status">
                  {codeNotice}
                </p>
              )}
              {loginMethod === "password" && loginError && (
                <p className="-mt-2 text-[13px] text-danger" role="alert">
                  {loginError}
                </p>
              )}
              {loginMethod === "code" && codeError && (
                <p className="-mt-2 text-[13px] text-danger" role="alert">
                  {codeError}
                </p>
              )}

              <Button
                type="submit"
                className="w-full"
                disabled={Boolean(submission)}
                aria-busy={
                  submission === "login" || submission === "otp-login"
                }
              >
                {submission === "login" || submission === "otp-login"
                  ? "登录中..."
                  : "登录"}
              </Button>
            </form>
          </TabsContent>

          <TabsContent value="register">
            {registerStage === "email" && (
              <form
                className="mt-5 flex flex-col gap-4"
                onSubmit={handleBeginRegistration}
                noValidate
              >
                <p className="text-[13px] leading-5 text-muted">
                  先验证邮箱，再设置昵称和密码
                </p>
                <Field
                  label="邮箱"
                  type="email"
                  placeholder="请输入邮箱"
                  autoComplete="email"
                  value={registerEmail}
                  onChange={(event) => setRegisterEmail(event.target.value)}
                  disabled={Boolean(submission)}
                />
                {registerShowTurnstile && TURNSTILE_SITE_KEY && (
                  <CloudflareTurnstile
                    siteKey={TURNSTILE_SITE_KEY}
                    onToken={handleRegisterTurnstileToken}
                    onError={handleRegisterTurnstileError}
                  />
                )}
                {registerEmailNotice && (
                  <p className="-mt-2 text-xs leading-5 text-muted" role="status">
                    {registerEmailNotice}
                  </p>
                )}
                {registerEmailError && (
                  <p className="-mt-2 text-[13px] text-danger" role="alert">
                    {registerEmailError}
                  </p>
                )}
                <Button
                  type="submit"
                  className="mt-1 w-full"
                  disabled={Boolean(submission)}
                  aria-busy={submission === "register-send"}
                >
                  {submission === "register-send"
                    ? "发送中..."
                    : "获取验证码"}
                </Button>
              </form>
            )}

            {registerStage === "verify-email" && (
              <form
                className="mt-5 flex flex-col gap-4"
                onSubmit={handleRegisterEmailVerification}
                noValidate
              >
                <Field
                  label="邮箱"
                  type="email"
                  value={registerEmail}
                  readOnly
                  aria-readonly="true"
                  className="bg-panel text-muted"
                />
                <div className="-mt-2 flex justify-end">
                  <button
                    type="button"
                    disabled={Boolean(submission)}
                    onClick={handleChangeRegisterEmail}
                    className="text-[13px] font-medium text-primary hover:underline disabled:pointer-events-none disabled:opacity-50"
                  >
                    更换邮箱
                  </button>
                </div>
                {registerShowTurnstile && TURNSTILE_SITE_KEY && (
                  <CloudflareTurnstile
                    siteKey={TURNSTILE_SITE_KEY}
                    onToken={handleRegisterTurnstileToken}
                    onError={handleRegisterTurnstileError}
                  />
                )}
                <div className="flex flex-col gap-1.5">
                  <span className="text-[13px] font-medium text-ink-2">
                    验证码
                  </span>
                  <div className="flex gap-2">
                    <Input
                      placeholder="请输入6位验证码"
                      className="min-w-0 flex-1"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={6}
                      value={registerCode}
                      onChange={(event) =>
                        setRegisterCode(event.target.value.replace(/\D/g, ""))
                      }
                      disabled={Boolean(submission)}
                    />
                    <Button
                      variant="outline"
                      type="button"
                      className="shrink-0"
                      disabled={
                        Boolean(submission) || registerCodeCooldown > 0
                      }
                      onClick={handleResendRegisterOtp}
                      aria-busy={submission === "register-resend"}
                    >
                      {submission === "register-resend"
                        ? "发送中..."
                        : registerCodeCooldown > 0
                          ? `${registerCodeCooldown}s后重发`
                          : "重新发送"}
                    </Button>
                  </div>
                </div>
                {registerCodeNotice && (
                  <p className="-mt-2 text-xs leading-5 text-muted" role="status">
                    {registerCodeNotice}
                  </p>
                )}
                {registerCodeError && (
                  <p className="-mt-2 text-[13px] text-danger" role="alert">
                    {registerCodeError}
                  </p>
                )}
                <Button
                  type="submit"
                  className="mt-1 w-full"
                  disabled={Boolean(submission)}
                  aria-busy={submission === "register-verify"}
                >
                  {submission === "register-verify"
                    ? "验证中..."
                    : "验证邮箱"}
                </Button>
              </form>
            )}

            {registerStage === "credentials" && (
              <form
                className="mt-5 flex flex-col gap-4"
                onSubmit={handleRegistration}
                noValidate
              >
                <label className="flex flex-col gap-1.5">
                  <span className="text-[13px] font-medium text-ink-2">邮箱</span>
                  <div className="relative">
                    <Input
                      type="email"
                      value={registerEmail}
                      readOnly
                      aria-readonly="true"
                      className="bg-panel pr-16 text-muted"
                    />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium text-success">
                      已验证
                    </span>
                  </div>
                </label>
                <Field
                  label="昵称"
                  placeholder="请输入昵称"
                  autoComplete="name"
                  value={registerName}
                  onChange={(event) => setRegisterName(event.target.value)}
                  disabled={Boolean(submission)}
                />
                <div className="relative">
                  <label className="flex flex-col gap-1.5">
                    <span className="text-[13px] font-medium text-ink-2">
                      密码
                    </span>
                    <div className="relative">
                      <Input
                        type="password"
                        placeholder="请输入密码"
                        autoComplete="new-password"
                        minLength={PASSWORD_MIN_LENGTH}
                        value={registerPassword}
                        onFocus={() => setRegisterPasswordFocused(true)}
                        onBlur={() => {
                          setRegisterPasswordFocused(false);
                          setRegisterPasswordTouched(true);
                        }}
                        onChange={(event) => {
                          setRegisterPassword(event.target.value);
                          setRegisterPasswordTouched(true);
                          setRegisterPasswordStarted(true);
                        }}
                        aria-describedby={
                          registerPasswordFocused
                            ? "registration-password-requirements"
                            : showRegisterPasswordResult
                              ? "registration-password-result"
                              : undefined
                        }
                        aria-invalid={
                          showRegisterPasswordResult &&
                          !registerPasswordValidation.valid
                            ? true
                            : undefined
                        }
                        disabled={Boolean(submission)}
                        className={cn(
                          showRegisterPasswordResult && "pr-10",
                          showRegisterPasswordResult &&
                            registerPasswordValidation.valid &&
                            "border-success focus-visible:border-success focus-visible:ring-success/15",
                          showRegisterPasswordResult &&
                            !registerPasswordValidation.valid &&
                            "border-danger focus-visible:border-danger focus-visible:ring-danger/15",
                        )}
                      />
                      {showRegisterPasswordResult && (
                        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2">
                          {registerPasswordValidation.valid ? (
                            <CheckCircle2
                              className="size-4 text-success"
                              aria-hidden="true"
                            />
                          ) : (
                            <span className="flex size-4 items-center justify-center rounded-full border border-danger text-danger">
                              <X
                                className="size-2.5"
                                strokeWidth={2.5}
                                aria-hidden="true"
                              />
                            </span>
                          )}
                        </span>
                      )}
                    </div>
                  </label>

                  {registerPasswordFocused && (
                    <PasswordRequirements
                      password={registerPassword}
                      started={registerPasswordStarted}
                    />
                  )}
                  {showRegisterPasswordResult && (
                    <p
                      id="registration-password-result"
                      className={cn(
                        "mt-1.5 text-xs",
                        registerPasswordValidation.valid
                          ? "text-success"
                          : "text-danger",
                      )}
                      role={
                        registerPasswordValidation.valid ? "status" : "alert"
                      }
                    >
                      {registerPasswordValidation.valid
                        ? "密码符合要求"
                        : "密码尚未满足全部要求"}
                    </p>
                  )}
                </div>
                <Field
                  label="确认密码"
                  type="password"
                  placeholder="请再次输入密码"
                  autoComplete="new-password"
                  minLength={PASSWORD_MIN_LENGTH}
                  value={registerPasswordConfirm}
                  onChange={(event) =>
                    setRegisterPasswordConfirm(event.target.value)
                  }
                  disabled={Boolean(submission)}
                />
                {registerError && (
                  <p className="-mt-2 text-[13px] text-danger" role="alert">
                    {registerError}
                  </p>
                )}
                <Button
                  type="submit"
                  className="mt-1 w-full"
                  disabled={Boolean(submission)}
                  aria-busy={submission === "register"}
                >
                  {submission === "register" ? "注册中..." : "完成注册"}
                </Button>
              </form>
            )}
          </TabsContent>
        </Tabs>

        {authTab === "login" && (
          <div className="mt-6">
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-line" />
              <span className="text-xs text-faint">或使用以下账号登录</span>
              <div className="h-px flex-1 bg-line" />
            </div>

            <div className="mt-4 flex justify-center gap-3">
              {listSocialProviders().map((provider) => (
                <button
                  key={provider.id}
                  type="button"
                  aria-label={`使用 ${provider.label} 登录`}
                  disabled={Boolean(submission) || socialSubmitting}
                  onClick={() => handleSocialLogin(provider.id)}
                  className="flex size-11 items-center justify-center rounded-full border border-line text-ink-2 transition hover:border-ink hover:text-ink disabled:pointer-events-none disabled:opacity-50"
                >
                  <provider.icon className="size-5" />
                </button>
              ))}
            </div>

            {socialError && (
              <p className="mt-3 text-center text-[13px] text-danger" role="alert">
                {socialError}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
