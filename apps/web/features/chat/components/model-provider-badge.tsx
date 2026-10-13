import { cn } from "@/lib/utils";
import type { ModelProvider } from "@/types/ai-search";

const PROVIDER_META: Record<
  ModelProvider,
  { mark: string; className: string }
> = {
  openai: {
    mark: "O",
    className: "bg-[#10a37f] text-white",
  },
  anthropic: {
    mark: "A",
    className: "bg-[#d97757] text-white",
  },
  google: {
    mark: "G",
    className: "border border-line bg-white text-[#4285f4]",
  },
  deepseek: {
    mark: "D",
    className: "bg-[#4d6bfe] text-white",
  },
  zhipu: {
    mark: "Z",
    className: "bg-[#2454ff] text-white",
  },
  platform: {
    mark: "深",
    className: "bg-primary text-primary-foreground",
  },
};

export function ModelProviderBadge({
  provider,
  size = "md",
  className,
}: {
  provider: ModelProvider;
  size?: "sm" | "md";
  className?: string;
}) {
  const meta = PROVIDER_META[provider];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-semibold",
        size === "sm" ? "size-5 text-[10px]" : "size-6 text-[11px]",
        meta.className,
        className,
      )}
      aria-hidden
    >
      {meta.mark}
    </span>
  );
}
