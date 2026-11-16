"use client";

import * as React from "react";
import { CloudflareTurnstile } from "@/components/auth/turnstile";
import { getSocialProviderMeta } from "@/components/auth/social-providers";

const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;

type VerifyResponse = {
  url?: string;
  error?: string;
  message?: string;
};

/**
 * OAuth 登录前的独立人机验证页(通用 Provider)。
 *
 * 进入页面先询问后端是否已在 15 分钟内通过验证;已通过则直接跳转 Provider
 * 授权页,否则只显示一个 Cloudflare Turnstile 组件,完成后自动发送 token。
 */
export function OAuthVerifyPage({
  provider,
  turnstileAction,
}: {
  provider: string;
  turnstileAction?: string;
}) {
  const providerMeta = getSocialProviderMeta(provider);
  const providerLabel = providerMeta?.label ?? provider;

  // 后端要求先做人机验证时才显示验证框。
  const [needsChallenge, setNeedsChallenge] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const submittedRef = React.useRef(false);

  const verify = React.useCallback(
    async (captchaToken: string) => {
      if (submittedRef.current) return;
      submittedRef.current = true;

      try {
        const response = await fetch(
          `/api/auth/oauth/verify?provider=${encodeURIComponent(provider)}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: captchaToken }),
          },
        );

        const data = (await response.json().catch(() => null)) as
          | VerifyResponse
          | null;

        if (response.ok && data?.url) {
          window.location.assign(data.url);
          return;
        }

        setError(data?.message ?? "无法创建登录链接，请稍后重试");
      } catch {
        setError("登录请求失败，请检查网络后重试");
      } finally {
        submittedRef.current = false;
      }
    },
    [provider],
  );

  // 挂载时先询问后端是否已通过验证,已通过则自动进入 Provider 授权页。
  React.useEffect(() => {
    if (!TURNSTILE_SITE_KEY) return;
    let cancelled = false;

    (async () => {
      try {
        const response = await fetch(
          `/api/auth/oauth/verify?provider=${encodeURIComponent(provider)}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          },
        );

        const data = (await response.json().catch(() => null)) as
          | VerifyResponse
          | null;

        if (cancelled) return;
        if (response.ok && data?.url) {
          window.location.assign(data.url);
          return;
        }

        if (data?.error === "verification_required") {
          setNeedsChallenge(true);
          return;
        }

        setError(data?.message ?? "无法创建登录链接，请稍后重试");
      } catch {
        if (!cancelled) setError("登录请求失败，请检查网络后重试");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [provider]);

  const handleToken = React.useCallback(
    (nextToken: string) => {
      void verify(nextToken);
    },
    [verify],
  );

  const handleError = React.useCallback(() => {
    setError("人机验证失败，请检查网络后重试");
  }, []);

  if (!TURNSTILE_SITE_KEY) {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center bg-background p-4">
        <p className="text-[13px] text-danger" role="alert">
          人机验证未配置，暂时无法使用 {providerLabel} 登录。
        </p>
      </main>
    );
  }

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-background p-4">
      {needsChallenge && (
        <CloudflareTurnstile
          siteKey={TURNSTILE_SITE_KEY}
          action={turnstileAction}
          scale={1.5}
          onToken={handleToken}
          onError={handleError}
        />
      )}
      {error && (
        <div className="mt-4 text-center" role="alert">
          <p className="text-[13px] text-danger">{error}</p>
          <button
            type="button"
            className="mt-3 rounded-md px-3 py-2 text-[13px] font-medium text-primary hover:bg-chip"
            onClick={() => window.location.reload()}
          >
            重新尝试
          </button>
        </div>
      )}
    </main>
  );
}
