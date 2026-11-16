import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { recentResearch } from "@/features/search/deep-search/data";
import { cn } from "@/lib/utils";

/** 近期研究栏 —— AI 研究助手页左侧 */
export function ResearchNav() {
  return (
    <aside className="w-52 shrink-0">
      <Button className="w-full rounded-xl">
        <Plus className="size-4" />
        开启新研究
      </Button>

      <p className="mt-6 px-1 text-xs text-faint">近期研究</p>
      <ul className="mt-2 space-y-1">
        {recentResearch.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className={cn(
                "w-full cursor-pointer rounded-xl px-3 py-2.5 text-left transition-colors",
                item.active ? "bg-card shadow-card" : "hover:bg-card/60",
              )}
            >
              <p
                className={cn(
                  "text-[13px] font-medium",
                  item.active ? "text-ink" : "text-ink-2",
                )}
              >
                {item.title}
              </p>
              <p className="mt-0.5 text-[11px] text-faint">
                {item.time} · {item.refs} 篇引用
              </p>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
