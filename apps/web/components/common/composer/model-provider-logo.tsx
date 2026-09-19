import type { ComponentType } from "react";
import { cn } from "@/lib/utils";
import type { ModelProvider } from "@/types/ai-search";

function OpenAILogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path
        fill="currentColor"
        d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.516 2.899A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.066.066 0 0 1-.027.057L9.985 19.288a4.5 4.5 0 0 1-6.385-4.984zm-1.24-9.69a4.48 4.48 0 0 1 2.365-1.972L4.864 8.344v5.588a.786.786 0 0 0 .392.681l5.843 3.369-2.02 1.168a.066.066 0 0 1-.063.005L3.86 16.326a4.5 4.5 0 0 1-1.5-7.712zm16.64 3.855-5.843-3.369 2.02-1.163a.066.066 0 0 1 .063-.005l5.628 3.251a4.5 4.5 0 0 1-.676 8.104v-5.677a.79.79 0 0 0-.192-.141zm2.01-3.023-.141-.085-4.774-2.758a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .027-.057l5.618-3.251a4.5 4.5 0 0 1 6.68 4.66zm-12.64 4.135-2.02-1.164a.066.066 0 0 1-.038-.057V6.601a4.5 4.5 0 0 1 7.375-3.453l-.142.08-4.778 2.758a.795.795 0 0 0-.393.681l-.004 6.737z"
      />
    </svg>
  );
}

function AnthropicLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path
        fill="currentColor"
        d="M13.83 3.24h2.91L12 20.76 7.26 3.24h2.91l1.83 6.38zm-1.83 0L7.26 3.24H4.35L9.09 20.76h2.91L12 3.24zm7.74 0h-2.91L12 20.76l4.74-17.52h2.91L15.82 9.62z"
      />
    </svg>
  );
}

function GoogleLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}

function DeepSeekLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <circle cx="12" cy="12" r="10" fill="#4D6BFE" />
      <path
        fill="#fff"
        d="M7 12c0-2.2 1.8-4.5 5-4.5s5 2.3 5 4.5-1.8 4.5-5 4.5S7 14.2 7 12zm5-2.5c-1.4 0-2.5 1.1-2.5 2.5s1.1 2.5 2.5 2.5 2.5-1.1 2.5-2.5S13.4 9.5 12 9.5z"
      />
    </svg>
  );
}

function ZhipuLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <rect width="24" height="24" rx="6" fill="#2454FF" />
      <text
        x="12"
        y="16"
        textAnchor="middle"
        fill="#fff"
        fontSize="11"
        fontWeight="700"
        fontFamily="system-ui,sans-serif"
      >
        Z
      </text>
    </svg>
  );
}

const LOGOS: Record<
  ModelProvider,
  ComponentType<{ className?: string }>
> = {
  openai: OpenAILogo,
  anthropic: AnthropicLogo,
  google: GoogleLogo,
  deepseek: DeepSeekLogo,
  zhipu: ZhipuLogo,
  platform: DeepSeekLogo,
};

export function ModelProviderLogo({
  provider,
  size = "md",
  className,
}: {
  provider: ModelProvider;
  size?: "sm" | "md";
  className?: string;
}) {
  const Logo = LOGOS[provider];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full",
        size === "sm" ? "size-5" : "size-6",
        className,
      )}
    >
      <Logo className={size === "sm" ? "size-5" : "size-6"} />
    </span>
  );
}
