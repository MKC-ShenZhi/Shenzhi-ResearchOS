"use client";

import { useState } from "react";
import { AppShell } from "@/components/common/layout/app-shell";
import { SearchHero } from "@/features/search/components/search-hero";
import { FeedTabs } from "@/features/search/components/feed-tabs";
import { FeedList } from "@/features/search/components/feed-list";
import type { DiscoveryFeedTab } from "@/features/search/services/mvp-random-discovery-feed";

/** 主发现页 `/` —— 对应「深知-主发现页.svg」 */
export function HomePage() {
  const [activeTab, setActiveTab] = useState<DiscoveryFeedTab>("recommend");

  return (
    <AppShell>
      <div className="mx-auto max-w-[1080px] space-y-5 overflow-visible px-4 py-4 lg:px-5 lg:py-5">
        <SearchHero />
        <FeedTabs activeTab={activeTab} onTabChange={setActiveTab} />
        <FeedList tab={activeTab} />
      </div>
    </AppShell>
  );
}
