import { fundingStatuses } from "@/features/knowledge/data-funding";
import { cn } from "@/lib/utils";

const TAG_COLORS = [
  "bg-success-soft text-[#059669] dark:text-success",
  "bg-chip text-muted",
];

const ALL_CATEGORIES = "全部";

export interface FundingCategoryCount {
  name: string;
  count: number;
}

/** 基金库左栏 —— 资助类别筛选 + 项目状态标签 */
export function FundingPanel({
  categories,
  activeCategory,
  onCategoryChange,
  activeStatus,
  onStatusChange,
}: {
  categories: FundingCategoryCount[];
  /** null = 全部 */
  activeCategory: string | null;
  onCategoryChange: (category: string | null) => void;
  activeStatus: string | null;
  onStatusChange: (status: string | null) => void;
}) {
  const total = categories.reduce((sum, c) => sum + c.count, 0);

  return (
    <aside className="w-60 shrink-0 self-stretch border-r border-line bg-card p-5">
      <h2 className="text-[15px] font-bold text-ink">项目基金库</h2>

      <p className="mt-5 px-1 text-xs text-faint">资助类别</p>
      <ul className="mt-1.5 space-y-0.5">
        {[{ name: ALL_CATEGORIES, count: total }, ...categories].map((category) => {
          const active =
            category.name === ALL_CATEGORIES
              ? activeCategory === null
              : activeCategory === category.name;
          return (
            <li key={category.name}>
              <button
                type="button"
                aria-pressed={active}
                onClick={() =>
                  onCategoryChange(
                    category.name === ALL_CATEGORIES ? null : category.name,
                  )
                }
                className={cn(
                  "flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-2 text-sm transition-colors",
                  active
                    ? "bg-primary-soft font-medium text-primary"
                    : "text-ink-2 hover:bg-chip",
                )}
              >
                <span
                  className={cn(
                    "size-3.5 rounded-[4px]",
                    active ? "bg-primary" : "bg-ink-2/70",
                  )}
                />
                <span className="flex-1 text-left">{category.name}</span>
                <span
                  className={cn(
                    "text-xs",
                    active
                      ? "rounded-full bg-primary px-1.5 py-0.5 leading-none text-white"
                      : "text-faint",
                  )}
                >
                  {category.count}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <p className="mt-5 px-1 text-xs text-faint">项目状态</p>
      <div className="mt-2 flex flex-wrap gap-2 px-1">
        {fundingStatuses.map((status, i) => (
          <button
            type="button"
            key={status}
            aria-pressed={activeStatus === status}
            onClick={() => onStatusChange(activeStatus === status ? null : status)}
            className={cn(
              "rounded-md border px-2 py-1 text-xs transition-all",
              TAG_COLORS[i % TAG_COLORS.length],
              activeStatus === status ? "border-primary ring-2 ring-primary/15" : "border-transparent",
            )}
          >
            {status}
          </button>
        ))}
      </div>
    </aside>
  );
}
