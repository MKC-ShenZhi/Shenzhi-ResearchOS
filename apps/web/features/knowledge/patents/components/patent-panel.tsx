import { patentStatuses } from "@/features/knowledge/data-patents";
import { cn } from "@/lib/utils";

const TAG_COLORS = [
  "bg-primary-soft text-primary",
  "bg-[#FEF3C7] text-[#B45309] dark:bg-[#3a2f10] dark:text-[#f0c94e]",
  "bg-success-soft text-[#059669] dark:text-success",
  "bg-danger-soft text-danger",
];

const ALL_FIELDS = "全部";

export interface PatentFieldCount {
  name: string;
  count: number;
}

/** 专利库左栏 —— 技术领域筛选 + 法律状态标签(布局对齐 LibraryPanel) */
export function PatentPanel({
  fields,
  activeField,
  onFieldChange,
  activeStatus,
  onStatusChange,
}: {
  fields: PatentFieldCount[];
  /** null = 全部 */
  activeField: string | null;
  onFieldChange: (field: string | null) => void;
  activeStatus: string | null;
  onStatusChange: (status: string | null) => void;
}) {
  const total = fields.reduce((sum, f) => sum + f.count, 0);

  return (
    <aside className="w-60 shrink-0 self-stretch border-r border-line bg-card p-5">
      <h2 className="text-[15px] font-bold text-ink">专利库</h2>

      <p className="mt-5 px-1 text-xs text-faint">技术领域</p>
      <ul className="mt-1.5 space-y-0.5">
        {[{ name: ALL_FIELDS, count: total }, ...fields].map((field) => {
          const active =
            field.name === ALL_FIELDS ? activeField === null : activeField === field.name;
          return (
            <li key={field.name}>
              <button
                type="button"
                aria-pressed={active}
                onClick={() =>
                  onFieldChange(field.name === ALL_FIELDS ? null : field.name)
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
                <span className="flex-1 text-left">{field.name}</span>
                <span
                  className={cn(
                    "text-xs",
                    active
                      ? "rounded-full bg-primary px-1.5 py-0.5 leading-none text-white"
                      : "text-faint",
                  )}
                >
                  {field.count}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <p className="mt-5 px-1 text-xs text-faint">法律状态</p>
      <div className="mt-2 flex flex-wrap gap-2 px-1">
        {patentStatuses.map((status, i) => (
          <button
            type="button"
            key={status}
            aria-pressed={activeStatus === (status.startsWith("PCT") ? "PCT" : status)}
            onClick={() => {
              const value = status.startsWith("PCT") ? "PCT" : status;
              onStatusChange(activeStatus === value ? null : value);
            }}
            className={cn(
              "rounded-md border px-2 py-1 text-xs transition-all",
              TAG_COLORS[i % TAG_COLORS.length],
              activeStatus === (status.startsWith("PCT") ? "PCT" : status) ? "border-primary ring-2 ring-primary/15" : "border-transparent",
            )}
          >
            {status}
          </button>
        ))}
      </div>
    </aside>
  );
}
