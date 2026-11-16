import { Sparkles } from "lucide-react";
import { answerBlocks, agentSession } from "@/features/search/deep-search/data";
import { withCitations } from "@/components/common/citations";
import { cn } from "@/lib/utils";
/** AI 深度研究回答卡片 —— 对应 AI 研究助手 SVG 的回答区 */
export function AnswerCard() {
  const { table } = answerBlocks;

  return (
    <article className="rounded-2xl bg-card p-6 shadow-card">
      {/* 头部 */}
      <div className="flex items-center gap-2.5 border-b border-line pb-4">
        <span className="flex size-8 items-center justify-center rounded-full bg-primary">
          <Sparkles className="size-4 text-white" />
        </span>
        <span className="text-sm font-semibold text-ink">深知 AI · 深度研究</span>
        <span className="rounded bg-brand-gold px-1.5 py-0.5 text-[10px] font-bold text-ink">
          Pro
        </span>
        <span className="text-xs text-faint">{agentSession.meta}</span>
      </div>

      <div className="mt-4 space-y-4 text-[15px] leading-relaxed text-ink-2">
        <p>{withCitations(answerBlocks.intro)}</p>

        <h3 className="pt-1 text-[15px] font-bold text-ink">
          {answerBlocks.methodHeading}
        </h3>
        <p>{withCitations(answerBlocks.methodBody)}</p>

        {/* 性能对比表 */}
        <div>
          <p className="text-[13px] font-medium text-ink">
            {answerBlocks.tableCaption}
          </p>
          <div className="mt-2 overflow-hidden rounded-xl bg-panel px-5 py-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-faint">
                  {table.header.map((h) => (
                    <th key={h} className="py-2.5 font-normal">
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
                      key={row[0]}
                      className={cn(
                        highlighted && "font-semibold text-primary",
                      )}
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

        <p>{withCitations(answerBlocks.industryBody)}</p>

        <h3 className="pt-1 text-[15px] font-bold text-ink">
          {answerBlocks.trendHeading}
        </h3>
        <ol className="space-y-2.5">
          {answerBlocks.trends.map((trend, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[11px] font-semibold text-primary">
                {i + 1}
              </span>
              <span>{withCitations(trend)}</span>
            </li>
          ))}
        </ol>

        <p>{withCitations(answerBlocks.conclusion)}</p>
      </div>
    </article>
  );
}
