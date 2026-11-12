import { BarChart3 } from "lucide-react";
import type { ScholarProfile } from "../types";
import { recentCitations } from "../presentation";

/** 沿用项目纯 CSS 柱图方案；只绘制有效的已提供年份，不补零、不推导总引用。 */
export function AnnualCitations({
  data,
}: {
  data: ScholarProfile["annual_citations"];
}) {
  const citations = recentCitations(data);
  const max = Math.max(1, ...citations.map((item) => item.count));
  return (
    <section
      className="min-w-0"
      aria-labelledby="citations-title"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 id="citations-title" className="text-sm font-semibold text-ink">
          年度引用
        </h2>
        <span className="text-xs tabular-nums text-muted">
          {citations.length ? `${citations[0].year}–${citations[citations.length - 1].year}` : "暂无数据"}
        </span>
      </div>
      <p className="mt-1.5 text-xs leading-5 text-muted">
        论文在对应年份获得的引用次数
      </p>
      {citations.length ? (
        <>
          <div className="relative mt-4 border-b border-line">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 flex flex-col justify-between pb-10"
            >
              <div className="border-t border-line/60" />
              <div className="border-t border-line/60" />
              <div className="border-t border-line/60" />
            </div>
            <div className="relative flex gap-1.5 px-0.5">
              {citations.map(({ year, count }) => (
                <div key={year} className="min-w-0 flex-1 text-center">
                  <div className="flex h-36 flex-col justify-end">
                    <span className="mb-2 text-[11px] font-medium tabular-nums text-ink-2">
                      {count.toLocaleString("en-US")}
                    </span>
                    <div
                      className="mx-auto w-full max-w-5 rounded-t-sm bg-primary/70"
                      style={{ height: `${(count / max) * 120}px` }}
                      aria-hidden="true"
                    />
                  </div>
                  <p className="py-2.5 text-xs tabular-nums text-muted">
                    {year}
                  </p>
                </div>
              ))}
            </div>
          </div>
          <table className="sr-only">
            <caption>年度引用数据</caption>
            <thead>
              <tr>
                <th>年份</th>
                <th>引用次数</th>
              </tr>
            </thead>
            <tbody>
              {citations.map(({ year, count }) => (
                <tr key={year}>
                  <td>{year}</td>
                  <td>{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs leading-5 text-muted">
            最近五个有统计的年份
          </p>
        </>
      ) : (
        <div className="flex min-h-32 flex-col items-center justify-center text-muted">
          <BarChart3 aria-hidden="true" className="size-7 text-faint" />
          <p className="mt-3 text-sm">暂无年度引用数据</p>
        </div>
      )}
    </section>
  );
}
