import { scholarDirections } from "@/features/knowledge/data-scholars";
import { cn } from "@/lib/utils";

/** 学者关系左栏 —— 布局与专利库筛选栏保持一致 */
export function DirectionFilter({
  activeDirection,
  onDirectionChange,
}: {
  activeDirection: string | null;
  onDirectionChange: (direction: string | null) => void;
}) {
  return (
    <aside className="w-60 shrink-0 self-stretch border-r border-line bg-card p-5">
      <h2 className="text-[15px] font-bold text-ink">学者关系</h2>
      <p className="mt-5 px-1 text-xs text-faint">研究方向</p>
      <ul className="mt-1.5 space-y-0.5">
        {[{ name: "全部", count: scholarsTotal }, ...scholarDirections].map((dir) => {
          const active = dir.name === "全部" ? activeDirection === null : activeDirection === dir.name;
          return <li key={dir.name}>
            <button
              type="button"
              aria-pressed={active}
              onClick={() => onDirectionChange(dir.name === "全部" ? null : dir.name)}
              className={cn(
                "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-2 text-sm transition-colors",
                active ? "bg-primary-soft font-medium text-primary" : "text-ink-2 hover:bg-chip",
              )}
            >
              <span className={cn("size-3.5 rounded-[4px]", active ? "bg-primary" : "bg-ink-2/70")} />
              <span className="flex-1 text-left">{dir.name}</span>
              <span className={cn("text-xs", active ? "rounded-full bg-primary px-1.5 py-0.5 leading-none text-white" : "text-faint")}>{dir.count}</span>
            </button>
          </li>;
        })}
      </ul>
    </aside>
  );
}

const scholarsTotal = scholarDirections.reduce((sum, direction) => {
  const value = Number.parseFloat(direction.count);
  return sum + (direction.count.toLowerCase().includes("k") ? value * 1000 : value);
}, 0);
