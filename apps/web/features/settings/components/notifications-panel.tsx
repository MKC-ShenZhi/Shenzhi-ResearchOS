import { Bell, Newspaper, Sparkles, Users } from "lucide-react";
import type { NotificationKey, NotificationPreferences, SettingsLocale } from "@/clients/backend/settings";
import { cn } from "@/lib/utils";
import { PreferenceStatus } from "./preference-status";

const items = [
  { key: "activity", icon: Newspaper, zh: "动态通知", en: "Activity", zhSub: "关注或收藏对象的动态偏好", enSub: "Updates about followed or saved items" },
  { key: "subscription", icon: Sparkles, zh: "订阅消息", en: "Subscription", zhSub: "订阅与用量相关消息偏好", enSub: "Subscription and usage messages" },
  { key: "interaction", icon: Users, zh: "互动消息", en: "Interactions", zhSub: "与你互动的消息偏好", enSub: "Messages about interactions" },
  { key: "system", icon: Bell, zh: "系统通知", en: "System", zhSub: "系统服务消息偏好", enSub: "System service messages" },
] as const satisfies readonly { key: NotificationKey; icon: typeof Bell; zh: string; en: string; zhSub: string; enSub: string }[];

export function NotificationsPanel({ locale, values, loading, notice, error, onChange }: {
  locale: SettingsLocale;
  values: NotificationPreferences;
  loading: boolean;
  notice: string | null;
  error: string | null;
  onChange: (values: NotificationPreferences) => void;
}) {
  return <div className="space-y-4">
    <div className="rounded-xl border border-line bg-primary-soft/30 px-4 py-3 text-xs leading-5 text-muted">{locale === "en" ? "These choices are saved preferences only. Notification delivery is not available yet." : "当前仅保存接收意愿；通知投递渠道尚未启用，不代表已经开启推送。"}</div>
    {items.map((item) => <div key={item.key} className="flex items-center gap-3 rounded-2xl bg-card px-5 py-4 shadow-card">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-chip"><item.icon className="size-4 text-ink-2" aria-hidden="true" /></span>
      <div className="min-w-0 flex-1"><h2 className="text-sm font-semibold text-ink">{locale === "en" ? item.en : item.zh}</h2><p className="mt-0.5 text-xs text-muted">{locale === "en" ? item.enSub : item.zhSub}</p></div>
      <button type="button" role="switch" aria-label={locale === "en" ? item.en : item.zh} aria-checked={values[item.key]} disabled={loading} onClick={() => onChange({ ...values, [item.key]: !values[item.key] })} className={cn("relative h-6 w-11 rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-60", values[item.key] ? "bg-primary" : "bg-line")}><span className={cn("absolute left-1 top-1 size-4 rounded-full bg-white shadow-sm transition-transform", values[item.key] && "translate-x-5")} /></button>
    </div>)}
    <PreferenceStatus locale={locale} loading={loading} notice={notice} error={error} />
  </div>;
}
