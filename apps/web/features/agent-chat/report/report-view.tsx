"use client";

import * as React from "react";
import { ChevronLeft, Link2 } from "lucide-react";
import type { AgentSource } from "@/clients/backend/agent";
import { extractHeadings, type Heading } from "./markdown-pipeline";
import { cn } from "@/lib/utils";
import { ReportCard } from "./report-card";

/** AgentSource 的字段全是可选的未知类型，展示层逐个防御性取值（缺失即空串）。 */
function textOf(value: unknown): string {
  return typeof value === "string" ? value : value === undefined || value === null ? "" : String(value);
}

/** 二级展示元信息：venue / year / 前两位作者，缺哪个跳哪个。 */
function refMeta(source: AgentSource): string[] {
  const authors = Array.isArray(source.authors) ? source.authors.map((author) => textOf(author)).filter(Boolean) : [];
  return [textOf(source.venue), textOf(source.year), authors.slice(0, 2).join(", ")].filter(Boolean);
}

/**
 * Report layout in the ChatGPT-Deep-Research mold: a collapsible table of
 * contents beside the rendered answer (headings carry `section-N` anchors
 * assigned by the markdown renderer), and the numbered source list at the
 * end. Citation chips inside the text open the same sources as a popover.
 */
export function ReportView({ text, sources, showToc = true }: { text: string; sources?: AgentSource[]; showToc?: boolean }) {
  const headings = React.useMemo(() => extractHeadings(text).filter((heading) => heading.level <= 2), [text]);
  const [activeId, setActiveId] = React.useState<string | null>(null);
  // Which index the collapsed tail of the reference list starts from; null = expanded.
  const [collapsedFrom, setCollapsedFrom] = React.useState<number | null>(60);
  // Report-local collapsible TOC: defaults open on wide screens, hidden on xs.
  const [tocOpen, setTocOpen] = React.useState(true);
  const hasToc = showToc && headings.length >= 2;

  // Scroll-spy: the heading closest above the scroll anchor of the report body
  // is the active entry. Scoped to this report's container so multiple reports
  // in one conversation track independently.
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    if (headings.length < 2) return;
    const container = containerRef.current;
    if (!container) return;
    const onScroll = () => {
      const anchor = container.getBoundingClientRect().top + 72;
      let current: Heading | null = null;
      for (const heading of headings) {
        const element = container.querySelector(`#${heading.id}`);
        if (!element) continue;
        if ((element as HTMLElement).getBoundingClientRect().top <= anchor) current = heading;
      }
      setActiveId(current?.id ?? headings[0]?.id ?? null);
    };
    onScroll();
    container.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { container.removeEventListener("scroll", onScroll); window.removeEventListener("scroll", onScroll); };
  }, [headings]);

  const scrollTo = (id: string) => {
    const element = containerRef.current?.querySelector(`#${id}`);
    if (element) {
      (element as HTMLElement).scrollIntoView({ behavior: "smooth", block: "start" });
      setActiveId(id);
    }
  };

  return (
    <div className="relative flex items-start gap-6">
      <div
        ref={containerRef}
        className="scrollbar-subtle max-h-[72vh] min-w-0 flex-1 overflow-y-auto rounded-xl border border-line bg-card px-5 py-6 shadow-card min-[900px]:px-8"
      >
        <ReportCard text={text} sources={sources ?? []} />
        {(sources?.length ?? 0) > 0 && (() => {
          // Cited sources (markers actually used in the answer) come first; the rest
          // stay listed but collapsed behind one click, so a 170-source run doesn't
          // bury the references the reader will actually check.
          const cited = new Set([...text.matchAll(/\[(\d+(?:[,\s]\d+)*)\]/g)].flatMap((match) => match[1].split(/[,\s]+/)).map(Number));
          const ordered = [...sources!].map((source, index) => ({ source, index })).sort((a, b) => Number(cited.has(b.index + 1)) - Number(cited.has(a.index + 1)));
          const citedCount = ordered.filter((entry) => cited.has(entry.index + 1)).length;
          const COLLAPSED_FROM = 60;
          const showAll = collapsedFrom === null;
          const visibleCount = showAll ? ordered.length : Math.min(citedCount + 8, Math.max(COLLAPSED_FROM, citedCount + 8));
          return (
            <div className="mt-8">
              <div className="mb-4 border-t border-line" />
              <div className="mb-3 flex items-center gap-2">
                <Link2 className="size-[17px] text-muted" />
                <span className="text-sm font-semibold text-muted">参考文献（{sources!.length}，其中被引用 {citedCount}）</span>
              </div>
              <div className="space-y-1.5 pl-1">
                {ordered.slice(0, visibleCount).map(({ source, index }) => {
                  const url = textOf(source.url);
                  const title = textOf(source.title) || url || "(未命名)";
                  const readDepth = textOf(source.readDepth);
                  return (
                    <div
                      key={`${textOf(source.id) || url || index}-${index}`}
                      title={url ? "打开来源" : undefined}
                      className={cn("flex items-baseline gap-3", url && "-mx-2 cursor-pointer rounded-lg px-2 transition-colors duration-200 hover:bg-primary-soft")}
                    >
                      <span className="min-w-6 text-right text-xs font-bold text-primary">{index + 1}</span>
                      <div className="min-w-0">
                        {url ? (
                          <a href={url} target="_blank" rel="noreferrer" title={title}
                            className="block truncate text-sm no-underline hover:text-primary hover:underline">
                            {title}
                          </a>
                        ) : (
                          <p className="truncate text-sm" title={title}>{title}</p>
                        )}
                        <div className="flex items-center gap-2">
                          {refMeta(source).map((meta, position) => (
                            <span key={position} className="truncate text-xs text-muted">{meta}</span>
                          ))}
                          {source.kind === "web" && <span className="rounded bg-chip px-1.5 py-0.5 text-[10px] text-muted">网页</span>}
                          {Boolean(source.preprint) && (
                            <span title="arXiv 托管且无正式 DOI/venue，未经同行评审" className="rounded bg-brand-gold/20 px-1.5 py-0.5 text-[10px] text-ink-2">预印本</span>
                          )}
                          {readDepth === "full" && <span title="已读这篇的全文" className="rounded bg-success-soft px-1.5 py-0.5 text-[10px] text-success">已读全文</span>}
                          {readDepth === "abstract" && <span title="只基于摘要引用" className="rounded bg-chip px-1.5 py-0.5 text-[10px] text-muted">仅摘要</span>}
                          {readDepth === "head" && <span title="批读的全文头部摘录" className="rounded bg-primary-soft px-1.5 py-0.5 text-[10px] text-primary">头部摘录</span>}
                        </div>
                      </div>
                    </div>
                  );
                })}
                {ordered.length > visibleCount && (
                  <button
                    type="button"
                    onClick={() => setCollapsedFrom(null)}
                    className="mt-1 cursor-pointer self-start text-[13px] text-primary hover:underline"
                  >
                    展开其余 {ordered.length - visibleCount} 条参考文献
                  </button>
                )}
              </div>
            </div>
          );
        })()}
      </div>
      {hasToc && (
        <div
          className={cn(
            // min-[900px] 精确复刻报告布局的 md 断点（Tailwind md=768 会在 768–900px
            // 窗口误显示 TOC，把报告卡挤到不可读的宽度）。
            "sticky top-0 hidden max-h-[78vh] flex-row transition-all duration-200 min-[900px]:flex",
            tocOpen ? "w-1/4 min-w-[200px] max-w-[280px]" : "w-[34px] min-w-[34px]",
          )}
        >
          <button
            type="button"
            onClick={() => setTocOpen((value) => !value)}
            aria-label={tocOpen ? "收起目录" : "展开目录"}
            title={tocOpen ? "收起目录" : "展开目录"}
            className="my-1 grid size-[34px] min-w-[34px] cursor-pointer place-items-center rounded-lg text-muted transition-colors duration-200 hover:bg-primary-soft hover:text-primary"
          >
            <span className={cn("grid place-items-center transition-transform duration-200", !tocOpen && "rotate-180")}>
              <ChevronLeft className="size-[18px]" />
            </span>
          </button>
          {tocOpen && (
            <div className="scrollbar-subtle min-w-0 flex-1 overflow-y-auto border-l border-line pb-2 pl-3 pt-2">
              <span className="mb-1 block text-[10px] font-semibold uppercase tracking-[.08em] text-muted">目录</span>
              <nav className="block">
                {headings.map((heading) => (
                  <a
                    key={heading.id}
                    title={heading.text}
                    onClick={(event) => { event.preventDefault(); scrollTo(heading.id); }}
                    className={cn(
                      "block cursor-pointer truncate rounded-sm py-1 no-underline transition-colors duration-200 hover:text-primary",
                      heading.level === 2 ? "pl-4" : "pl-1",
                      activeId === heading.id ? "bg-primary-soft font-bold text-primary" : "font-normal text-muted",
                    )}
                  >
                    {heading.text}
                  </a>
                ))}
              </nav>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
