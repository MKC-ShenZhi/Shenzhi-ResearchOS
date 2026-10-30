"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import {
  Bookmark,
  ChevronDown,
  Compass,
  Layers,
  Library,
  LogOut,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Send,
  Sparkles,
  User,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { SITE } from "@/lib/constants";
import { projects } from "@/features/projects/data";
import { FollowedDeadlineBadge } from "@/features/submit/components/followed-deadline-badge";
import { useAuth } from "@/components/auth/auth-provider";
import { UserAvatar } from "@/components/common/user-avatar";
import { userAvatarSource } from "@/clients/profile";
import { useUserProfile } from "@/hooks/use-user-profile";
import { useSidebarStore } from "@/stores/sidebar";
import {
  FeatureNavigationLink,
  useFeatureAvailability,
} from "@/components/common/feature-availability-provider";
import { isUnavailableFeatureHref } from "@/lib/feature-availability";
import { SEARCH_RESTORATION_ROUTES } from "@/lib/navigation/search-restoration";
import { Logo } from "./logo";
import { SettingsMenu } from "./settings-menu";
import { SidebarChatHistory } from "./sidebar-chat-history";
import { SearchNavigationLink } from "./search-navigation-link";

interface NavItem {
  href: string;
  label: string;
  icon: typeof Compass;
  badge?: string;
  disabled?: boolean;
  /** 前缀匹配(用于详情页保持高亮) */
  matchPrefix?: string;
}

const RESEARCH_NAV: NavItem[] = [
  { href: "/", label: "发现", icon: Compass, badge: "新" },
];

const MY_PAPERS_NAV: NavItem = {
  href: "/knowledge/papers",
  label: "我的文献",
  icon: Bookmark,
  matchPrefix: "/knowledge/papers",
};

/** 「投稿」的子栏目:会议即原投稿页面,点击投稿默认打开 */
const SUBMIT_SUB_NAV = [
  { href: "/submit", label: "会议" },
  { href: "/submit/journals", label: "期刊" },
];

/** 「知识库」的子栏目 */
const KNOWLEDGE_SUB_NAV = [
  { href: "/knowledge/search", label: "论文库" },
  { href: "/knowledge/scholars", label: "学者库" },
  { href: "/knowledge/topics", label: "主题库" },
  { href: "/knowledge/funding", label: "项目基金库" },
  { href: "/knowledge/graph", label: "关系图谱" },
];

/** 「AI 助手」的子栏目;AI 助手本身有独立对话页(/agents),不与子栏目共享 */
const AGENT_SUB_NAV = [
  { href: "/agents/deep-research", label: "Deep Research" },
  { href: "/agents/auto-research", label: "Auto Research" },
];

/** 「科研项目」的子栏目即用户创建的项目列表(副标题 = 项目名称) */
const PROJECT_SUB_NAV = projects.map((p) => ({
  href: `/projects/${p.id}`,
  label: p.name,
}));

const subscribeHydration = () => () => {};

function NavLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const pathname = usePathname();
  const setCollapsed = useSidebarStore((s) => s.setCollapsed);
  const active = item.matchPrefix
    ? pathname.startsWith(item.matchPrefix)
    : pathname === item.href;
  const Icon = item.icon;
  const inner = (
    <>
      <Icon className="size-[18px] shrink-0" strokeWidth={1.8} />
      {!collapsed && (
        <span className="flex-1 text-[15px] font-medium">{item.label}</span>
      )}
      {!collapsed && item.badge && (
        <span className="rounded-full bg-brand-gold px-1.5 py-0.5 text-[10px] font-semibold leading-none text-ink">
          {item.badge}
        </span>
      )}
    </>
  );

  if (item.disabled) {
    return (
      <span
        title={collapsed ? `${item.label}(即将上线)` : "即将上线"}
        className={cn(
          "flex h-10 shrink-0 cursor-not-allowed items-center rounded-xl text-muted/50",
          collapsed ? "justify-center" : "gap-3 px-3",
        )}
      >
        {inner}
      </span>
    );
  }

  // 折叠(图标栏)态:点击图标先跳转;再次点击当前栏目图标则展开侧边栏
  if (collapsed) {
    return (
      <Link
        href={item.href}
        scroll={false}
        title={item.label}
        aria-label={item.label}
        aria-current={active ? "page" : undefined}
        onClick={() => {
          if (active) setCollapsed(false);
        }}
        className={cn(
          "flex h-10 shrink-0 items-center justify-center rounded-xl transition-colors",
          active
            ? "bg-primary text-white shadow-sm"
            : "text-ink-2 hover:bg-card",
        )}
      >
        <Icon className="size-[18px] shrink-0" strokeWidth={1.8} />
      </Link>
    );
  }

  return (
    <Link
      href={item.href}
      scroll={false}
      title={collapsed ? item.label : undefined}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex h-10 shrink-0 items-center rounded-xl transition-colors",
        "gap-3 px-3",
        active
          ? "bg-primary text-white shadow-sm"
          : "text-ink-2 hover:bg-card",
      )}
    >
      {inner}
    </Link>
  );
}

/**
 * 可展开导航项 —— 展开状态存于全局 store,切换到其他条目后仍保持展开。
 * 折叠/展开规则:
 * - 侧边栏展开时,点击主标题:副标题折叠则展开并跳转(有主标题页跳主标题页,
 *   没有则跳第一个副标题页);副标题已展开时仅按跳转逻辑跳转;
 * - 侧边栏折叠(图标栏)时,点击图标先跳转;再次点击当前栏目的图标,
 *   则展开侧边栏并展开副标题。
 * 右侧箭头只收起/展开副标题,不跳转。
 */
function ExpandableNav({
  href,
  label,
  icon: Icon,
  subNav,
  collapsed,
  footer,
  badge,
}: {
  href: string;
  label: string;
  icon: typeof Compass;
  subNav: { href: string; label: string }[];
  collapsed: boolean;
  /** 子栏目列表末尾的附加内容(如「新建项目」) */
  footer?: React.ReactNode;
  /** 主标题旁的提醒(如关注会议临近截稿);折叠时显示为图标角标 */
  badge?: (compact: boolean) => React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const routeActive =
    pathname.startsWith(href) && !pathname.startsWith(MY_PAPERS_NAV.href);
  const stored = useSidebarStore((s) => s.expanded[href]);
  const setExpanded = useSidebarStore((s) => s.setExpanded);
  const setCollapsed = useSidebarStore((s) => s.setCollapsed);
  const { showComingSoon } = useFeatureAvailability();
  const availableSubNav = subNav.filter(
    (item) => !isUnavailableFeatureHref(item.href),
  );
  const open = stored ?? routeActive;
  /** 主页是否独立于副标题(如 AI 助手:/agents 不是任何副标题页) */
  const hasOwnPage = !availableSubNav.some((s) => s.href === href);
  /** 跳转目标:有主标题页跳主标题页,没有则跳第一个副标题页 */
  const dest = hasOwnPage ? href : availableSubNav[0].href;

  const navigate = (target: string) => {
    if (isUnavailableFeatureHref(target)) {
      showComingSoon();
      return false;
    }
    router.push(target, { scroll: false });
    return true;
  };

  const handleMainClick = () => {
    if (isUnavailableFeatureHref(dest)) {
      showComingSoon();
      return;
    }
    if (!open) {
      // 副标题折叠:展开副标题并跳转
      setExpanded(href, true);
      if (pathname !== dest) navigate(dest);
    } else if (routeActive) {
      // 当前栏目子页面点击主标题时返回栏目主页
      if (pathname !== dest) navigate(dest);
    } else if (pathname !== dest) {
      // 副标题展开但处于其他栏目:仅跳转
      navigate(dest);
    }
  };

  if (isUnavailableFeatureHref(href)) return null;

  if (collapsed) {
    return (
      <button
        type="button"
        title={label}
        onClick={() => {
          if (isUnavailableFeatureHref(dest)) {
            showComingSoon();
            return;
          }
          if (routeActive) {
            // Knowledge 图标从子页面返回总览;其他栏目保持原有展开行为
            setCollapsed(false);
            setExpanded(href, true);
            if (href === "/knowledge" && pathname !== href) {
              router.push(href, { scroll: false });
            }
          } else {
            // 先跳转,保持图标栏
            navigate(dest);
          }
        }}
        className={cn(
          "relative flex h-10 shrink-0 items-center justify-center rounded-xl transition-colors",
          routeActive
            ? "bg-primary text-white shadow-sm"
            : "text-ink-2 hover:bg-card",
        )}
      >
        <Icon className="size-[18px] shrink-0" strokeWidth={1.8} />
        {badge?.(true)}
      </button>
    );
  }

  return (
    <div className="shrink-0">
      <div
        className={cn(
          "flex h-10 items-center rounded-xl transition-colors",
          routeActive
            ? "bg-primary text-white shadow-sm"
            : "text-ink-2 hover:bg-card",
        )}
      >
        <button
          type="button"
          onClick={handleMainClick}
          className="flex h-full min-w-0 flex-1 items-center gap-3 pl-3 text-left"
        >
          <Icon className="size-[18px] shrink-0" strokeWidth={1.8} />
          <span className="flex-1 text-[15px] font-medium">{label}</span>
          {badge?.(false)}
        </button>
        <button
          type="button"
          aria-label={open ? `收起${label}子栏目` : `展开${label}子栏目`}
          title={open ? "收起" : "展开"}
          onClick={() => setExpanded(href, !open)}
          className="mr-2 rounded-md p-1.5 hover:bg-white/15"
        >
          <ChevronDown
            className={cn("size-4 transition-transform", !open && "-rotate-90")}
          />
        </button>
      </div>

      {open && (
        <div className="mt-0.5 flex flex-col gap-0.5 pl-6">
          {availableSubNav.map((sub) => {
            const active = pathname === sub.href || pathname.startsWith(`${sub.href}/`);
            const NavigationLink = Object.hasOwn(SEARCH_RESTORATION_ROUTES, sub.href)
              ? SearchNavigationLink
              : FeatureNavigationLink;
            return (
              <NavigationLink
                key={sub.href}
                href={sub.href}
                scroll={false}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-9 items-center rounded-lg px-3 text-sm transition-colors",
                  active
                    ? "bg-card font-semibold text-primary shadow-sm"
                    : "text-muted hover:bg-card hover:text-ink-2",
                )}
              >
                {sub.label}
              </NavigationLink>
            );
          })}
          {footer}
        </div>
      )}
    </div>
  );
}

/** 登录后「···」向上弹出的标签栏:登出 */
function LogoutPopup({
  onClose,
  onLoggedOut,
  signOut,
}: {
  onClose: () => void;
  onLoggedOut: () => void;
  signOut: ReturnType<typeof useAuth>["signOut"];
}) {
  const [loggingOut, setLoggingOut] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const onPointerDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const handleLogout = async () => {
    if (loggingOut) return;

    setError(null);
    setLoggingOut(true);
    try {
      const { error: signOutError } = await signOut();
      if (signOutError) {
        setError("退出失败，请稍后重试");
        return;
      }

      onLoggedOut();
    } catch {
      setError("退出失败，请稍后重试");
    } finally {
      setLoggingOut(false);
    }
  };

  return (
    <div
      ref={ref}
      className="absolute bottom-full right-0 z-50 mb-2 w-28 rounded-xl border border-line bg-card p-1.5 shadow-pop"
    >
      {error && (
        <p className="px-2.5 py-1 text-[11px] leading-4 text-danger" role="alert">
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={handleLogout}
        disabled={loggingOut}
        className="flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-sm text-ink-2 transition-colors hover:bg-chip"
      >
        <LogOut className="size-4 text-muted" strokeWidth={1.8} />
        {loggingOut ? "退出中..." : "登出"}
      </button>
    </div>
  );
}

/** 全局侧边栏 —— 240px 左侧栏(背景 primary soft)，可折叠为 64px 图标栏 */
export function AppSidebar({ mobileOpen = false, onMobileClose }: { mobileOpen?: boolean; onMobileClose?: () => void }) {
  const desktopCollapsed = useSidebarStore((s) => s.collapsed);
  const collapsed = mobileOpen ? false : desktopCollapsed;
  const toggleCollapsed = useSidebarStore((s) => s.toggleCollapsed);
  const setNavScrollTop = useSidebarStore((s) => s.setNavScrollTop);
  const { showComingSoon } = useFeatureAvailability();
  const pathname = usePathname();
  const navRef = React.useRef<HTMLElement>(null);
  const navScrollTopRef = React.useRef(useSidebarStore.getState().navScrollTop);
  const ignoreScrollUntilRef = React.useRef(0);
  const {
    session,
    isPending: sessionPending,
    openLogin,
    signOut,
  } = useAuth();
  const sessionReady = React.useSyncExternalStore(subscribeHydration, () => true, () => false);
  // Cookie session is visible on the client before hydration; keep the first
  // paint identical to SSR (logged-out chrome) to avoid a hard-refresh mismatch.
  const userName = !sessionReady || sessionPending
    ? null
    : session?.user.name?.trim() || session?.user.email || null;
  const { profile } = useUserProfile();
  const avatarSrc = userName
    ? userAvatarSource(profile, session?.user.image)
    : null;
  const [logoutOpen, setLogoutOpen] = React.useState(false);
  const handleLoggedOut = () => {
    setLogoutOpen(false);
    onMobileClose?.();
    openLogin({ notice: "已退出登录，你可以重新登录或注册" });
  };

  React.useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;

    const handleScroll = () => {
      if (performance.now() < ignoreScrollUntilRef.current) return;
      navScrollTopRef.current = nav.scrollTop;
      setNavScrollTop(nav.scrollTop);
    };
    nav.addEventListener("scroll", handleScroll, { passive: true });
    return () => nav.removeEventListener("scroll", handleScroll);
  }, [setNavScrollTop]);

  React.useLayoutEffect(() => {
    const restorePosition = () => {
      const nav = navRef.current;
      if (nav && nav.scrollTop !== navScrollTopRef.current) {
        nav.scrollTop = navScrollTopRef.current;
      }
    };

    ignoreScrollUntilRef.current = performance.now() + 400;
    restorePosition();
    const frames = [
      requestAnimationFrame(restorePosition),
      requestAnimationFrame(() => requestAnimationFrame(restorePosition)),
    ];
    const timeout = window.setTimeout(restorePosition, 200);
    return () => {
      frames.forEach((frame) => cancelAnimationFrame(frame));
      window.clearTimeout(timeout);
    };
  }, [pathname]);

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-30 flex-col bg-sidebar py-5 transition-[width] duration-200 lg:flex",
        mobileOpen ? "flex max-w-[calc(100vw-3rem)] pt-[max(1.25rem,env(safe-area-inset-top))] pb-[max(1.25rem,env(safe-area-inset-bottom))]" : "hidden",
        collapsed ? "w-16 px-2" : "w-60 px-4",
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2",
          collapsed ? "flex-col" : "justify-between",
        )}
      >
        <Logo compact={collapsed} />
        <button
          type="button"
          onClick={mobileOpen ? onMobileClose : toggleCollapsed}
          aria-label={mobileOpen ? "关闭导航" : collapsed ? "展开侧边栏" : "折叠侧边栏"}
          title={collapsed ? "展开侧边栏" : "折叠侧边栏"}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-chip hover:text-ink"
        >
          {mobileOpen ? <X className="size-4" /> : collapsed ? (
            <PanelLeftOpen className="size-4" strokeWidth={1.8} />
          ) : (
            <PanelLeftClose className="size-4" strokeWidth={1.8} />
          )}
        </button>
      </div>

      <nav
        ref={navRef}
        className="scrollbar-subtle mt-4 flex flex-1 flex-col gap-0.5 overflow-y-auto"
      >
        {!collapsed && (
          <p className="shrink-0 px-3 pb-1.5 pt-2 text-[11px] font-medium tracking-wide text-faint">
            研究
          </p>
        )}
        {RESEARCH_NAV.map((item) => (
          <NavLink key={item.label} item={item} collapsed={collapsed} />
        ))}
        <ExpandableNav
          href="/agents"
          label="AI 助手"
          icon={Sparkles}
          subNav={AGENT_SUB_NAV}
          collapsed={collapsed}
        />
        <ExpandableNav
          href="/knowledge"
          label="知识库"
          icon={Library}
          subNav={KNOWLEDGE_SUB_NAV}
          collapsed={collapsed}
        />
        <ExpandableNav
          href="/projects"
          label="科研项目"
          icon={Layers}
          subNav={PROJECT_SUB_NAV}
          collapsed={collapsed}
          footer={
            <button
              type="button"
              title="新建项目(演示)"
              onClick={showComingSoon}
              className="flex h-9 cursor-pointer items-center gap-2 rounded-lg px-3 text-sm text-faint transition-colors hover:bg-card hover:text-ink-2"
            >
              <Plus className="size-3.5" />
              新建项目
            </button>
          }
        />
        <ExpandableNav
          href="/submit"
          label="投稿"
          icon={Send}
          subNav={SUBMIT_SUB_NAV}
          collapsed={collapsed}
          badge={(compact) => <FollowedDeadlineBadge compact={compact} />}
        />
        <React.Suspense fallback={null}>
          <SidebarChatHistory collapsed={collapsed} />
        </React.Suspense>
      </nav>

      <div className="mt-4 flex shrink-0 flex-col gap-0.5 [&>div]:mt-0">
        {!isUnavailableFeatureHref(MY_PAPERS_NAV.href) && (
          <NavLink item={MY_PAPERS_NAV} collapsed={collapsed} />
        )}

        {/* 设置(悬停显示选项栏) */}
        <SettingsMenu collapsed={collapsed} mobile={mobileOpen} />
      </div>

      {/* 用户卡片:未登录点击弹出登录弹窗;登录后「···」向上弹出「登出」 */}
      {collapsed ? (
        <div className="relative mt-2 flex justify-center">
          <button
            type="button"
            aria-label={userName ? "账号菜单" : "登录"}
            className="flex size-9 cursor-pointer items-center justify-center rounded-full bg-primary-soft"
            onClick={() =>
              userName ? setLogoutOpen((v) => !v) : (onMobileClose?.(), openLogin())
            }
          >
            {userName ? (
              <UserAvatar
                src={avatarSrc}
                name={userName}
                alt={`${userName}的头像`}
                className="size-9 text-[13px]"
              />
            ) : (
              <User className="size-4.5 text-primary" />
            )}
          </button>
          {userName && logoutOpen && (
            <LogoutPopup
              onClose={() => setLogoutOpen(false)}
              onLoggedOut={handleLoggedOut}
              signOut={signOut}
            />
          )}
        </div>
      ) : userName ? (
        <div className="relative mt-2">
          <div className="flex items-center gap-2.5 rounded-xl bg-card p-2.5 shadow-card">
            <UserAvatar
              src={avatarSrc}
              name={userName}
              alt={`${userName}的头像`}
              className="size-9 text-[13px]"
            />
            <span className="flex min-w-0 flex-1 flex-col leading-tight">
              <span className="truncate text-[13px] font-semibold text-ink">
                {userName}
              </span>
            </span>
            <button
              type="button"
              aria-label="账号菜单"
              aria-expanded={logoutOpen}
              className="cursor-pointer rounded-md p-1 text-faint transition-colors hover:bg-chip hover:text-ink-2"
              onClick={() => setLogoutOpen((v) => !v)}
            >
              <MoreHorizontal className="size-4" />
            </button>
          </div>
          {logoutOpen && (
            <LogoutPopup
              onClose={() => setLogoutOpen(false)}
              onLoggedOut={handleLoggedOut}
              signOut={signOut}
            />
          )}
        </div>
      ) : (
        <button
          type="button"
          className="mt-2 flex cursor-pointer items-center gap-2.5 rounded-xl bg-card p-2.5 text-left shadow-card transition-colors hover:bg-chip"
          onClick={() => { onMobileClose?.(); openLogin(); }}
        >
          <span className="flex size-9 items-center justify-center rounded-full bg-primary-soft">
            <User className="size-4.5 text-primary" />
          </span>
          <span className="flex min-w-0 flex-1 flex-col leading-tight">
            <span className="truncate text-[13px] font-semibold text-ink">
              {SITE.user.name}
            </span>
          </span>
          <span aria-hidden className="rounded-md p-1 text-faint">
            <MoreHorizontal className="size-4" />
          </span>
        </button>
      )}

      {/* 联系我们 */}
      {!collapsed && (
        <p className="mt-3 text-center text-[10px] leading-none text-faint">
          联系我们
        </p>
      )}
    </aside>
  );
}
