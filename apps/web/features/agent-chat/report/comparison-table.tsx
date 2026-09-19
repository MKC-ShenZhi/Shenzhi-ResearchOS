"use client";

import * as React from "react";
import type { PaperRef } from "./paper-ref";
import type { ParsedTable } from "./markdown-pipeline";

/**
 * Minimal inline-markdown renderer for table cells. The comparison table
 * renders extracted cell text outside react-markdown, so model-emitted inline
 * syntax (`**5,048 MB**`) would otherwise show as literal asterisks. Covers
 * the subset the model actually emits in cells — bold / emphasis / code /
 * http links — and leaves anything unmatched as literal text.
 *
 * Local to this file on purpose: the comparison table is its only consumer
 * (app-wide markdown goes through react-markdown in report-card.tsx).
 */
function renderInlineMarkdown(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  // **bold** | *em* (no space right after the opening asterisk, so "3 * 4"
  // arithmetic stays literal) | `code` | [label](http url)
  const re =
    /(\*\*([^*]+)\*\*)|(\*([^*\s][^*]*)\*)|(`([^`]+)`)|(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g;
  let last = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    if (match[2] !== undefined) nodes.push(<strong key={key++} className="font-semibold">{match[2]}</strong>);
    else if (match[4] !== undefined) nodes.push(<em key={key++}>{match[4]}</em>);
    else if (match[6] !== undefined) nodes.push(<code key={key++} className="rounded bg-chip px-1 py-0.5 font-mono text-[0.92em]">{match[6]}</code>);
    else if (match[8] !== undefined) nodes.push(<a key={key++} href={match[9]} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{match[8]}</a>);
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/**
 * How many data columns fit at the current viewport width (md 900px,
 * lg 1200px — the breakpoints the report layout itself uses). A hook, not
 * CSS, because pagination is stateful: the page index must clamp when the
 * viewport narrows.
 */
function useMaxCols(): number {
  const [cols, setCols] = React.useState(3);
  React.useEffect(() => {
    const md = window.matchMedia("(max-width: 899px)");
    const lg = window.matchMedia("(max-width: 1199px)");
    const update = () => setCols(md.matches ? 1 : lg.matches ? 2 : 3);
    update();
    md.addEventListener("change", update);
    lg.addEventListener("change", update);
    return () => {
      md.removeEventListener("change", update);
      lg.removeEventListener("change", update);
    };
  }, []);
  return cols;
}

/** Cell text carries literal `<br>` from the markdown source; React would
 * escape it, so split into real line breaks. Each line goes through the
 * inline-markdown renderer so `**bold**` etc. inside cells render properly. */
function Lines({ text }: { text: string }) {
  return (
    <>
      {text.split("<br>").map((line, i) => (
        <React.Fragment key={i}>
          {i > 0 && <br />}
          {renderInlineMarkdown(line)}
        </React.Fragment>
      ))}
    </>
  );
}

/**
 * Renders one `## 对比表` comparison table with column pagination
 * (3 → 2 → 1 based on viewport width).
 * The first column holds `[n] Title` — the [n] is a superscript matching
 * running-text citations (it is NOT a clickable CitationChip; those are
 * injected only into running text).
 */
export function ComparisonTable({ idx, tables, references }: {
  idx: string;
  tables: ParsedTable[];
  references: PaperRef[];
}) {
  const maxCols = useMaxCols();
  // All hooks must run before the early return: an empty/dangling table
  // index must not change the hook count between renders.
  const [page, setPage] = React.useState(0);
  const table = tables[parseInt(idx, 10)];

  // Unknown / empty table (e.g. dangling marker after pipeline change).
  if (!table || table.rows.length === 0) {
    return null;
  }

  const { header, rows } = table;
  const colCount = Math.min(maxCols, header.length);
  const dataCols = header.slice(1); // column 0 is the paper column
  const pages = Math.ceil(Math.max(1, dataCols.length) / colCount);
  // Clamp the current page: colCount changes with viewport width (3→2→1),
  // which shrinks `pages`; an out-of-range page makes `visible` empty and
  // the table render blank.
  const pageIdx = Math.min(page, pages - 1);
  const start = pageIdx * colCount;
  const visible = dataCols.slice(start, start + colCount);

  // First column is `[n] Title` — split off the number for the chip.
  const splitFirst = (cell: string) => {
    const m = cell.match(/^\[(\d+)\]\s*([\s\S]*)$/);
    if (m) return { n: parseInt(m[1], 10), rest: m[2] };
    return { n: null, rest: cell };
  };

  return (
    <div className="my-4">
      {/* 参考站纸面表格：卡片底 + 主色表头行 + 细格线 */}
      <div className="max-w-full overflow-x-auto rounded-xl border border-line bg-card shadow-card [touch-action:pan-x pan-y] [webkit-overflow-scrolling:touch]">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th className="min-w-[180px] border-b border-line bg-primary-soft px-3 py-2.5 text-left font-semibold text-primary">
                {renderInlineMarkdown(header[0] ?? "")}
              </th>
              {visible.map((h, i) => (
                <th key={`${h}-${start + i}`} className="min-w-[120px] border-b border-line bg-primary-soft px-3 py-2.5 text-left font-semibold text-primary">
                  {renderInlineMarkdown(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => {
              const { n, rest } = splitFirst(row[0] ?? "");
              const ref = n !== null ? references[n - 1] : undefined;
              return (
                <tr key={ri} className="transition-colors hover:bg-primary-soft">
                  <td className="min-w-[180px] border-b border-line px-3 py-2.5 text-sm text-ink last:border-b-0 [&:last-child]:border-b-0">
                    <span className="leading-[1.55]">
                      {n !== null && ref && (
                        <sup className="inline select-none align-super text-[0.7rem] font-semibold leading-none text-primary">[{n}]</sup>
                      )}
                      <Lines text={rest} />
                    </span>
                  </td>
                  {visible.map((_, ci) => {
                    const cell = row[1 + start + ci];
                    return (
                      <td key={ci} className="min-w-[120px] border-b border-line px-3 py-2.5 text-sm text-ink [&:last-child]:border-b-0">
                        <span className="leading-[1.55]"><Lines text={cell ?? ""} /></span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="mt-2 flex items-center justify-end gap-2">
          <span className="text-xs text-muted">{pageIdx + 1}/{pages}</span>
          <div className="flex overflow-hidden rounded-lg border border-line">
            <button
              type="button"
              disabled={pageIdx === 0}
              onClick={() => setPage(Math.max(0, pageIdx - 1))}
              className="min-w-9 cursor-pointer px-2 py-1 text-xs text-ink-2 transition-colors hover:bg-chip disabled:cursor-not-allowed disabled:opacity-40"
            >
              &lt;
            </button>
            <button
              type="button"
              disabled={pageIdx >= pages - 1}
              onClick={() => setPage(Math.min(pages - 1, pageIdx + 1))}
              className="min-w-9 cursor-pointer border-l border-line px-2 py-1 text-xs text-ink-2 transition-colors hover:bg-chip disabled:cursor-not-allowed disabled:opacity-40"
            >
              &gt;
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
