"use client";

import { Flame, Search, Settings2, Star, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { DiscoveryFeedTab } from "../services/mvp-random-discovery-feed";

const TABS: Array<{ key: DiscoveryFeedTab; label: string; icon: typeof Flame }> = [
  { key: "recommend", label: "推荐", icon: Flame },
  { key: "frontier", label: "前沿", icon: TrendingUp },
  { key: "follow", label: "关注", icon: Star },
  { key: "research", label: "研究", icon: Search },
];

/** Feed 流标签栏 —— 推荐 / 前沿 / 关注 / 研究 */
export function FeedTabs({
  activeTab,
  onTabChange,
}: {
  activeTab: DiscoveryFeedTab;
  onTabChange: (tab: DiscoveryFeedTab) => void;
}) {
  return (
    <div className="flex items-center gap-8 px-1">
      {TABS.map((tab) => {
        const Icon = tab.icon;
        return (
          <button
            key={tab.key}
            type="button"
            onClick={() => onTabChange(tab.key)}
            aria-pressed={activeTab === tab.key}
            className={cn(
              "flex cursor-pointer items-center gap-1.5 text-[15px] transition-colors",
              activeTab === tab.key
                ? "font-semibold text-primary"
                : "text-muted hover:text-ink-2",
            )}
          >
            {Icon && <Icon className="size-4" />}
            {tab.label}
          </button>
        );
      })}
      <Button
        variant="outline"
        size="sm"
        className="ml-auto rounded-lg"
        disabled
        title="个性化推荐暂未开放"
      >
        <Settings2 className="size-3.5" />
        个性化即将上线
      </Button>
    </div>
  );
}
