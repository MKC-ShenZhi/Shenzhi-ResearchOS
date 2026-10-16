import { AppShell } from "@/components/common/layout/app-shell";
import { SearchHero } from "@/features/search/components/search-hero";
import { FeedList } from "@/features/search/components/feed-list";

/** 主发现页 `/` —— 对应「深知-主发现页.svg」 */
export function HomePage() {
  return (
    <AppShell>
      <div className="mx-auto max-w-[1080px] space-y-5 overflow-visible px-4 py-4 lg:px-5 lg:py-5">
        <SearchHero />
        <section aria-labelledby="paper-discovery-heading">
          <div className="mb-4 px-1">
            <h2 id="paper-discovery-heading" className="text-lg font-semibold text-ink">
              论文发现
            </h2>
            <p className="mt-1 text-sm text-muted">
              浏览近期收录的 2026 年论文
            </p>
          </div>
          <FeedList />
        </section>
      </div>
    </AppShell>
  );
}
