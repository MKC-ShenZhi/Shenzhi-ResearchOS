import { settingsMessages } from "../i18n";
import type { SettingsLocale } from "@/clients/settings";

export function PreferenceStatus({
  locale,
  loading,
  notice,
  error,
}: {
  locale: SettingsLocale;
  loading: boolean;
  notice: string | null;
  error: string | null;
}) {
  const t = settingsMessages[locale];
  if (loading) return <p className="text-xs text-muted" role="status">{locale === "en" ? "Loading preferences…" : "正在加载偏好…"}</p>;
  if (error) return <p className="text-xs text-danger" role="alert">{t.saveFailed}</p>;
  if (notice === "saved") return <p className="text-xs text-muted" role="status">{t.saved}</p>;
  if (notice === "local") return <p className="text-xs text-muted" role="status">{t.localOnly}</p>;
  return null;
}
