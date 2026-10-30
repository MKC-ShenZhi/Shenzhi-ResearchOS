import { AppShell } from "@/components/common/layout/app-shell";
import { ConferenceBrowser } from "@/features/submit/components/conference-browser";

/** 投稿 · 会议 `/submit` —— 会议截稿倒计时,点击侧边栏「投稿」默认打开 */
export function SubmitPage() {
  return (
    <AppShell>
      <div className="mx-auto max-w-[1180px] px-4 py-4 sm:px-8 sm:py-6">
        <ConferenceBrowser />
      </div>
    </AppShell>
  );
}
