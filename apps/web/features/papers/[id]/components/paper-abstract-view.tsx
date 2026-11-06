"use client";

import { useEffect, useRef, useState } from "react";
import { BookOpen, ExternalLink, Quote } from "lucide-react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { Badge } from "@/components/ui/badge";
import { paperDoiUrl } from "@/lib/navigation/paper";
import { ABSTRACT_LINK_PLACEHOLDER, replaceAbstractLinks, splitAbstractLinks } from "../abstract-links";
import { HtmlGenerator, parse } from "latex.js";
import "katex/dist/katex.min.css";

const COLLAPSED_AUTHOR_COUNT = 6;
const ABSTRACT_LINK_CLASS =
  "[overflow-wrap:anywhere] text-primary underline decoration-primary/30 underline-offset-2 transition-colors hover:decoration-primary";

function createAbstractLink(text: string, href: string) {
  const link = document.createElement("a");
  link.href = href;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.className = ABSTRACT_LINK_CLASS;
  link.textContent = text;
  return link;
}

/** 将 LaTeX 渲染结果中的网址占位符还原为链接；网址文本始终取自原始摘要。 */
function restoreAbstractLinks(container: HTMLElement, links: ReturnType<typeof replaceAbstractLinks>["links"]) {
  if (!links.length) return;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    if (ABSTRACT_LINK_PLACEHOLDER.test(node.data)) textNodes.push(node);
  }
  for (const node of textNodes) {
    // split 带捕获组时，奇数位为占位符中的链接序号。
    const parts = node.data.split(new RegExp(ABSTRACT_LINK_PLACEHOLDER, "g"));
    node.replaceWith(...parts.map((part, index) => {
      if (index % 2 === 0) return part;
      const link = links[Number(part)];
      return link ? createAbstractLink(link.text, link.href) : "";
    }));
  }
}

export function PaperAbstractView({
  paper,
  onOpenPaper,
}: {
  paper: KnowledgePaperDetail;
  onOpenPaper?: () => void;
}) {
  const doiUrl = paperDoiUrl(paper.doi);
  const abstract = paper.abstract ?? "";
  const hasAbstract = abstract.trim().length > 0;
  // null 表示上游未提供，不显示为 0，也不占位展示“暂无数据”。
  const stats = [
    { label: "被引用", value: paper.citationCount },
    { label: "参考文献", value: paper.referenceCount },
  ].filter((item): item is { label: string; value: number } => item.value !== null && item.value !== undefined);

  return (
    <section
      aria-label={`${paper.title} 摘要`}
      className="mx-auto min-h-full w-full max-w-3xl px-6 py-10 lg:px-10 lg:py-12"
    >
      <header>
        {(paper.venue || paper.year) && (
          <div className="mb-4 flex flex-wrap items-center gap-1.5">
            {paper.venue && <Badge className="px-2.5 py-1">{paper.venue}</Badge>}
            {paper.year && <Badge variant="gray" className="px-2.5 py-1">{paper.year}</Badge>}
          </div>
        )}
        <h1 className="text-2xl font-semibold leading-snug tracking-tight text-ink text-balance lg:text-[1.875rem] lg:leading-[1.3]">
          {paper.title}
        </h1>
        <PaperAuthors authors={paper.authors} />
        {(stats.length > 0 || doiUrl || (onOpenPaper && paper.pdfUrl)) && (
          <div className="mt-6 flex flex-wrap items-center gap-2">
            {onOpenPaper && paper.pdfUrl && (
              <button
                type="button"
                onClick={onOpenPaper}
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-deep"
              >
                <BookOpen className="size-4" />
                阅读全文
              </button>
            )}
            {doiUrl && (
              <a
                href={doiUrl}
                target="_blank"
                rel="noreferrer"
                title={`DOI：${paper.doi}`}
                className="inline-flex h-9 max-w-full items-center gap-1.5 rounded-full border border-line px-3.5 text-sm text-ink-2 transition-colors hover:border-primary/40 hover:bg-primary-soft hover:text-primary"
              >
                <span className="font-medium">DOI</span>
                <span className="truncate text-muted">{paper.doi}</span>
                <ExternalLink className="size-3.5 shrink-0" />
              </a>
            )}
            {stats.map((item) => (
              <span
                key={item.label}
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-chip px-3.5 text-sm text-muted"
              >
                <Quote className="size-3.5" />
                {item.label}
                <span className="font-semibold tabular-nums text-ink-2">{item.value.toLocaleString()}</span>
              </span>
            ))}
          </div>
        )}
      </header>

      <div className="mt-10 border-t border-line pt-8">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-ink">
          <span aria-hidden="true" className="h-4 w-1 rounded-full bg-primary" />
          Abstract
        </h2>
        {hasAbstract ? (
          <LatexAbstractContent key={abstract} abstract={abstract} />
        ) : (
          <p className="mt-4 whitespace-pre-wrap text-[15px] leading-[1.85] text-muted">
            当前论文暂无摘要
          </p>
        )}
      </div>
      {(paper.keywords.length > 0 || paper.subjects.length > 0) && (
        <section className="mt-10 border-t border-line pt-6">
          <h3 className="mb-3 text-sm font-semibold text-ink">关键词与学科</h3>
          <div className="flex flex-wrap gap-2">
            {paper.keywords.map((word) => <Badge key={word} variant="violet">{word}</Badge>)}
            {paper.subjects.map((word) => <Badge key={word} variant="amber">{word}</Badge>)}
          </div>
        </section>
      )}
    </section>
  );
}

function PaperAuthors({ authors }: { authors: string[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!authors.length) return <p className="mt-4 text-sm text-muted">未知作者</p>;

  const collapsible = authors.length > COLLAPSED_AUTHOR_COUNT + 1;
  const visible = collapsible && !expanded ? authors.slice(0, COLLAPSED_AUTHOR_COUNT) : authors;

  return (
    <p className="mt-4 text-sm leading-6 text-ink-2">
      {visible.map((author, index) => (
        <span key={`${author}-${index}`}>
          {index > 0 && <span aria-hidden="true" className="px-1.5 text-faint">·</span>}
          {author}
        </span>
      ))}
      {collapsible && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((current) => !current)}
          className="ml-2 rounded-md px-1 text-primary hover:bg-primary-soft"
        >
          {expanded ? "收起" : `等 ${authors.length} 位作者`}
        </button>
      )}
    </p>
  );
}

function LatexAbstractContent({ abstract }: { abstract: string }) {
  const renderedAbstractRef = useRef<HTMLDivElement>(null);
  const fallbackRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const container = renderedAbstractRef.current;
    const fallback = fallbackRef.current;
    if (!container || !fallback) return;

    try {
      const { source, links } = replaceAbstractLinks(abstract);
      const generator = new HtmlGenerator({ hyphenate: false });
      parse(source, { generator });
      container.replaceChildren(generator.domFragment());
      restoreAbstractLinks(container, links);
      container.hidden = false;
      fallback.hidden = true;
    } catch (error) {
      console.error("Failed to render paper abstract with LaTeX.js.", error);
      container.replaceChildren();
      container.hidden = true;
      fallback.hidden = false;
    }

    return () => container.replaceChildren();
  }, [abstract]);

  return (
    <>
      <div
        ref={renderedAbstractRef}
        aria-label="论文摘要内容"
        className="paper-abstract-latex mt-4 max-w-full overflow-x-auto whitespace-pre-wrap text-[15px] leading-[1.85] text-ink-2"
        hidden
      />
      <p
        ref={fallbackRef}
        className="mt-4 whitespace-pre-wrap text-[15px] leading-[1.85] text-ink-2"
      >
        {splitAbstractLinks(abstract).map((segment, index) => (
          segment.type === "link"
            ? <a key={index} href={segment.href} target="_blank" rel="noreferrer" className={ABSTRACT_LINK_CLASS}>{segment.text}</a>
            : segment.text
        ))}
      </p>
    </>
  );
}
