import { Monitor, Moon, Sun } from "lucide-react";
import type { ReactNode } from "react";
import type { SettingsLocale } from "@/clients/settings";
import type { ThemeMode } from "@/stores/theme";
import { supportsThemeMode, VISIBLE_THEME_PRESETS, type ThemePreset } from "@/lib/theme-presets";
import { cn } from "@/lib/utils";
import { settingsMessages } from "../i18n";
import { PreferenceStatus } from "./preference-status";
import { ProfileEditor } from "./profile/profile-editor";

const themes: { mode: ThemeMode; zh: string; en: string; icon: typeof Sun }[] = [
  { mode: "light", zh: "日间", en: "Light", icon: Sun },
  { mode: "dark", zh: "夜间", en: "Dark", icon: Moon },
  { mode: "system", zh: "跟随系统", en: "System", icon: Monitor },
];

function Section({ id, title, children }: { id?: string; title: string; children: ReactNode }) {
  return <section id={id} className="scroll-mt-6"><h2 className="text-[15px] font-semibold text-ink">{title}</h2>{children}</section>;
}

export function ProfilePanel({
  account,
  user,
  locale,
  themeMode,
  themePreset,
  loading,
  notice,
  error,
  onLocaleChange,
  onThemeChange,
  onThemePresetChange,
}: {
  account: ReactNode;
  user: { id: string; name?: string | null; email?: string | null; image?: string | null } | null;
  locale: SettingsLocale;
  themeMode: ThemeMode;
  themePreset: ThemePreset;
  loading: boolean;
  notice: string | null;
  error: string | null;
  onLocaleChange: (locale: SettingsLocale) => void;
  onThemeChange: (theme: ThemeMode) => void;
  onThemePresetChange: (theme: ThemePreset) => void;
}) {
  const t = settingsMessages[locale];
  return (
    <div className="space-y-8">
      <Section title={t.profileIntro}>
        <ProfileEditor key={user?.id ?? "anonymous"} user={user} locale={locale} />
      </Section>
      <Section title={t.account}>{account}</Section>
      <Section title={t.language}>
        <div className="mt-3 flex gap-2 rounded-2xl bg-card p-6 shadow-card">
          {(["zh-CN", "en"] as const).map((value) => <button key={value} type="button" aria-pressed={locale === value} onClick={() => onLocaleChange(value)} className={cn("h-10 rounded-xl px-5 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary", locale === value ? "bg-primary-soft font-medium text-primary" : "bg-chip text-ink-2")}>{value === "zh-CN" ? "中文" : "English"}</button>)}
        </div>
      </Section>
      <Section id="appearance" title={t.appearance}>
        <div className="mt-3 rounded-2xl bg-card p-6 shadow-card">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {VISIBLE_THEME_PRESETS.map((option) => <button key={option.id} type="button" aria-pressed={themePreset === option.id} onClick={() => onThemePresetChange(option.id)} className={cn("min-h-14 rounded-xl px-4 py-2 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary", themePreset === option.id ? "bg-primary-soft text-primary" : "bg-chip text-ink-2")}><span className="block text-sm font-medium">{option.label}</span><span className="mt-0.5 block text-xs text-muted">{option.description}</span></button>)}
          </div>
          {supportsThemeMode(themePreset) && <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
            {themes.map((option) => <button key={option.mode} type="button" aria-pressed={themeMode === option.mode} onClick={() => onThemeChange(option.mode)} className={cn("flex h-10 items-center gap-2 rounded-xl px-5 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary", themeMode === option.mode ? "bg-primary-soft font-medium text-primary" : "bg-chip text-ink-2")}><option.icon className="size-4" aria-hidden="true" />{locale === "en" ? option.en : option.zh}</button>)}
          </div>}
        </div>
      </Section>
      <PreferenceStatus locale={locale} loading={loading} notice={notice} error={error} />
    </div>
  );
}
