import { cn } from "@/lib/utils";

/** 紧凑圆环配额指示（类似 CC compact ring） */
export function QuotaRing({
  used,
  limit,
  size = 28,
  className,
}: {
  used: number;
  limit: number;
  size?: number;
  className?: string;
}) {
  const pct =
    limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const r = (size - 4) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;

  return (
    <div
      className={cn("relative shrink-0", className)}
      style={{ width: size, height: size }}
      title={`今日已用 ${used}/${limit}`}
      aria-label={`今日配额 ${used}/${limit}`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-line)"
          strokeWidth={2.5}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--color-primary)"
          strokeWidth={2.5}
          strokeDasharray={c}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-[stroke-dashoffset] duration-300"
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[9px] font-semibold tabular-nums text-muted">
        {limit - used}
      </span>
    </div>
  );
}
