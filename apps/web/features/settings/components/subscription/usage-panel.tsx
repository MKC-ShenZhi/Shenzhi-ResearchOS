"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, BarChart3, RefreshCw } from "lucide-react";
import { fetchEntitlementUsage } from "@/clients/backend/entitlements";
import type { SettingsLocale } from "@/clients/settings";
import { Button } from "@/components/ui/button";

export function UsagePanel({ locale, userId, compact = false }: { locale: SettingsLocale; userId?: string; compact?: boolean }) {
  const zh = locale === "zh-CN";
  const query = useQuery({ queryKey: ["entitlement-usage", userId], queryFn: () => fetchEntitlementUsage(userId!), enabled: !!userId, retry: false });
  const windows = query.data?.windows.filter((window) => window.metric === "tokens" && window.window_ref.window_type === "natural") ?? [];
  return <section className="rounded-2xl border border-line bg-card p-5 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="flex items-center gap-2 font-semibold text-ink"><BarChart3 className="size-4 text-primary" aria-hidden="true" />{zh ? "用量概览" : "Usage overview"}</h2>
        <p className="mt-1.5 text-xs leading-5 text-muted">{zh ? "掌握研究节奏，让每一份额度用有所值。" : "Keep track of the resources behind your research."}</p></div>
      {compact ? <Link href="/settings?tab=usage" className="flex items-center gap-1 text-xs text-primary hover:underline">{zh ? "查看用量" : "View usage"}<ArrowUpRight className="size-3.5" aria-hidden="true" /></Link> : <Button variant="ghost" size="sm" disabled={!userId || query.isFetching} onClick={() => void query.refetch()}><RefreshCw className={query.isFetching ? "animate-spin" : ""} aria-hidden="true" />{zh ? "刷新" : "Refresh"}</Button>}
    </div>
    {!userId ? <p className="mt-6 text-sm text-muted">{zh ? "登录后查看你的实际用量。" : "Sign in to view your usage."}</p> : query.isPending ? <p role="status" className="mt-6 animate-pulse text-sm text-muted">{zh ? "正在读取额度…" : "Loading usage…"}</p> : query.isError ? <div className="mt-5 rounded-xl bg-background p-4"><p role="status" className="text-sm text-muted">{zh ? "暂时无法读取用量，请确认订阅权益有效后重试。" : "Usage is unavailable. Check your subscription and try again."}</p><Button className="mt-2" variant="ghost" size="sm" onClick={() => void query.refetch()}>{zh ? "重新获取" : "Try again"}</Button></div> : windows.length === 0 ? <p className="mt-6 text-sm text-muted">{zh ? "当前权益没有可展示的每日 Token 额度。" : "No daily token allowance is available for this entitlement."}</p> : windows.map((window) => {
      const used = window.limit_units > 0 ? Math.min(100, window.used_units / window.limit_units * 100) : 0;
      const held = window.limit_units > 0 ? Math.min(100 - used, window.held_units / window.limit_units * 100) : 0;
      return <div key={window.window_ref.window_id + window.rule_id} className="mt-6">
        <div className="flex flex-wrap items-end justify-between gap-2"><div><p className="text-xs text-muted">{zh ? "每日 Token 额度" : "Daily token allowance"}</p><p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight text-ink">{window.remaining_units.toLocaleString(locale)}<span className="ml-2 text-xs font-normal text-muted">{zh ? "剩余" : "remaining"}</span></p></div><span className="text-xs tabular-nums text-muted">{zh ? "总额度" : "Total"} {window.limit_units.toLocaleString(locale)}</span></div>
        <div role="meter" aria-label={zh ? "已使用及预留额度" : "Used and reserved allowance"} aria-valuemin={0} aria-valuemax={Math.max(1, window.limit_units)} aria-valuenow={Math.min(window.limit_units, window.used_units + window.held_units)} className="mt-4 flex h-2 overflow-hidden rounded-full bg-chip"><div className="h-full bg-primary" style={{ width: `${used}%` }} /><div className="h-full bg-primary/30" style={{ width: `${held}%` }} /></div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted"><span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-primary" />{zh ? "已使用" : "Used"} {window.used_units.toLocaleString(locale)}</span><span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-primary/30" />{zh ? "任务预留" : "Reserved"} {window.held_units.toLocaleString(locale)}</span></div>
        {window.window_ref.end && <p className="mt-4 text-xs text-muted">{zh ? "下次重置：" : "Resets: "}{new Date(window.window_ref.end).toLocaleString(locale, { timeZone: window.window_ref.timezone ?? undefined })}{window.window_ref.timezone ? ` · ${window.window_ref.timezone}` : ""}</p>}
      </div>;
    })}
    {!compact && <div className="mt-6 border-t border-line pt-5 text-xs leading-6 text-muted"><p>{zh ? "任务预留是执行中任务暂时占用的额度，结算后会按实际用量更新。续费不会重置当天已使用或已预留的额度。" : "Running tasks reserve allowance. Settlement updates it to actual usage. Renewing does not reset today's usage or reservations."}</p><p>{zh ? "此处展示当前额度窗口，历史消费趋势尚未提供。" : "This view shows current allowance windows. Historical usage trends are not yet available."}</p></div>}
  </section>;
}
