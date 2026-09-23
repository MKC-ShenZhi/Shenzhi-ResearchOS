"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";

import {
  deleteAgentSession, listAgentSessions, renameAgentSession,
  type AgentSessionSummary,
} from "@/clients/backend/agent";
import { useAuth } from "@/components/auth/auth-provider";
import { migrateLegacyAgentSessions } from "@/features/agent-chat/session-store";
import {
  AGENT_SESSIONS_CHANGED, notifyAgentSessionsChanged,
} from "@/features/agent-chat/session-events";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 10;

/** Direct Agent history list. Its sentinel observes AppSidebar nav; no nested scroll area. */
export function SidebarChatHistory({ collapsed }: { collapsed?: boolean }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentSessionId = searchParams.get("session");
  const { session, isPending } = useAuth();
  const [items, setItems] = useState<AgentSessionSummary[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuId, setMenuId] = useState<string | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef(0);
  const loadingRef = useRef(false);
  const cursorRef = useRef<string | null>(null);
  const hasMoreRef = useRef(true);

  const load = useCallback(async (reset: boolean) => {
    if (loadingRef.current || (!reset && !hasMoreRef.current)) return;
    loadingRef.current = true;
    setLoading(true);
    setError(null);
    const request = ++requestRef.current;
    try {
      let page = await listAgentSessions(PAGE_SIZE, reset ? null : cursorRef.current);
      if (request !== requestRef.current) return;
      setItems((current) => reset
        ? page.sessions
        : [...current, ...page.sessions.filter((item) => !current.some((old) => old.id === item.id))]);
      if (reset && !page.ephemeral) {
        const migrated = await migrateLegacyAgentSessions();
        if (migrated > 0) {
          page = await listAgentSessions(PAGE_SIZE);
          if (request !== requestRef.current) return;
          setItems(page.sessions);
        }
      }
      cursorRef.current = page.next_cursor;
      hasMoreRef.current = page.has_more;
      setHasMore(page.has_more);
    } catch (cause) {
      if (request === requestRef.current) {
        setError(cause instanceof Error ? cause.message : "聊天历史加载失败");
      }
    } finally {
      if (request === requestRef.current) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (isPending) return;
    let active = true;
    requestRef.current += 1;
    loadingRef.current = false;
    queueMicrotask(() => {
      if (!active) return;
      setItems([]);
      setHasMore(true);
      cursorRef.current = null;
      hasMoreRef.current = true;
      void load(true);
    });
    return () => { active = false; };
  }, [isPending, session?.user.id, load]);

  useEffect(() => {
    const refresh = () => {
      loadingRef.current = false;
      setHasMore(true);
      cursorRef.current = null;
      hasMoreRef.current = true;
      void load(true);
    };
    window.addEventListener(AGENT_SESSIONS_CHANGED, refresh);
    return () => window.removeEventListener(AGENT_SESSIONS_CHANGED, refresh);
  }, [load]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    const root = sentinel?.closest("nav") ?? null;
    if (!sentinel || !root || !hasMore) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void load(false);
    }, { root, rootMargin: "0px 0px 120px 0px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, load]);

  if (collapsed) return null;

  const rename = async (item: AgentSessionSummary) => {
    const title = window.prompt("重命名会话", item.title)?.trim();
    setMenuId(null);
    if (!title || title === item.title) return;
    try {
      const updated = await renameAgentSession(item.id, title);
      setItems((current) => current.map((entry) => entry.id === item.id ? updated : entry));
      notifyAgentSessionsChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "重命名失败");
    }
  };

  const remove = async (item: AgentSessionSummary) => {
    setMenuId(null);
    if (!window.confirm(`删除会话「${item.title}」？`)) return;
    try {
      await deleteAgentSession(item.id);
      setItems((current) => current.filter((entry) => entry.id !== item.id));
      notifyAgentSessionsChanged();
      if (currentSessionId === item.id) router.push("/");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除失败");
    }
  };

  return (
    <section className="mt-3 shrink-0" aria-label="聊天历史">
      <p className="px-3 pb-1.5 pt-2 text-[11px] font-medium tracking-wide text-faint">聊天</p>
      <div className="space-y-0.5">
        {items.map((item) => (
          <div key={item.id} className={cn(
            "group relative flex min-h-9 items-center rounded-lg transition-colors",
            currentSessionId === item.id ? "bg-primary-soft" : "hover:bg-chip",
          )}>
            <button type="button" title={item.title}
              onClick={() => router.push(`/agents?session=${encodeURIComponent(item.id)}`)}
              className="min-w-0 flex-1 cursor-pointer truncate px-3 py-2 pr-9 text-left text-[13px] text-ink-2"
              aria-current={currentSessionId === item.id ? "page" : undefined}>
              {item.title}
            </button>
            <button type="button" aria-label={`${item.title} 更多操作`}
              onClick={() => setMenuId((current) => current === item.id ? null : item.id)}
              className="absolute right-1 rounded-md p-1 text-faint opacity-0 transition-opacity hover:bg-card hover:text-ink group-hover:opacity-100 focus:opacity-100">
              <MoreHorizontal className="size-4" />
            </button>
            {menuId === item.id && (
              <div className="absolute right-1 top-8 z-40 w-28 rounded-xl border border-line bg-card p-1 shadow-pop">
                <button type="button" onClick={() => void rename(item)}
                  className="flex h-8 w-full items-center gap-2 rounded-lg px-2 text-xs text-ink-2 hover:bg-chip">
                  <Pencil className="size-3.5" />重命名
                </button>
                <button type="button" onClick={() => void remove(item)}
                  className="flex h-8 w-full items-center gap-2 rounded-lg px-2 text-xs text-red-600 hover:bg-chip">
                  <Trash2 className="size-3.5" />删除
                </button>
              </div>
            )}
          </div>
        ))}
        {items.length === 0 && !loading && !error && (
          <p className="px-3 py-2 text-xs text-faint">还没有聊天</p>
        )}
        {error && <p role="alert" className="px-3 py-1 text-xs text-red-600">{error}</p>}
        {loading && <p className="px-3 py-1 text-xs text-faint">加载中…</p>}
        <div ref={sentinelRef} className="h-px" aria-hidden />
      </div>
    </section>
  );
}
