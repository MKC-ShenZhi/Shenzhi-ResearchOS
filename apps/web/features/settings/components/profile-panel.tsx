import { Monitor, Moon, Sun, User } from "lucide-react";
import type { ReactNode } from "react";
import type { SettingsLocale } from "@/clients/settings";
import type { ThemeMode } from "@/stores/theme";
import { cn } from "@/lib/utils";
import { settingsMessages } from "../i18n";
import { PreferenceStatus } from "./preference-status";

const themes: { mode: ThemeMode; zh: string; en: string; icon: typeof Sun }[] = [
  { mode: "light", zh: "日间", en: "Light", icon: Sun },
  { mode: "dark", zh: "夜间", en: "Dark", icon: Moon },
  { mode: "system", zh: "跟随系统", en: "System", icon: Monitor },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section><h2 className="text-[15px] font-semibold text-ink">{title}</h2>{children}</section>;
}

export function ProfilePanel({
  account,
  user,
  locale,
  themeMode,
  loading,
  notice,
  error,
  onLocaleChange,
  onThemeChange,
}: {
  account: ReactNode;
  user: { name?: string | null; email?: string | null; image?: string | null } | null;
  locale: SettingsLocale;
  themeMode: ThemeMode;
  loading: boolean;
  notice: string | null;
  error: string | null;
  onLocaleChange: (locale: SettingsLocale) => void;
  onThemeChange: (theme: ThemeMode) => void;
}) {
  const t = settingsMessages[locale];
  return (
    <div className="space-y-8">
      <Section title={t.profileIntro}>
        <div className="mt-3 flex flex-col gap-5 rounded-2xl bg-card p-6 shadow-card sm:flex-row sm:items-center">
          {user?.image ? (
            // eslint-disable-next-line @next/next/no-img-element -- Better Auth may provide an external avatar URL.
            <img src={user.image} alt="" className="size-24 rounded-2xl object-cover" />
          ) : (
            <span className="flex size-24 shrink-0 items-center justify-center rounded-2xl bg-primary-soft">
              <User className="size-10 text-primary" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0">
            {user ? <><p className="font-semibold text-ink">{user.name || user.email}</p><p className="mt-1 text-sm text-muted">{user.email}</p></> : <p className="text-sm text-muted">{t.signInProfile}</p>}
            <p className="mt-3 text-xs leading-5 text-muted">{user ? t.profileEmpty : t.avatarNote}</p>
          </div>
        </div>
      </Section>
      <Section title={t.account}>{account}</Section>
      <Section title={t.language}>
        <div className="mt-3 flex gap-2 rounded-2xl bg-card p-6 shadow-card">
          {(["zh-CN", "en"] as const).map((value) => <button key={value} type="button" aria-pressed={locale === value} onClick={() => onLocaleChange(value)} className={cn("h-10 rounded-xl px-5 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary", locale === value ? "bg-primary-soft font-medium text-primary" : "bg-chip text-ink-2")}>{value === "zh-CN" ? "中文" : "English"}</button>)}
        </div>
      </Section>
      <Section title={t.appearance}>
        <div className="mt-3 flex flex-wrap gap-2 rounded-2xl bg-card p-6 shadow-card">
          {themes.map((option) => <button key={option.mode} type="button" aria-pressed={themeMode === option.mode} onClick={() => onThemeChange(option.mode)} className={cn("flex h-10 items-center gap-2 rounded-xl px-5 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary", themeMode === option.mode ? "bg-primary-soft font-medium text-primary" : "bg-chip text-ink-2")}><option.icon className="size-4" aria-hidden="true" />{locale === "en" ? option.en : option.zh}</button>)}
        </div>
      </Section>
      <PreferenceStatus locale={locale} loading={loading} notice={notice} error={error} />
    </div>
  );
}
