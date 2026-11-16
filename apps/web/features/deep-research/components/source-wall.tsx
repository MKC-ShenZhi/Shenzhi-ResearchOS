import { drReport } from "@/features/deep-research/data";

/** 来源墙 —— 已收集来源 chips,hover 显示完整标题与出处 */
export function SourceWall({ count }: { count: number }) {
  const total = drReport.references.length;
  const shown = Math.min(count, total);
  const visible = drReport.references.slice(0, shown);
  return (
    <section className="rounded-2xl bg-card p-4 shadow-card">
      <div className="flex items-center">
        <h2 className="text-sm font-semibold text-ink">来源墙</h2>
        <span className="ml-auto text-[11px] text-faint">
          {shown} / {total}
        </span>
      </div>
      {visible.length === 0 ? (
        <p className="mt-3 text-xs text-faint">检索到的来源将出现在这里…</p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {visible.map((s) => (
            <span
              key={s.id}
              title={`${s.title} · ${s.venue}`}
              className="cursor-default rounded-full bg-chip px-2.5 py-1 text-[11px] text-ink-2"
            >
              {s.short}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
