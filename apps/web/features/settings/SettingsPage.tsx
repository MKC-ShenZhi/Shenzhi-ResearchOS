import { Suspense } from "react";
import { AppShell } from "@/components/common/layout/app-shell";
import { SettingsTabs } from "./components/settings-tabs";

/** 设置页 `/settings` —— Tab 受控于 ?tab= 参数(如 /settings?tab=api) */
export function SettingsPage() {
  return (
    <AppShell>
      <div className="mx-auto max-w-[960px] px-8 py-10">
        <Suspense>
          <SettingsTabs />
        </Suspense>
      </div>
    </AppShell>
  );
}
