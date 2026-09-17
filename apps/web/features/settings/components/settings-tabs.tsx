"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth/auth-provider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useUserSettings } from "../hooks/use-user-settings";
import { settingsMessages } from "../i18n";
import { AccountSection } from "./account-section";
import { NotificationsPanel } from "./notifications-panel";
import { PlaceholderPanel } from "./placeholder-panel";
import { ProfilePanel } from "./profile-panel";
import { isSettingsTab, SETTINGS_TABS } from "./tab-config";

export { McpIcon } from "./tab-config";

export function SettingsTabs() {
  const router = useRouter();
  const params = useSearchParams();
  const { session } = useAuth();
  const settings = useUserSettings();
  const requestedTab = params.get("tab");
  const active = isSettingsTab(requestedTab) ? requestedTab : "profile";
  const t = settingsMessages[settings.locale];

  return <>
    <h1 className="text-xl font-bold text-ink">{t.title}</h1>
    <Tabs value={active} onValueChange={(value) => router.replace(`/settings?tab=${value}`, { scroll: false })}>
      <div className="mt-6 overflow-x-auto pb-1">
        <TabsList aria-label={t.title} className="min-w-max gap-2 border-b border-line sm:gap-4">
          {SETTINGS_TABS.map((tab) => <TabsTrigger key={tab.value} id={`settings-tab-${tab.value}`} aria-controls={`settings-panel-${tab.value}`} value={tab.value} className="flex items-center gap-1.5 whitespace-nowrap focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"><tab.icon className="size-4" aria-hidden="true" />{t[tab.message]}</TabsTrigger>)}
        </TabsList>
      </div>
      <TabsContent id="settings-panel-profile" aria-labelledby="settings-tab-profile" value="profile" className="mt-6"><ProfilePanel account={<AccountSection />} user={session?.user ?? null} locale={settings.locale} themeMode={settings.themeMode} loading={settings.loading} notice={settings.notice} error={settings.error} onLocaleChange={(value) => void settings.setLocale(value)} onThemeChange={(value) => void settings.setTheme(value)} /></TabsContent>
      {(["subscription", "usage", "agent", "mcp", "api"] as const).map((value) => <TabsContent key={value} id={`settings-panel-${value}`} aria-labelledby={`settings-tab-${value}`} value={value} className="mt-6"><PlaceholderPanel locale={settings.locale} name={t[value]} /></TabsContent>)}
      <TabsContent id="settings-panel-notifications" aria-labelledby="settings-tab-notifications" value="notifications" className="mt-6"><NotificationsPanel locale={settings.locale} values={settings.notifications} loading={settings.loading} notice={settings.notice} error={settings.error} onChange={(value) => void settings.setNotifications(value)} /></TabsContent>
    </Tabs>
  </>;
}
