"use client";

import { Suspense, useCallback, useState, type ReactNode } from "react";
import { AppSidebar } from "./app-sidebar";
import { MobileHeader } from "./mobile-header";
import { MobileNavDrawer } from "./mobile-nav-drawer";
import { useSidebarStore } from "@/stores/sidebar";
import { cn } from "@/lib/utils";
import { AnonymousClaimCoordinator } from "@/features/chat/components/anonymous-claim-coordinator";
import { useRecordSearchRestoration } from "@/hooks/use-search-restoration";

function SearchNavigationRecorder() {
  useRecordSearchRestoration();
  return null;
}

/**
 * 应用外壳 —— 固定左侧栏 + 内容区
 * (论文阅读器等沉浸式页面不使用此布局)
 * 侧边栏折叠时内容区位置自适应左移,内部布局不变
 */
export function AppShell({ children }: { children: ReactNode }) {
  const collapsed = useSidebarStore((s) => s.collapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeMobile = useCallback(() => setMobileOpen(false), []);

  return (
    <div className="min-h-screen bg-background">
      <Suspense fallback={null}>
        <SearchNavigationRecorder />
      </Suspense>
      <MobileNavDrawer open={mobileOpen} onClose={closeMobile}>
        <AppSidebar mobileOpen={mobileOpen} onMobileClose={closeMobile} />
      </MobileNavDrawer>
      <AnonymousClaimCoordinator />
      <div inert={mobileOpen}>
      <MobileHeader open={mobileOpen} onOpen={() => setMobileOpen(true)} />
      <main
        className={cn(
          "min-w-0 transition-[padding] duration-200",
          collapsed ? "lg:pl-16" : "lg:pl-60",
        )}
      >
        {children}
      </main>
      </div>
    </div>
  );
}
