import { AppShell } from "@/components/common/layout/app-shell";
import { ConferenceBrowser } from "@/features/submit/components/conference-browser";

/** 会议DDL `/submit` —— 会议截稿倒计时,侧边栏一级入口「会议DDL」 */
export function SubmitPage() {
  return (
    <AppShell>
      <div className="mx-auto max-w-[1180px] px-4 py-4 sm:px-8 sm:py-6">
        <ConferenceBrowser />
      </div>
    </AppShell>
  );
}
