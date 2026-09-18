"use client";

import { create } from "zustand";
import { apiJson, ApiError } from "@/clients/backend/http";

export interface CollectionFolder {
  id: number;
  name: string;
  is_default: boolean;
  paper_count: number;
}

interface CollectionState {
  folders: CollectionFolder[];
  paperFolders: Record<string, number[]>;
  loading: boolean;
  loadFolders: () => Promise<void>;
  loadPaperFolders: (paperId: string) => Promise<number[]>;
  createFolder: (name: string) => Promise<CollectionFolder>;
  renameFolder: (folderId: number, name: string) => Promise<CollectionFolder>;
  deleteFolder: (folderId: number) => Promise<void>;
  updatePaperFolders: (paperId: string, folderIds: number[]) => Promise<void>;
}

/**
 * 未登录时的默认文件夹占位：仅用于前端展示与提示，不来自后端。
 * 使用负数 id，保证未登录时不会命中任何真实文件夹。
 */
const UNAUTHENTICATED_FOLDERS: CollectionFolder[] = [
  { id: -1, name: "想读", is_default: true, paper_count: 0 },
  { id: -2, name: "在读", is_default: true, paper_count: 0 },
  { id: -3, name: "已读", is_default: true, paper_count: 0 },
];

export const useCollections = create<CollectionState>((set, get) => ({
  folders: [],
  paperFolders: {},
  loading: false,
  loadFolders: async () => {
    set({ loading: true });
    try {
      const response = await apiJson<{ folders: CollectionFolder[] }>("/collections/folders");
      set({ folders: response.folders });
    } catch (error) {
      // 未登录：固定展示三个默认文件夹占位，使展示与上次登录状态无关；
      // 点击文件夹后由内容区给出“请先登录”提示。
      if (error instanceof ApiError && error.status === 401) {
        set({ folders: UNAUTHENTICATED_FOLDERS });
        return;
      }
      throw error;
    } finally {
      set({ loading: false });
    }
  },
  loadPaperFolders: async (paperId) => {
    const response = await apiJson<{ folder_ids: number[] }>(
      `/papers/${encodeURIComponent(paperId)}/collections`,
    );
    set((state) => ({
      paperFolders: { ...state.paperFolders, [paperId]: response.folder_ids },
    }));
    return response.folder_ids;
  },
  createFolder: async (name) => {
    const folder = await apiJson<CollectionFolder>("/collections/folders", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    set((state) => ({ folders: [...state.folders, folder] }));
    return folder;
  },
  renameFolder: async (folderId, name) => {
    const folder = await apiJson<CollectionFolder>(`/collections/folders/${folderId}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    });
    set((state) => ({ folders: state.folders.map((item) => item.id === folderId ? folder : item) }));
    return folder;
  },
  deleteFolder: async (folderId) => {
    await apiJson<unknown>(`/collections/folders/${folderId}`, { method: "DELETE" });
    set((state) => ({
      folders: state.folders.filter((item) => item.id !== folderId),
      paperFolders: Object.fromEntries(
        Object.entries(state.paperFolders).map(([paperId, ids]) => [paperId, ids.filter((id) => id !== folderId)]),
      ),
    }));
  },
  updatePaperFolders: async (paperId, folderIds) => {
    await apiJson<unknown>(`/papers/${encodeURIComponent(paperId)}/collections`, {
      method: "PUT",
      body: JSON.stringify({ folder_ids: folderIds }),
    });
    set((state) => ({
      paperFolders: { ...state.paperFolders, [paperId]: folderIds },
      folders: state.folders.map((folder) => ({
        ...folder,
        paper_count: folder.paper_count + (folderIds.includes(folder.id) ? 1 : 0),
      })),
    }));
    await get().loadFolders();
  },
}));
