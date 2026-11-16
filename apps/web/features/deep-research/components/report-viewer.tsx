import { Sparkles } from "lucide-react";
import { withCitations } from "@/components/common/citations";
import { drReport } from "@/features/deep-research/data";
import { cn } from "@/lib/utils";
import type { DRReportSection } from "@/types";
import type { DRSectionState } from "./use-deep-research-run";

/** 性能对比表(与深度搜索答案卡同款样式) */
function ReportTable({
  table,
}: {
  table: NonNullable<DRReportSection["table"]>;
}) {
  return (
    <div>
      <p className="text-[13px] font-medium text-ink">{table.caption}</p>
      <div className="mt-2 overflow-hidden rounded-xl bg-panel px-5 py-2">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-faint">
              {table.header.map((h, i) => (
                <th key={i} className="py-2.5 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, ri) => {
              const highlighted = ri === table.highlightRow;
              return (
                <tr
                  key={ri}
                  className={cn(highlighted && "font-semibold text-primary")}
                >
                  <td className="py-2.5">
                    {withCitations(row[0])}
                    {highlighted && (
                      <span className="ml-1.5 text-xs">· 推荐</span>
                    )}
                  </td>
                  {row.slice(1).map((cell, ci) => (
                    <td key={ci} className="py-2.5">
                      {cell}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * Deep Research 报告 —— 报告头 + 章节三态(已生成 / 生成中 / 待生成)+ 参考文献
 * 全部章节完成后出现参考文献列表
 */
export function ReportViewer({
  sectionState,
}: {
  sectionState: Record<string, DRSectionState>;
}) {
  const started = Object.values(sectionState).some((s) => s !== "todo");
  const allDone =
    Object.keys(sectionState).length > 0 &&
    Object.values(sectionState).every((s) => s === "done");

  return (
    <article className="rounded-2xl bg-card p-6 shadow-card">
      {/* 品牌行(与深度搜索答案卡同源) */}
      <div className="flex items-center gap-2.5">
        <span className="flex size-8 items-center justify-center rounded-full bg-primary">
          <Sparkles className="size-4 text-white" aria-hidden="true" />
        </span>
        <span className="text-sm font-semibold text-ink">
          深知 AI · Deep Research
        </span>
        <span className="rounded bg-brand-gold px-1.5 py-0.5 text-[10px] font-bold text-ink">
          Pro
        </span>
      </div>

      <header className="mt-4 border-b border-line pb-4">
        <h1 className="text-lg font-bold text-ink">{drReport.title}</h1>
        {started ? (
          <p className="mt-2 text-sm leading-relaxed text-muted">
            {drReport.abstract}
          </p>
        ) : (
          <p className="mt-2 text-sm text-faint">
            研究完成后,这里将生成报告摘要…
          </p>
        )}
        <p className="mt-2 text-xs text-faint">
          阅读 {drReport.stats.read} 篇 · 引用 {drReport.stats.cited} 篇
        </p>
      </header>

      <div className="mt-4 space-y-6">
        {drReport.sections.map((sec) => {
          const state = sectionState[sec.id] ?? "todo";

          if (state === "todo") {
            return (
              <section
                key={sec.id}
                className="rounded-xl border border-dashed border-line p-4 opacity-60"
              >
                <h2 className="text-[15px] font-bold text-faint">
                  {sec.heading}
                </h2>
                <p className="mt-2 text-xs text-faint">待生成</p>
              </section>
            );
          }

          if (state === "running") {
            return (
              <section
                key={sec.id}
                className="rounded-xl border border-primary/40 bg-primary-soft/40 p-4"
              >
                <h2 className="text-[15px] font-bold text-ink">
                  {sec.heading}
                </h2>
                <p className="mt-2 text-[15px] leading-relaxed text-ink-2">
                  {sec.paragraphs[0]
                    ? withCitations(sec.paragraphs[0])
                    : "正在撰写…"}
                  <span
                    className="ml-1 inline-block h-4 w-2 animate-pulse rounded-sm bg-primary align-text-bottom"
                    aria-hidden="true"
                  />
                </p>
              </section>
            );
          }

          return (
            <section key={sec.id}>
              <h2 className="text-[15px] font-bold text-ink">{sec.heading}</h2>
              <div className="mt-2 space-y-4 text-[15px] leading-relaxed text-ink-2">
                {sec.paragraphs.map((p, i) => (
                  <p key={i}>{withCitations(p)}</p>
                ))}
                {sec.table && <ReportTable table={sec.table} />}
                {sec.list && (
                  <ol className="space-y-2.5">
                    {sec.list.map((item, i) => (
                      <li key={i} className="flex items-start gap-3">
                        <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[11px] font-semibold text-primary">
                          {i + 1}
                        </span>
                        <span>{withCitations(item)}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </section>
          );
        })}

        {allDone && (
          <section className="border-t border-line pt-4">
            <h2 className="text-[15px] font-bold text-ink">参考文献</h2>
            <ol className="mt-2 space-y-1.5">
              {drReport.references.map((r) => (
                <li
                  key={r.id}
                  className="flex gap-2 text-[13px] leading-relaxed text-ink-2"
                >
                  <span className="shrink-0 font-medium text-primary">
                    [{r.id}]
                  </span>
                  <span>
                    {r.title} ·{" "}
                    <span className="text-faint">
                      {r.venue} · {r.author}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
    </article>
  );
}
