import type { SettingsLocale } from "@/clients/settings";

export function PlaceholderPanel({ locale, name }: { locale: SettingsLocale; name: string }) {
  return <div className="rounded-2xl bg-card p-8 text-sm text-muted shadow-card">{locale === "en" ? `${name} is planned for a later phase.` : `${name}将在后续阶段接入，当前不提供演示操作。`}</div>;
}
