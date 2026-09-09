"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { MoreHorizontal, Search, Upload } from "lucide-react";
import { apiJson, ApiError } from "@/clients/backend/http";
import type { CollectionPaperListResponse } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { paperHref } from "@/lib/navigation/paper";
import { useCollections } from "@/stores/collections";

export function LibraryTable({ folderId }: { folderId: number | null }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CollectionPaperListResponse | null>(null);
  const [error, setError] = useState("");
  const [unauthenticated, setUnauthenticated] = useState(false);
  const [menu, setMenu] = useState<string | null>(null);
  const folders = useCollections((state) => state.folders);
  const loadFolders = useCollections((state) => state.loadFolders);

  function handleLoadError(reason: unknown) {
    if (reason instanceof ApiError && reason.status === 401) {
      setError("");
      setUnauthenticated(true);
      return;
    }
    setError(reason instanceof ApiError && reason.status === 403 ? "无权访问该文件夹" : "文件夹内容加载失败");
  }

  useEffect(() => {
    if (!folderId) return;
    let cancelled = false;
    void apiJson<CollectionPaperListResponse>(`/collections/folders/${folderId}/papers?page=1&page_size=20`)
      .then((response) => { if (!cancelled) { setError(""); setUnauthenticated(false); setData(response); setPage(1); } })
      .catch((reason) => { if (!cancelled) handleLoadError(reason); });
    return () => { cancelled = true; };
  }, [folderId]);

  async function loadPage(nextPage: number) {
    if (!folderId) return;
    setError("");
    try {
      setData(await apiJson<CollectionPaperListResponse>(`/collections/folders/${folderId}/papers?page=${nextPage}&page_size=20`));
      setPage(nextPage);
    } catch (reason) {
      handleLoadError(reason);
    }
  }

  async function removePaper(paperId: string) {
    if (!folderId) return;
    await apiJson<unknown>(`/collections/folders/${folderId}/papers/${encodeURIComponent(paperId)}`, { method: "DELETE" });
    await loadPage(page);
    await loadFolders();
    setMenu(null);
  }

  async function movePaper(paperId: string, targetFolderId: number) {
    if (!folderId) return;
    try {
      await apiJson<unknown>(`/collections/folders/${folderId}/papers/${encodeURIComponent(paperId)}/move`, {
        method: "POST",
        body: JSON.stringify({ target_folder_id: targetFolderId }),
      });
      await loadPage(page);
      await loadFolders();
      setMenu(null);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "移动失败，请重试");
    }
  }

  const items = data?.items.filter((item) => `${item.title} ${item.authors.join(" ")} ${item.venue ?? ""}`.toLowerCase().includes(query.trim().toLowerCase())) ?? [];
  const pageCount = Math.max(1, Math.ceil((data?.total ?? 0) / 20));

  return (
    <section className="min-w-0 flex-1 p-8">
      <div className="flex items-center justify-between">
        <div><h1 className="text-xl font-bold text-ink">论文库</h1><p className="mt-1 text-xs text-faint">当前文件夹 · {data?.total ?? 0} 篇论文</p></div>
        <Button className="rounded-xl"><Upload className="size-4" />上传私有论文</Button>
      </div>
      <div className="mt-5 flex items-center gap-2.5">
        <div className="relative min-w-[280px] max-w-[460px] flex-1"><Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索论文的标题/作者/会议" className="h-10 w-full rounded-xl border border-line bg-card pl-10 pr-4 text-sm text-ink outline-none placeholder:text-faint focus-visible:border-primary/50" /></div>
        <span className="text-xs text-faint">找到 {items.length} 篇</span>
      </div>
      {error && <div className="mt-5 rounded-xl bg-danger-soft p-4 text-sm text-danger">{error}<button type="button" onClick={() => void loadPage(page)} className="ml-3 underline">重试</button></div>}
      {unauthenticated ? <div className="mt-8 rounded-2xl bg-card p-12 text-center text-sm text-muted shadow-card">该功能需要登录后使用，请先登录</div> : !folderId ? <div className="mt-8 rounded-2xl bg-card p-12 text-center text-sm text-faint shadow-card">暂无文件夹</div> : !error && data && data.items.length === 0 ? <div className="mt-8 rounded-2xl bg-card p-12 text-center text-sm text-faint shadow-card">这个文件夹还是空的，快去收藏论文吧</div> : !error && <>
        <div className="mt-4 grid grid-cols-[minmax(0,1fr)_220px_100px_36px] items-center gap-4 rounded-xl bg-card px-5 py-3 text-xs text-faint shadow-card"><span>论文</span><span>作者</span><span>添加时间</span><span /></div>
        <div className="mt-3 space-y-2">
          {items.map((item) => (
            <div key={item.paper_id} className="grid grid-cols-[minmax(0,1fr)_220px_100px_36px] items-center gap-4 rounded-xl px-5 py-3 transition-colors hover:bg-card">
              <Link href={paperHref(item.paper_id, "/knowledge/papers")} className="flex min-w-0 items-center gap-3"><span className="flex h-11 w-9 shrink-0 items-end justify-center rounded-md bg-primary-soft pb-1 text-[10px] font-bold text-primary">PDF</span><span className="min-w-0"><span className="block truncate text-[15px] font-semibold text-ink">{item.title}</span><span className="mt-0.5 block truncate text-xs text-faint">{item.venue ?? "暂无会议"} · {item.year ?? "—"}</span></span></Link>
              <p className="truncate text-[13px] text-muted">{item.authors.join(" · ") || "未知作者"}</p>
              <time className="text-[13px] text-muted">{new Date(item.added_at).toLocaleDateString("zh-CN")}</time>
              <span className="relative"><button type="button" onClick={() => setMenu(menu === item.paper_id ? null : item.paper_id)} aria-label="论文操作" className="rounded-md p-1 text-faint hover:bg-chip"><MoreHorizontal className="size-4" /></button>{menu === item.paper_id && <span className="absolute right-0 top-full z-20 w-36 rounded-lg border border-line bg-card p-1 text-xs shadow-card"><button type="button" onClick={() => void removePaper(item.paper_id)} className="block w-full rounded-md px-2 py-1.5 text-left text-danger hover:bg-danger-soft">删除</button><span className="mt-1 block border-t border-line pt-1"><span className="block px-2 py-1 text-faint">移至</span>{folders.filter((folder) => folder.id !== folderId).map((folder) => <button key={folder.id} type="button" onClick={() => void movePaper(item.paper_id, folder.id)} className="block w-full truncate rounded-md px-2 py-1.5 text-left text-ink-2 hover:bg-chip">{folder.name}</button>)}</span></span>}</span>
            </div>
          ))}
        </div>
        {items.length === 0 && (data?.total ?? 0) > 0 && <div className="mt-3 rounded-2xl bg-card p-12 text-center text-sm text-faint shadow-card">未找到匹配的论文</div>}
        <div className="mt-5 flex justify-center gap-1">{Array.from({ length: Math.min(pageCount, 5) }, (_, index) => index + 1).map((number) => <button key={number} type="button" onClick={() => void loadPage(number)} className={`size-8 rounded-lg text-xs ${number === page ? "bg-primary text-white" : "text-muted hover:bg-chip"}`}>{number}</button>)}</div>
      </>}
    </section>
  );
}
