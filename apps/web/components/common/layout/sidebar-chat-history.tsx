"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronDown,
  History,
  MessageSquarePlus,
  Pencil,
  Search,
  Star,
  Trash2,
} from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { cn } from "@/lib/utils";
import { deleteChatSession, listChatSessions, updateChatSession } from "@/clients/backend/chat";
import { deleteLocalAskSession, listLocalAskSessions } from "@/features/chat/services/local-history";
import { isMissingSessionError, messageForApiError } from "@/features/chat/services/errors";
import { mergeHistorySources } from "@/features/chat/services/history-snapshot";
import { chatIdentityScope } from "@/features/chat/services/identity-scope";
import { askSessionUrl } from "@/features/chat/services/session-url";
import {
  useAskSidebarBridge,
  type SidebarChatHistoryItem,
} from "@/stores/ask-sidebar-bridge";
import { useSidebarStore } from "@/stores/sidebar";

const HISTORY_KEY = "/agents/history";

function relativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} 天前`;
  return new Date(ts).toLocaleDateString("zh-CN");
}

/** 主侧栏：可折叠「对话历史」下拉（Chat 唯一历史入口） */
export function SidebarChatHistory({ collapsed }: { collapsed?: boolean }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, isPending: authPending } = useAuth();
  const identityScope = authPending ? null : chatIdentityScope(session?.user.id);
  const bridgeItems = useAskSidebarBridge((s) => s.historyItems);
  const activeId = useAskSidebarBridge((s) => s.activeHistoryId);
  const setActiveSessionId = useAskSidebarBridge((s) => s.setActiveSessionId);
  const refreshNonce = useAskSidebarBridge((s) => s.historyRefreshNonce);
  const requestReset = useAskSidebarBridge((s) => s.requestReset);
  const requestLoad = useAskSidebarBridge((s) => s.requestLoad);
  const clearPending = useAskSidebarBridge((s) => s.clearPending);
  const bumpHistoryRefresh = useAskSidebarBridge((s) => s.bumpHistoryRefresh);
  const resetForIdentityChange = useAskSidebarBridge((s) => s.resetForIdentityChange);
  const storedOpen = useSidebarStore((s) => s.expanded[HISTORY_KEY]);
  const setExpanded = useSidebarStore((s) => s.setExpanded);
  const open = storedOpen ?? false;

  const [pending, setPending] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const editRef = useRef<HTMLInputElement>(null);
  const refreshSequence = useRef(0);
  const previousIdentityScope = useRef<string | null>(null);

  const setHistoryItems = useAskSidebarBridge((s) => s.setHistoryItems);
  const removeHistoryItem = useAskSidebarBridge((s) => s.removeHistoryItem);

  const refresh = useCallback(() => {
    if (!identityScope) return;
    const requestId = ++refreshSequence.current;
    setHistoryError(null);
    void listChatSessions()
      .then((data) => {
        if (requestId !== refreshSequence.current) return;
        // The backend response is authoritative. In particular, [] must
        // replace an old bridge snapshot after a Memory repository restart.
        setHistoryItems(mergeHistorySources(data.sessions, listLocalAskSessions()));
      })
      .catch((error) => {
        if (requestId !== refreshSequence.current) return;
        setHistoryItems(mergeHistorySources([], listLocalAskSessions()));
        setHistoryError(messageForApiError(error));
      });
  }, [identityScope, setHistoryItems]);

  useEffect(() => {
    if (!identityScope) {
      refreshSequence.current += 1;
      return;
    }
    if (previousIdentityScope.current !== identityScope) {
      previousIdentityScope.current = identityScope;
      resetForIdentityChange();
    }
    queueMicrotask(refresh);
    return () => {
      // Ignore a response started for an older route or auth identity.
      refreshSequence.current += 1;
    };
  }, [identityScope, pathname, refresh, refreshNonce, resetForIdentityChange]);

  useEffect(() => {
    if (editingId) editRef.current?.focus();
  }, [editingId]);

  // The bridge is the single rendered snapshot. Never fall back to a stale
  // local component copy when the authoritative backend list is empty.
  const items = bridgeItems;
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => item.title.toLowerCase().includes(q));
  }, [items, query]);

  const onAgentRoute = pathname === "/agents" || pathname.startsWith("/agents/ask");

  const openSession = (item: SidebarChatHistoryItem) => {
    if (item.source === "db") {
      clearPending();
      router.push(askSessionUrl(item.id));
      return;
    }
    setActiveSessionId(null);
    requestLoad(item, "/agents");
    const actualPathname = typeof window === "undefined" ? pathname : window.location.pathname;
    if (actualPathname !== "/agents") router.push("/agents");
  };

  const newChat = () => {
    setActiveSessionId(null);
    requestReset();
    router.push(askSessionUrl(null));
  };

  const mutate = async (fn: () => Promise<void>) => {
    if (pending) return;
    setPending(true);
    setHistoryError(null);
    try {
      await fn();
      refresh();
      bumpHistoryRefresh();
    } catch (error) {
      setHistoryError(messageForApiError(error));
    } finally {
      setPending(false);
    }
  };

  const togglePanel = () => setExpanded(HISTORY_KEY, !open);

  const commitEdit = async (id: string) => {
    const title = draftTitle.trim();
    setEditingId(null);
    if (!title) return;
    try {
      await updateChatSession(id, { title });
      refresh();
      bumpHistoryRefresh();
    } catch (error) {
      setHistoryError(messageForApiError(error));
    }
  };

  if (collapsed) {
    return (
      <Link
        href="/agents"
        title="对话历史"
        className="flex h-10 shrink-0 items-center justify-center rounded-xl text-ink-2 transition-colors hover:bg-card"
      >
        <History className="size-[18px]" strokeWidth={1.8} />
      </Link>
    );
  }

  return (
    <div className="shrink-0">
      <button
        type="button"
        onClick={togglePanel}
        aria-expanded={open}
        className={cn(
          "flex h-10 w-full cursor-pointer items-center gap-2 rounded-xl px-3 text-left transition-colors",
          open ? "bg-card text-ink shadow-sm" : "text-ink-2 hover:bg-card",
        )}
      >
        <History className="size-[18px] shrink-0" strokeWidth={1.8} />
        <span className="flex-1 text-[15px] font-medium">对话历史</span>
        {items.length > 0 && (
          <span className="rounded-full bg-chip px-1.5 py-0.5 text-[10px] text-muted">
            {items.length}
          </span>
        )}
        <ChevronDown
          className={cn("size-4 shrink-0 text-faint transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="mt-0.5 flex flex-col gap-1 border-t border-line/40 pt-1 pl-3">
          <button
            type="button"
            onClick={newChat}
            className="flex h-9 cursor-pointer items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-white transition-colors hover:bg-primary-deep"
          >
            <MessageSquarePlus className="size-4 shrink-0" strokeWidth={1.8} />
            新对话
          </button>

          <div className="flex items-center gap-2 rounded-lg border border-line bg-card px-2.5">
            <Search className="size-3.5 shrink-0 text-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索历史…"
              className="h-8 w-full bg-transparent text-[13px] text-ink outline-none placeholder:text-faint"
            />
          </div>

          {historyError && (
            <p role="alert" className="px-2 py-1 text-[12px] text-rose-500">
              {historyError}
            </p>
          )}

          <div className="scrollbar-subtle max-h-48 space-y-0.5 overflow-y-auto py-0.5">
            {filtered.length === 0 ? (
              <p className="px-2 py-3 text-center text-[12px] text-faint">
                {items.length === 0 ? "还没有历史对话" : "无匹配结果"}
              </p>
            ) : (
              filtered.map((item) => (
                <div
                  key={`${item.source}-${item.id}`}
                  className={cn(
                    "group relative flex min-h-9 items-center rounded-lg px-1 transition-colors",
                    onAgentRoute && activeId === item.id ? "bg-primary-soft" : "hover:bg-chip",
                  )}
                >
                  {editingId === item.id && item.source === "db" ? (
                    <input
                      ref={editRef}
                      value={draftTitle}
                      onChange={(e) => setDraftTitle(e.target.value)}
                      onBlur={() => void commitEdit(item.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void commitEdit(item.id);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      className="h-8 w-full rounded-md border border-primary/40 bg-card px-2 text-[13px] text-ink outline-none"
                    />
                  ) : (
                    <>
                      <button
                        type="button"
                        title={item.title}
                        disabled={pending}
                        aria-current={onAgentRoute && activeId === item.id ? "page" : undefined}
                        onClick={() => openSession(item)}
                        className="min-w-0 flex-1 cursor-pointer pr-16 pl-2 text-left"
                      >
                        <span className="flex items-center gap-1 truncate text-[13px] text-ink-2">
                          {item.favorite && (
                            <Star className="size-3 shrink-0 fill-current text-primary" />
                          )}
                          {item.title}
                        </span>
                        <span className="block text-[10.5px] text-faint">
                          {relativeTime(item.updatedAt)}
                          {item.source === "local" ? " · 本地" : ""}
                        </span>
                      </button>
                      <div className="absolute right-1 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                        {item.source === "db" && (
                          <>
                            <button
                              type="button"
                              title={item.favorite ? "取消收藏" : "收藏"}
                              disabled={pending}
                              onClick={() =>
                                void mutate(async () => {
                                  await updateChatSession(item.id, {
                                    favorite: !item.favorite,
                                  });
                                })
                              }
                              className="rounded-md bg-card p-1 text-faint shadow-sm ring-1 ring-line/60 hover:text-primary"
                            >
                              <Star
                                className={cn(
                                  "size-3.5",
                                  item.favorite && "fill-current text-primary",
                                )}
                              />
                            </button>
                            <button
                              type="button"
                              title="重命名"
                              disabled={pending}
                              onClick={() => {
                                setEditingId(item.id);
                                setDraftTitle(item.title);
                              }}
                              className="rounded-md bg-card p-1 text-faint shadow-sm ring-1 ring-line/60 hover:text-primary"
                            >
                              <Pencil className="size-3.5" />
                            </button>
                          </>
                        )}
                        <button
                          type="button"
                          title="删除"
                          disabled={pending}
                          onClick={() => {
                            if (!window.confirm(`删除会话「${item.title}」？`)) return;
                            if (item.source === "db") {
                              void mutate(async () => {
                                try {
                                  await deleteChatSession(item.id);
                                } catch (error) {
                                  // DELETE is idempotent from the UI's point
                                  // of view: a missing backend session already
                                  // satisfies the desired final state.
                                  if (!isMissingSessionError(error)) throw error;
                                }
                                removeHistoryItem(item.id, "db");
                                if (activeId === item.id) {
                                  requestReset();
                                  router.push(askSessionUrl(null));
                                }
                              });
                            } else {
                              deleteLocalAskSession(item.id);
                              removeHistoryItem(item.id, "local");
                              refresh();
                              bumpHistoryRefresh();
                              if (activeId === item.id) {
                                requestReset();
                                router.push(askSessionUrl(null));
                              }
                            }
                          }}
                          className="rounded-md bg-card p-1 text-faint shadow-sm ring-1 ring-line/60 hover:text-rose-500"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
