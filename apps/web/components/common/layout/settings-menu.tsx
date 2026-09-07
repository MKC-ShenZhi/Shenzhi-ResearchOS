"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import {
  BarChart3,
  Bell,
  Bot,
  KeyRound,
  Monitor,
  Moon,
  Settings,
  Sparkles,
  Sun,
  UserRound,
} from "lucide-react";
import { useThemeStore, type ThemeMode } from "@/stores/theme";
import { cn } from "@/lib/utils";
import { McpIcon } from "@/features/settings/components/settings-tabs";
import { useSidebarStore } from "@/stores/sidebar";

/** 设置选项,自上而下与设置页 Tab 顺序一致,点击跳转对应 Tab */
const MENU_ITEMS = [
  { label: "个人", icon: UserRound, href: "/settings?tab=profile" },
  { label: "订阅", icon: Sparkles, href: "/settings?tab=subscription" },
  { label: "用量统计", icon: BarChart3, href: "/settings?tab=usage" },
  { label: "Agent设置", icon: Bot, href: "/settings?tab=agent" },
  { label: "MCP", icon: null, href: "/settings?tab=mcp" },
  { label: "API", icon: KeyRound, href: "/settings?tab=api" },
  { label: "通知", icon: Bell, href: "/settings?tab=notifications" },
];

const THEME_OPTIONS: { mode: ThemeMode; label: string; icon: typeof Sun }[] = [
  { mode: "light", label: "日间", icon: Sun },
  { mode: "dark", label: "夜间", icon: Moon },
  { mode: "system", label: "跟随系统", icon: Monitor },
];

/** 设置条目 + 悬停展开的选项栏,栏底为日/夜/跟随系统切换 */
export function SettingsMenu({ collapsed }: { collapsed: boolean }) {
  const mode = useThemeStore((s) => s.mode);
  const setMode = useThemeStore((s) => s.setMode);
  // persist 的主题在客户端水合后才可读,避免水合不一致
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );
  const setCollapsed = useSidebarStore((s) => s.setCollapsed);
  const pathname = usePathname();
  // 与侧边栏一致:已处于设置栏目时再点击才折叠;从其他栏目进入仅跳转
  const collapseIfSameSection = () => {
    if (pathname.startsWith("/settings")) setCollapsed(true);
  };

  return (
    <div className="group relative mt-4 shrink-0">
      {collapsed ? (
        <Link
          href="/settings"
          scroll={false}
          title="设置"
          aria-label="设置"
          onClick={() => {
            // 图标栏:再次点击当前栏目图标则展开侧边栏
            if (pathname.startsWith("/settings")) setCollapsed(false);
          }}
          className="flex h-10 w-full items-center justify-center rounded-xl text-ink-2 transition-colors hover:bg-card"
        >
          <Settings className="size-[18px] shrink-0" strokeWidth={1.8} />
        </Link>
      ) : (
        <Link
          href="/settings"
          scroll={false}
          title="设置"
          onClick={collapseIfSameSection}
          className="flex h-10 w-full items-center gap-3 rounded-xl px-3 text-ink-2 transition-colors hover:bg-card"
        >
          <Settings className="size-[18px] shrink-0" strokeWidth={1.8} />
          <span className="flex-1 text-left text-[15px] font-medium">设置</span>
        </Link>
      )}

      {/* 悬停选项栏:出现在条目右侧,底部对齐向上展开 */}
      <div className="pointer-events-none absolute bottom-0 left-full z-50 pl-2 opacity-0 transition-opacity duration-100 group-hover:pointer-events-auto group-hover:opacity-100">
        <div className="w-52 rounded-2xl border border-line bg-card p-2 shadow-pop">
          {MENU_ITEMS.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              scroll={false}
              onClick={collapseIfSameSection}
              className="flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-sm text-ink-2 transition-colors hover:bg-chip"
            >
              {item.icon ? (
                <item.icon className="size-4 shrink-0 text-muted" strokeWidth={1.8} />
              ) : (
                <McpIcon className="size-4 shrink-0 text-muted" />
              )}
              {item.label}
            </Link>
          ))}

          {/* 主题:日间 / 夜间 / 跟随系统 */}
          <div className="mt-1.5 flex items-center gap-1 border-t border-line px-1 pb-1 pt-2.5">
            {THEME_OPTIONS.map((opt) => (
              <button
                key={opt.mode}
                type="button"
                title={opt.label}
                aria-label={opt.label}
                aria-pressed={mounted && mode === opt.mode}
                onClick={() => setMode(opt.mode)}
                className={cn(
                  "flex h-8 flex-1 cursor-pointer items-center justify-center rounded-lg transition-colors",
                  mounted && mode === opt.mode
                    ? "bg-primary-soft text-primary"
                    : "text-muted hover:bg-chip hover:text-ink-2",
                )}
              >
                <opt.icon className="size-4" strokeWidth={1.8} />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
