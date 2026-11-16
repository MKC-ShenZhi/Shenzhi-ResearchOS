"use client";

import { Heart, HeartPulse } from "lucide-react";
import type { HealthState } from "@/features/auto-research/research-run";
import { cn } from "@/lib/utils";

/** 健康度底栏 —— Deli 值守机制的可视化仪表 */
export function HealthBar({ health }: { health: HealthState }) {
  const tokenPct = Math.min(100, Math.round((health.tokensUsed / health.tokensBudget) * 100));
  const watchdogItems = [
    { key: "L0", state: health.watchdog.l0 },
    { key: "L1", state: health.watchdog.l1 },
    { key: "L2", state: health.watchdog.l2 },
  ];

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
      <span className="text-muted">
        迭代 <b className="text-ink">{health.iteration}</b>
        <span className="ml-1 text-faint">本轮新发现 {health.newFindings}</span>
      </span>

      <span className={cn("text-muted", health.staleCount > 0 && "text-[#d97706]")}>
        停滞计数 <b>{health.staleCount}</b>
        <span className="ml-1 text-faint">≥2 结构性转向 · ≥4 升级人工</span>
      </span>

      <span className="flex items-center gap-1.5 text-muted">
        看门狗
        {watchdogItems.map((w) => (
          <span key={w.key} className="flex items-center gap-0.5">
            {w.state === "ok" ? (
              <HeartPulse className="size-3.5 text-success" />
            ) : (
              <Heart className="size-3.5 text-[#d97706]" />
            )}
            <span className="text-[10px] text-faint">{w.key}</span>
          </span>
        ))}
      </span>

      <span className="flex min-w-0 items-center gap-1.5 text-muted">
        方向谱
        <span className="flex min-w-0 flex-wrap gap-1">
          {health.directions.length === 0 && <span className="text-faint">—</span>}
          {health.directions.map((d) => (
            <span key={d} className="rounded-md bg-chip px-1.5 py-0.5 text-[10px] text-muted">
              {d}
            </span>
          ))}
          {health.nextDirection && (
            <span className="rounded-md border border-dashed border-primary px-1.5 py-0.5 text-[10px] text-primary">
              下一方向:{health.nextDirection}
            </span>
          )}
        </span>
      </span>

      <span className="ml-auto flex items-center gap-2 text-muted">
        <span>
          预算 <b className="text-ink">{Math.round(health.tokensUsed / 1000)}k</b>/
          {Math.round(health.tokensBudget / 1000)}k token
        </span>
        <span className="h-1.5 w-24 overflow-hidden rounded-full bg-chip">
          <span
            className={cn("block h-full rounded-full", tokenPct > 90 ? "bg-danger" : "bg-primary")}
            style={{ width: `${tokenPct}%` }}
          />
        </span>
        <span className="text-faint">
          回合 {health.roundsUsed}/{health.roundsBudget}
        </span>
      </span>
    </div>
  );
}
