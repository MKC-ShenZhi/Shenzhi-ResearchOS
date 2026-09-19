import { ArrowRight } from "lucide-react";
import { agentReferences } from "@/features/search/deep-search/data";
import { cn } from "@/lib/utils";

const TONE_COLORS: Record<string, string> = {
  violet: "bg-primary",
  green: "bg-success",
  amber: "bg-[#B45309] dark:bg-[#d99a2b]",
  gray: "bg-muted",
};

/** 参考来源卡片组 —— 10 篇引用文献的横向卡片 */
export function ReferenceGrid() {
  return (
    <section className="rounded-2xl bg-card p-6 shadow-card">
      <div className="flex items-center justify-between">
        <h3 className="text-[15px] font-semibold text-ink">
          参考来源 · 10 篇
        </h3>
        <button
          type="button"
          className="flex cursor-pointer items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          查看全部
          <ArrowRight className="size-3" />
        </button>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {agentReferences.map((ref) => (
          <article
            key={ref.id}
            className={cn(
              "cursor-pointer rounded-xl border border-line p-3.5 transition-colors hover:border-primary/40",
              ref.recommended &&
                "border-[#FDE68A] bg-[#FFFBEB] dark:border-[#5a4a1a] dark:bg-[#26200f]",
            )}
          >
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-full text-xs font-semibold text-white",
                  TONE_COLORS[ref.tone],
                )}
              >
                {ref.id}
              </span>
              <span className="text-[11px] text-faint">{ref.venue}</span>
            </div>
            <p className="mt-2 line-clamp-3 text-[13px] font-medium leading-snug text-ink-2">
              {ref.title}
            </p>
            <p className="mt-2 text-[11px] text-faint">
              {ref.author} · {ref.citations}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
