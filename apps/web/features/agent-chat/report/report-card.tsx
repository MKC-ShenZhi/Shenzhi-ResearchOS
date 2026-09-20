"use client";

import * as React from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import "katex/dist/katex.min.css";
import type { AgentSource } from "@/clients/backend/agent";
import type { PaperRef } from "./paper-ref";
import { renderMarkdown } from "./markdown-pipeline";
import { imageFailureLabel, isUsableReportImage } from "./presentation";
import { CitationChip } from "./citation-chip";
import { ComparisonTable as ComparisonTableView } from "./comparison-table";

/**
 * 报告正文的「纸面文章」排版（PAPER token）。颜色一律走 app 设计令牌
 * （styles/globals.css 的 @theme），字号/行高/边距保持纸面比例不变。
 * 用容器后代选择器整体接管标题/段落/列表/代码/表格，天然处理 `pre > code`
 * 嵌套（块内 code 不吃行内 pill），并保留 paper / comparisontable 自定义渲染。
 */
const ARTICLE =
  // 尺度按**我们的实际容器宽度**定，不是照搬 SZDR 的数值：
  // SZDR 的报告占满整个主内容区（约 900-1100px），h1 30 / h2 23 / 正文 16 在那种宽度下是对的；
  // 我们的报告嵌在聊天回答流里（扣掉侧栏、头像列、卡片内边距，只剩约 600-700px），
  // 同一套字号在窄容器里比例上必然偏大。这里等比压到适合聊天宽度的一档，
  // 保留 SZDR 的视觉语言：h1 底线、h2 左侧色条、h3 主色、表格表头着色、引用块。
  "text-[14.5px] leading-[1.8] break-words text-ink " +
  "[&_h1]:mb-3.5 [&_h1]:mt-0 [&_h1]:border-b [&_h1]:border-line [&_h1]:pb-2 [&_h1]:text-[22px] [&_h1]:font-bold [&_h1]:leading-[1.35] [&_h1]:text-ink " +
  "[&_h2]:mb-2.5 [&_h2]:mt-6 [&_h2]:border-l-[3px] [&_h2]:border-primary [&_h2]:pl-2.5 [&_h2]:text-[17.5px] [&_h2]:font-bold [&_h2]:leading-[1.45] " +
  "[&_h3]:mb-2 [&_h3]:mt-[18px] [&_h3]:text-[15.5px] [&_h3]:font-bold [&_h3]:text-primary " +
  "[&_h4]:mb-1.5 [&_h4]:mt-4 [&_h4]:text-[14.5px] [&_h4]:font-bold " +
  "[&_p]:mb-[13px] " +
  "[&_a]:text-primary [&_a]:no-underline hover:[&_a]:underline " +
  "[&_ul]:mb-[13px] [&_ul]:pl-5 [&_ol]:mb-[13px] [&_ol]:pl-5 " +
  "[&_li]:my-0.5 [&_li::marker]:text-primary " +
  "[&_code]:rounded [&_code]:bg-chip [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.88em] [&_code]:text-ink " +
  "[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-[0.92em] " +
  "[&_pre]:mb-[13px] [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-chip [&_pre]:px-3.5 [&_pre]:py-2.5 [&_pre]:leading-[1.6] " +
  "[&_blockquote]:mb-[13px] [&_blockquote]:border-l-[3px] [&_blockquote]:border-line [&_blockquote]:bg-card [&_blockquote]:px-3 [&_blockquote]:py-2 " +
  "[&_table]:mb-[13px] [&_table]:w-full [&_table]:border-collapse [&_table]:text-[13.5px] " +
  "[&_th]:border-b [&_th]:border-line [&_th]:bg-primary-soft [&_th]:px-2.5 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold [&_th]:text-primary " +
  "[&_td]:border-b [&_td]:border-line [&_td]:px-2.5 [&_td]:py-2 [&_td]:text-ink [&_tr:last-child_td]:border-b-0 " +
  "[&_hr]:my-4 [&_hr]:border-t [&_hr]:border-line " +
  "[&_img]:mx-auto [&_img]:my-2 [&_img]:block [&_img]:max-w-full [&_img]:rounded-lg";

function MarkdownImage({ alt = "", src = "", title }: { alt?: string; src?: string; title?: string }) {
  // The failed src itself is the state, so a new src is "not failed" again
  // without an effect that would reset a boolean on every url change.
  const [failedSrc, setFailedSrc] = React.useState<string | null>(null);
  const failed = failedSrc !== null && failedSrc === src;
  if (failed || !src) {
    return (
      <div
        role="img"
        aria-label={imageFailureLabel(alt, "zh")}
        className="my-2.5 rounded-lg border border-dashed border-line bg-card p-4 text-center"
      >
        <p className="text-sm text-muted">{imageFailureLabel(alt, "zh")}</p>
        {src && <p className="mt-1 break-all text-xs text-faint">{src}</p>}
      </div>
    );
  }
  return (
    // Report figures are remote engine artifacts, not bundled assets;
    // next/image adds nothing here.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      title={title || alt || undefined}
      loading="lazy"
      decoding="async"
      onLoad={(event) => {
        const image = event.currentTarget;
        if (!isUsableReportImage(image.naturalWidth, image.naturalHeight)) {
          setFailedSrc(src);
        }
      }}
      onError={() => setFailedSrc(src)}
      className="mx-auto my-2.5 block max-w-full rounded-lg"
    />
  );
}

/** AgentSource 的字段全是可选的未知类型，逐个防御性取值（缺失即空串）。 */
function textOf(value: unknown): string {
  return typeof value === "string" ? value : value === undefined || value === null ? "" : String(value);
}

/**
 * 报告正文渲染（ResearchOS markdown stack）：
 *
 *   renderMarkdown (sanitize → splitTableBlocks → injectChips)  — 字符串层
 *   → react-markdown + rehype-raw                               — 元素层
 *
 * 注入的 `<Paper ns="1,3"></Paper>` / `<ComparisonTable idx="0"></ComparisonTable>`
 * 标记会被解析成小写 hast 元素（`paper` / `comparisontable`），由下面的
 * components 映射渲染为 React 组件。仍以 markdown 表格形态存活的表格
 * （图表来源清单区域）走 `table` 映射，带横向滚动容器。
 */
export function ReportCard({ text, sources }: { text: string; sources?: AgentSource[] }) {
  const references = React.useMemo<PaperRef[]>(
    () => (sources ?? []).map((source, index) => ({
      n: index + 1,
      document_id: textOf(source.document_id ?? source.id ?? source.url ?? index + 1),
      title: textOf(source.title) || "Source",
      abstract: textOf(source.abstract ?? source.snippet),
      year: textOf(source.year),
      authors: Array.isArray(source.authors) ? source.authors.map((author) => textOf(author)) : [],
      venue: textOf(source.venue),
      doi: textOf(source.doi),
      url: textOf(source.url),
      kind: source.kind === "paper" ? "paper" : "web",
    })),
    [sources],
  );
  const result = React.useMemo(() => renderMarkdown(text), [text]);
  const rootRef = React.useRef<HTMLDivElement>(null);

  // The markdown source never carries heading ids, so they are assigned
  // post-render in document order to match extractHeadings' sequential
  // `section-N` ids (the ToC scrolls via getElementById).
  // scroll-margin-top clears fixed chrome so scrollIntoView targets land
  // below it, not underneath.
  React.useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    root.querySelectorAll("h1, h2, h3").forEach((el, i) => {
      el.id = `section-${i}`;
      (el as HTMLElement).style.scrollMarginTop = "72px";
    });
  }, [result.text]);

  const components = React.useMemo<Components>(() => ({
    img: (props: { alt?: string; src?: string; title?: string }) => (
      <MarkdownImage alt={props.alt} src={props.src} title={props.title} />
    ),
    table: (props: { children?: React.ReactNode }) => (
      <div className="mb-4 max-w-full overflow-x-auto [touch-action:pan-x pan-y] [webkit-overflow-scrolling:touch]">
        <table>{props.children}</table>
      </div>
    ),
    paper: (props: { ns?: string }) => <CitationChip ns={props.ns ?? ""} references={references} />,
    comparisontable: (props: { idx?: string }) => (
      <ComparisonTableView idx={props.idx ?? ""} tables={result.tables} references={references} />
    ),
  }) as Components, [references, result.tables]);

  return (
    <div ref={rootRef} className={ARTICLE}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, [rehypeKatex, { trust: false, strict: "ignore" }]]}
        components={components}
      >
        {result.text}
      </ReactMarkdown>
    </div>
  );
}
