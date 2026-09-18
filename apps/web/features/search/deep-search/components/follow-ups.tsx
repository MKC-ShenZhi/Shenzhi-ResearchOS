import { ArrowRight } from "lucide-react";
import { followUps } from "@/features/search/deep-search/data";

/** 继续深入研究 —— 追问建议 chips */
export function FollowUps() {
  return (
    <section>
      <p className="text-xs text-faint">继续深入研究</p>
      <div className="mt-2.5 flex flex-wrap gap-2.5">
        {followUps.map((question) => (
          <button
            key={question}
            type="button"
            className="flex h-9 cursor-pointer items-center gap-2 rounded-full border border-line bg-card px-4 text-[13px] text-ink-2 transition-colors hover:border-primary hover:text-primary"
          >
            {question}
            <ArrowRight className="size-3.5" />
          </button>
        ))}
      </div>
    </section>
  );
}
