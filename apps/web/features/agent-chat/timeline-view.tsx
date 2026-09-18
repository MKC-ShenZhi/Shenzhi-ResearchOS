/**
 * 过程区渲染：把 `timeline.ts` 产出的条目按 pi 的方式画出来。
 *
 * pi 的对应物是 assistant-message.ts（内容块）+ tool-execution.ts（工具条目）：
 * 思考是弱化色的斜体文本块，正文是普通 markdown，工具行是等宽的一行。
 * 整个过程区（思考 + 工具 + 过渡正文）套**一个**折叠框、默认收起（产品要求：
 * 答案优先，过程按需展开）；折叠态的 summary 保留运行指示与最新动作预览，
 * 收起时也看得出 agent 正在干什么。
 */
import { Loader2 } from "lucide-react";

import { previewLine, renderEntries, type Activity, type Entry, type StreamState } from "./timeline";

function ToolLine({ tool }: { tool: Activity }) {
  return (
    <div className="flex items-center gap-2 font-mono text-xs text-muted">
      <span className={`shrink-0 ${tool.isError ? "text-red-500" : tool.done ? "text-agent" : "text-ink-2"}`}>
        {!tool.done ? "→" : tool.isError ? "✗" : "✓"}
      </span>
      {!tool.done && <Loader2 className="size-3 shrink-0 animate-spin text-agent" strokeWidth={2.2} aria-hidden />}
      <span className="min-w-0 truncate text-ink-2">{tool.name}</span>
      {tool.arguments && (
        <span className="min-w-0 flex-1 truncate text-faint" title={tool.arguments}>
          {previewLine(tool.arguments)}
        </span>
      )}
      {tool.done && <span className="shrink-0 text-faint">{tool.durationMs}ms</span>}
    </div>
  );
}

/**
 * 思考块：折叠，展开看全文；折叠态用单行预览保留"它在想什么"的线索。
 *
 * 默认折叠是因为一段思考往往几百字，展开会把工具行挤到屏幕外；但完全不显示又看不出
 * 它在干什么——所以折叠态必须有预览（空内容由 renderEntries 过滤，这里不再判）。
 */
function ThinkingBlock({ text, live }: { text: string; live: boolean }) {
  return (
    <details className="group">
      <summary className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-muted hover:text-ink">
        {live
          ? <Loader2 className="size-3 shrink-0 animate-spin text-agent" strokeWidth={2.2} aria-hidden />
          : <span className="shrink-0 text-faint transition-transform group-open:rotate-90">›</span>}
        <span className="shrink-0">{live ? "正在思考" : "思考"}</span>
        <span className="min-w-0 flex-1 truncate text-faint">{previewLine(text)}</span>
      </summary>
      <div className="mt-1 whitespace-pre-wrap border-l-2 border-line pl-3 text-xs italic leading-6 text-muted">
        {text}
      </div>
    </details>
  );
}

/** 正文块：一轮的正文。过程区里用稍弱的字号与色，避免与最终答案抢注意力。 */
function TextBlock({ text }: { text: string }) {
  return <div className="whitespace-pre-wrap text-[13px] leading-6 text-ink-2">{text}</div>;
}

/** 折叠态 summary 的最新动作预览：工具给"名字(参数)"，思考/正文给单行文本。 */
function entryPreview(entry: Entry | undefined): string {
  if (!entry) return "";
  if (entry.kind === "tool") {
    return `${entry.tool.name}(${previewLine(entry.tool.arguments ?? "", 60)})`;
  }
  return previewLine(entry.text);
}

export function Timeline({ state, live }: { state: StreamState; live: boolean }) {
  const entries = renderEntries(state);
  if (entries.length === 0 && !live) return null;
  const lastIndex = entries.length - 1;

  return (
    // details 不加 open 属性 = 默认收起；展开与否由 DOM 自持，React 重渲染不打断用户操作
    <details className="group mb-3">
      <summary className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-muted hover:text-ink">
        {live
          ? <Loader2 className="size-3 shrink-0 animate-spin text-agent" strokeWidth={2.2} aria-hidden />
          : <span className="shrink-0 text-faint transition-transform group-open:rotate-90">›</span>}
        <span className="shrink-0">
          {live && entries.length === 0 ? "正在思考" : `思考与工具调用（${entries.length}）`}
        </span>
        <span className="min-w-0 flex-1 truncate text-faint">{entryPreview(entries[lastIndex])}</span>
      </summary>
      <div className="mt-1.5 space-y-1.5 border-l-2 border-line pl-3">
        {entries.map((entry, index) => {
          if (entry.kind === "tool") return <ToolLine key={`t${entry.tool.toolCallId}-${index}`} tool={entry.tool} />;
          if (entry.kind === "thinking") {
            return <ThinkingBlock key={`k${index}`} text={entry.text} live={live && index === lastIndex} />;
          }
          return <TextBlock key={`x${index}`} text={entry.text} />;
        })}
        {live && entries.length === 0 && (
          <div className="flex items-center gap-2 text-xs italic text-muted">
            <Loader2 className="size-3 shrink-0 animate-spin text-agent" strokeWidth={2.2} aria-hidden />
            正在思考
          </div>
        )}
      </div>
    </details>
  );
}
