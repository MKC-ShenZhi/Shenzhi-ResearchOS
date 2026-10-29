"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Search, Upload } from "lucide-react";
import { apiJson, ApiError } from "@/clients/backend/http";
import { deletePrivatePaper, listPrivatePapers, privatePaperFileHref, uploadPrivatePaper, type PrivatePaper } from "@/clients/backend/private-papers";
import type { CollectionPaperListResponse } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { PaperCollectorCount } from "@/features/knowledge/interactions/components/paper-collector-count";
import { paperHref } from "@/lib/navigation/paper";
import { useCollections } from "@/stores/collections";
import { PaperReadBadgeForPaper } from "./paper-read-badge";

export function LibraryTable({ folderId }: { folderId: number | null }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CollectionPaperListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(folderId !== null);
  const [error, setError] = useState("");
  const [unauthenticated, setUnauthenticated] = useState(false);
  const [menu, setMenu] = useState<string | null>(null);
  const [privateMenu, setPrivateMenu] = useState<number | null>(null);
  const [privatePapers, setPrivatePapers] = useState<PrivatePaper[]>([]);
  const [privateTabOpen, setPrivateTabOpen] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const folders = useCollections((state) => state.folders);
  const loadFolders = useCollections((state) => state.loadFolders);
  const queryClient = useQueryClient();

  /** 收藏关系变化后，全平台收藏人数以服务端重新统计为准。 */
  function refreshCollectorCounts() {
    void queryClient.invalidateQueries({
      predicate: (query) => query.queryKey[0] === "paper-interaction",
    });
  }

  function handleLoadError(reason: unknown) {
    if (reason instanceof ApiError && reason.status === 401) {
      setError("");
      setUnauthenticated(true);
      return;
    }
    setError(reason instanceof ApiError && reason.status === 403 ? "无权访问该文件夹" : "文件夹内容加载失败");
  }

  useEffect(() => {
    if (folderId === null) return;
    let cancelled = false;
    void apiJson<CollectionPaperListResponse>(`/collections/folders/${folderId}/papers?page=1&page_size=20`)
      .then((response) => { if (!cancelled) { setError(""); setUnauthenticated(false); setData(response); setPage(1); setIsLoading(false); } })
      .catch((reason) => { if (!cancelled) { handleLoadError(reason); setIsLoading(false); } });
    return () => { cancelled = true; };
  }, [folderId]);

  useEffect(() => {
    if (folderId === null || folderId < 1) return;
    let cancelled = false;
    void listPrivatePapers(folderId).then((result) => {
      if (!cancelled) setPrivatePapers(result.items);
    }).catch((reason) => {
      if (!cancelled) {
        setPrivateTabOpen(true);
        setUploadError(reason instanceof ApiError && reason.status === 401
          ? "请先登录后查看私有论文" : "私有论文加载失败，请刷新重试");
      }
    });
    return () => { cancelled = true; };
  }, [folderId]);

  async function handlePrivateUpload(file: File | undefined) {
    if (!file || folderId === null || folderId < 1) return;
    setPrivateTabOpen(true);
    setUploadError("");
    if (!file.name.toLowerCase().endsWith(".pdf")) { setUploadError("仅支持 PDF 文件"); return; }
    if (file.size > 20 * 1024 * 1024) { setUploadError("私有论文不能超过 20 MB"); return; }
    setUploading(true);
    try {
      await uploadPrivatePaper(folderId, file);
      const result = await listPrivatePapers(folderId);
      setPrivatePapers(result.items);
      setPrivateTabOpen(true);
      await loadFolders();
    } catch (reason) {
      setUploadError(reason instanceof ApiError ? reason.message : "上传失败，请稍后重试");
    } finally {
      setUploading(false);
    }
  }

  async function removePrivatePaper(id: number) {
    if (!window.confirm("删除这篇私有论文？")) return;
    try {
      await deletePrivatePaper(id);
      setPrivatePapers((current) => current.filter((paper) => paper.id !== id));
      setPrivateMenu(null);
      await loadFolders();
    } catch (reason) {
      setPrivateTabOpen(true);
      setUploadError(reason instanceof ApiError ? reason.message : "删除失败，请重试");
    }
  }

  async function loadPage(nextPage: number) {
    if (!folderId) return;
    setError("");
    setIsLoading(true);
    try {
      setData(await apiJson<CollectionPaperListResponse>(`/collections/folders/${folderId}/papers?page=${nextPage}&page_size=20`));
      setPage(nextPage);
    } catch (reason) {
      handleLoadError(reason);
    } finally {
      setIsLoading(false);  
    }
  }

  async function removePaper(paperId: string) {
    if (!folderId) return;
    try {
      await apiJson<unknown>(`/collections/folders/${folderId}/papers/${encodeURIComponent(paperId)}`, { method: "DELETE" });
      await loadPage(page);
      await loadFolders();
      refreshCollectorCounts();
      setMenu(null);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) setUnauthenticated(true);
      else setError(reason instanceof ApiError && reason.status === 403 ? "无权访问该文件夹" : "操作失败，请重试");
    }
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
      refreshCollectorCounts();
      setMenu(null);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) setUnauthenticated(true);
      else setError(reason instanceof ApiError ? reason.message : "移动失败，请重试");
    }
  }

  const normalizedQuery = query.trim().toLowerCase();
  const items = data?.items.filter((item) => `${item.title} ${item.authors.join(" ")} ${item.venue ?? ""}`.toLowerCase().includes(normalizedQuery)) ?? [];
  const matchingPrivatePapers = privatePapers.filter((paper) => `${paper.title} ${paper.filename}`.toLowerCase().includes(normalizedQuery));
  const pageCount = Math.max(1, Math.ceil((data?.total ?? 0) / 20));

  return (
    <section className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-5 lg:h-full lg:min-h-0 lg:p-8">
      <div className="flex items-center gap-3">
        <div className="relative min-w-0 max-w-[460px] flex-1"><Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" /><input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="搜索本页深知论文及私有论文" placeholder="搜索本页深知论文及私有论文" className="h-10 w-full rounded-xl border border-line bg-card pl-10 pr-4 text-sm text-ink outline-none placeholder:text-faint focus-visible:border-primary/50" /></div>
        {normalizedQuery && <span className="text-xs text-faint">已显示匹配 {items.length + matchingPrivatePapers.length} 篇</span>}
      </div>
      <section className="mt-5 rounded-2xl bg-card p-3 sm:p-5 shadow-card" aria-label="深知论文">
      <h2 className="text-base font-semibold text-ink">深知论文</h2>
      {error && <div className="mt-4 rounded-xl bg-danger-soft p-4 text-sm text-danger">{error}<button type="button" onClick={() => void loadPage(page)} className="ml-3 underline">重试</button></div>}
      {unauthenticated ? <div className="mt-4 rounded-xl bg-panel p-6 text-center text-sm text-muted">该功能需要登录后使用，请先登录</div> : !folderId ? <div className="mt-4 rounded-xl bg-panel p-6 text-center text-sm text-faint">暂无文件夹</div> : isLoading ? <div className="mt-4 rounded-xl bg-panel p-6 text-center text-sm text-muted">加载中...</div> : error ? null : data && data.items.length === 0 ? <div className="mt-4 rounded-xl bg-panel p-6 text-center text-sm text-faint">当前文件夹暂无深知论文</div> : !error && <>
        <div className="mt-4 hidden lg:grid grid-cols-[minmax(0,1fr)_220px_100px_36px] items-center gap-4 border-b border-line px-3 py-2 text-xs text-faint"><span>论文</span><span>作者</span><span>添加时间</span><span /></div>
        <div className="divide-y divide-line">
          {items.map((item) => (
            <div key={item.paper_id} className="grid grid-cols-[minmax(0,1fr)_36px] lg:grid-cols-[minmax(0,1fr)_220px_100px_36px] items-center gap-4 rounded-xl px-3 py-3 transition-colors hover:bg-panel">
              <Link href={paperHref(item.paper_id, { mode: "create", source: "/knowledge/papers" })} className="flex min-w-0 items-center gap-3"><span className="flex h-11 w-9 shrink-0 items-end justify-center rounded-md bg-primary-soft pb-1 text-[10px] font-bold text-primary">PDF</span><span className="min-w-0"><span className="flex min-w-0 items-center gap-2"><span className="truncate text-[15px] font-semibold text-ink">{item.title}</span><PaperReadBadgeForPaper paperId={item.paper_id} /></span><span className="mt-0.5 block truncate text-xs text-faint">{item.venue ?? "暂无会议"} · {item.year ?? "—"} · <PaperCollectorCount paperId={item.paper_id} className="align-middle text-xs" /></span></span></Link>
              <p className="hidden truncate text-[13px] text-muted lg:block">{item.authors.join(" · ") || "未知作者"}</p>
              <time className="hidden text-[13px] text-muted lg:block">{new Date(item.added_at).toLocaleDateString("zh-CN")}</time>
              <span className="relative"><button type="button" onClick={() => setMenu(menu === item.paper_id ? null : item.paper_id)} aria-label="论文操作" className="rounded-md p-1 text-faint hover:bg-chip"><MoreHorizontal className="size-4" /></button>{menu === item.paper_id && <span className="absolute right-0 top-full z-20 w-36 rounded-lg border border-line bg-card p-1 text-xs shadow-card"><button type="button" onClick={() => void removePaper(item.paper_id)} className="block w-full rounded-md px-2 py-1.5 text-left text-danger hover:bg-danger-soft">删除</button><span className="mt-1 block border-t border-line pt-1"><span className="block px-2 py-1 text-faint">移至</span>{folders.filter((folder) => folder.id !== folderId).map((folder) => <button key={folder.id} type="button" onClick={() => void movePaper(item.paper_id, folder.id)} className="block w-full truncate rounded-md px-2 py-1.5 text-left text-ink-2 hover:bg-chip">{folder.name}</button>)}</span></span>}</span>
            </div>
          ))}
        </div>
        {items.length === 0 && (data?.total ?? 0) > 0 && <div className="mt-3 rounded-xl bg-panel p-6 text-center text-sm text-faint">未找到匹配的深知论文</div>}
        {pageCount > 1 && <div className="mt-3 flex justify-center gap-1">{Array.from({ length: Math.min(pageCount, 5) }, (_, index) => index + 1).map((number) => <button key={number} type="button" onClick={() => void loadPage(number)} className={`size-8 rounded-lg text-xs ${number === page ? "bg-primary text-white" : "text-muted hover:bg-chip"}`}>{number}</button>)}</div>}
      </>}
      </section>
      {!unauthenticated && folderId !== null && folderId > 0 && (
        <section className="mt-5 rounded-2xl bg-card p-3 sm:p-5 shadow-card" aria-label="私有论文">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2><button
              type="button"
              onClick={() => setPrivateTabOpen((open) => !open)}
              aria-expanded={privateTabOpen}
              aria-controls="private-paper-list"
              className="text-base font-semibold text-ink"
            >
              私有论文 <span className="ml-1 text-xs font-normal text-muted">{normalizedQuery ? matchingPrivatePapers.length : privatePapers.length}</span>
            </button></h2>
            <input ref={fileInput} type="file" accept=".pdf,application/pdf" className="hidden" onChange={(event) => { void handlePrivateUpload(event.target.files?.[0]); event.target.value = ""; }} />
            <Button className="rounded-xl" disabled={uploading} onClick={() => fileInput.current?.click()}><Upload className="size-4" />{uploading ? "上传中…" : "上传私有论文"}</Button>
          </div>
          {uploadError && <p role="alert" className="mt-4 text-sm text-danger">{uploadError}</p>}
          <div id="private-paper-list" hidden={!privateTabOpen}>
            {matchingPrivatePapers.length === 0 ? <div className="mt-4 rounded-xl bg-panel p-6 text-center text-sm text-faint">{normalizedQuery ? "未找到匹配的私有论文" : "当前文件夹暂无私有论文"}</div> : <>
              <div className="mt-4 hidden lg:grid grid-cols-[minmax(0,1fr)_220px_100px_36px] items-center gap-4 border-b border-line px-3 py-2 text-xs text-faint"><span>论文</span><span>作者</span><span>添加时间</span><span /></div>
              <div className="divide-y divide-line">{matchingPrivatePapers.map((paper) => (
                <div key={paper.id} className="grid grid-cols-[minmax(0,1fr)_36px] lg:grid-cols-[minmax(0,1fr)_220px_100px_36px] items-center gap-4 rounded-xl px-3 py-3 transition-colors hover:bg-panel">
                  <a href={privatePaperFileHref(paper.id)} target="_blank" rel="noopener noreferrer" className="flex min-w-0 items-center gap-3"><span className="flex h-11 w-9 shrink-0 items-end justify-center rounded-md bg-primary-soft pb-1 text-[10px] font-bold text-primary">PDF</span><span className="min-w-0"><span className="block truncate text-[15px] font-semibold text-ink">{paper.title}</span><span className="mt-0.5 block text-xs text-faint">私有上传 · {(paper.size_bytes / 1024 / 1024).toFixed(1)} MB</span></span></a>
                  <span className="hidden text-[13px] text-muted lg:block">—</span>
                  <time className="hidden text-[13px] text-muted lg:block">{new Date(paper.created_at).toLocaleDateString("zh-CN")}</time>
                  <span className="relative"><button type="button" onClick={() => setPrivateMenu(privateMenu === paper.id ? null : paper.id)} aria-label="私有论文操作" className="rounded-md p-1 text-faint hover:bg-chip"><MoreHorizontal className="size-4" /></button>{privateMenu === paper.id && <span className="absolute right-0 top-full z-20 w-28 rounded-lg border border-line bg-card p-1 text-xs shadow-card"><a href={privatePaperFileHref(paper.id)} target="_blank" rel="noopener noreferrer" className="block rounded-md px-2 py-1.5 text-ink-2 hover:bg-chip">查看</a><button type="button" onClick={() => void removePrivatePaper(paper.id)} className="block w-full rounded-md px-2 py-1.5 text-left text-danger hover:bg-danger-soft">删除</button></span>}</span>
                </div>
              ))}</div>
            </>}
          </div>
        </section>
      )}
    </section>
  );
}
