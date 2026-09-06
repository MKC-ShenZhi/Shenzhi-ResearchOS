"use client";

import { create } from "zustand";

export interface SidebarChatHistoryItem {
  id: string;
  title: string;
  updatedAt: number;
  source: "db" | "local";
  favorite?: boolean;
}

export type AskSidebarAction =
  | { type: "reset"; requestId: number }
  | { type: "load"; item: SidebarChatHistoryItem; targetPath?: string; requestId: number }
  | null;

interface AskSidebarBridgeState {
  historyItems: SidebarChatHistoryItem[];
  activeHistoryId: string | null;
  activeSessionId: string | null;
  pendingAction: AskSidebarAction;
  historyRefreshNonce: number;
  nextActionId: number;
  setHistoryItems: (historyItems: SidebarChatHistoryItem[]) => void;
  setActiveHistoryId: (activeHistoryId: string | null) => void;
  setActiveSessionId: (activeSessionId: string | null) => void;
  removeHistoryItem: (id: string, source?: SidebarChatHistoryItem["source"]) => void;
  requestReset: () => void;
  requestLoad: (item: SidebarChatHistoryItem, targetPath?: string) => void;
  clearPending: () => void;
  bumpHistoryRefresh: () => void;
  resetForIdentityChange: () => void;
}

export const useAskSidebarBridge = create<AskSidebarBridgeState>((set) => ({
  historyItems: [],
  activeHistoryId: null,
  activeSessionId: null,
  pendingAction: null,
  historyRefreshNonce: 0,
  nextActionId: 0,
  setHistoryItems: (historyItems) => set({ historyItems }),
  setActiveHistoryId: (activeHistoryId) => set({ activeHistoryId }),
  setActiveSessionId: (activeSessionId) => set({ activeSessionId }),
  removeHistoryItem: (id, source) =>
    set((state) => {
      const matches = (item: SidebarChatHistoryItem) => item.id === id && (!source || item.source === source);
      const activeItem = state.historyItems.find((item) => item.id === state.activeHistoryId);
      return {
        historyItems: state.historyItems.filter((item) => !matches(item)),
        activeHistoryId: activeItem && matches(activeItem) ? null : state.activeHistoryId,
        activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
      };
    }),
  requestReset: () =>
    set((state) => {
      const requestId = state.nextActionId + 1;
      return { nextActionId: requestId, pendingAction: { type: "reset", requestId } };
    }),
  requestLoad: (item, targetPath) =>
    set((state) => {
      const requestId = state.nextActionId + 1;
      return { nextActionId: requestId, pendingAction: { type: "load", item, targetPath, requestId } };
    }),
  clearPending: () => set({ pendingAction: null }),
  bumpHistoryRefresh: () =>
    set((s) => ({ historyRefreshNonce: s.historyRefreshNonce + 1 })),
  resetForIdentityChange: () => set({
    historyItems: [],
    activeHistoryId: null,
    activeSessionId: null,
    pendingAction: null,
  }),
}));
