"use client";

import { Play } from "lucide-react";
import { GATE_META, MODULES, type NodeStatus, type PipelineNode } from "@/features/auto-research/research-pipeline";
import { EVIDENCE_SAMPLE, REVIEW_PANEL, TOPIC_GATES } from "@/features/auto-research/research-run";
import { cn } from "@/lib/utils";

interface NodeDetailProps {
  node: PipelineNode;
  status: NodeStatus;
  canEnter: boolean;
  onEnter: (nodeId: string) => void;
}

const SUPPORT_STYLE: Record<string, string> = {
  直接支持: "bg-success-soft text-success",
  部分支持: "bg-[#d97706]/10 text-[#d97706]",
  仅背景: "bg-chip text-muted",
  相互矛盾: "bg-danger-soft text-danger",
  无法核实: "bg-danger-soft text-danger",
};

/** 节点详情 —— 摘要 / 产物 / 特色可视化(三关卡·评审团·证据追踪)/ 中途进入 */
export function NodeDetail({ node, status, canEnter, onEnter }: NodeDetailProps) {
  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <span
            className="inline-block size-2.5 rounded-full"
            style={{ backgroundColor: MODULES[node.module].color }}
          />
          <p className="text-sm font-semibold text-ink">
            {node.index} {node.label}
          </p>
          <span className="text-[10px] text-faint">{MODULES[node.module].label}模块</span>
        </div>
        <p className="mt-2 text-xs leading-5 text-muted">{node.summary}</p>
      </div>

      {node.gate && (
        <div className="rounded-lg bg-panel px-3 py-2">
          <p className="text-[11px] font-medium text-ink-2">收尾关卡:{GATE_META[node.gate].label}</p>
          <p className="text-[10px] text-faint">{GATE_META[node.gate].hint}</p>
        </div>
      )}

      {/* ① 选题验证:三关卡评分 */}
      {node.id === "topic" && (
        <div className="space-y-2">
          <p className="text-[11px] font-medium text-ink-2">研究空白三关卡</p>
          {TOPIC_GATES.map((g) => (
            <div key={g.label}>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-ink-2">{g.label}</span>
                <span className={cn("font-semibold", g.score >= 3 ? "text-success" : "text-danger")}>
                  {g.score} / 5
                </span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-chip">
                <div
                  className={cn("h-full rounded-full", g.score >= 4 ? "bg-success" : "bg-[#d97706]")}
                  style={{ width: `${(g.score / 5) * 100}%` }}
                />
              </div>
              <p className="mt-0.5 text-[10px] text-faint">{g.note}</p>
            </div>
          ))}
          <p className="rounded-lg bg-primary-soft px-2.5 py-1.5 text-[11px] text-primary">
            结论:有条件可以做(任一关卡 &lt;3 即不建议做,未评估项则为有条件)
          </p>
        </div>
      )}

      {/* ⑨ 模拟评审:五人评审团 */}
      {node.id === "review" && (
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium text-ink-2">五人评审团</p>
          {REVIEW_PANEL.map((r) => (
            <div key={r.role} className="flex items-center justify-between rounded-lg bg-panel px-2.5 py-1.5">
              <span className="text-[11px] text-ink-2">{r.role}</span>
              <span
                className={cn(
                  "rounded-md px-1.5 py-0.5 text-[10px] font-semibold",
                  r.tone === "ok" && "bg-success-soft text-success",
                  r.tone === "warn" && "bg-[#d97706]/10 text-[#d97706]",
                  r.tone === "da" && "bg-brand-violet/10 text-brand-violet",
                )}
              >
                {r.tone === "da" ? "反驳 4/5 · 部分让步" : `${r.score} / 10`}
              </span>
            </div>
          ))}
          <p className="text-[10px] text-faint">反谄媚机制:Devil&apos;s Advocate 仅在反驳评分 ≥4/5 时让步</p>
        </div>
      )}

      {/* ⑤/⑧ 证据与论断追踪 */}
      {(node.id === "survey" || node.id === "writing") && (
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium text-ink-2">论断 → 证据追踪</p>
          {EVIDENCE_SAMPLE.map((e) => (
            <div key={e.claim} className="rounded-lg bg-panel px-2.5 py-2">
              <div className="flex items-start justify-between gap-2">
                <p className="text-[11px] leading-4.5 text-ink-2">{e.claim}</p>
                <span className={cn("shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-medium", SUPPORT_STYLE[e.support])}>
                  {e.support}
                </span>
              </div>
              <p className="mt-1 text-[10px] text-faint">{e.refs.join(" · ")}</p>
            </div>
          ))}
        </div>
      )}

      <div>
        <p className="text-[11px] font-medium text-ink-2">交付物</p>
        <ul className="mt-1 space-y-1">
          {node.deliverables.map((d) => (
            <li key={d} className="text-[11px] text-muted">
              · {d}
            </li>
          ))}
        </ul>
      </div>

      {canEnter && (
        <button
          type="button"
          onClick={() => onEnter(node.id)}
          className="flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-dashed border-primary px-3 py-2 text-xs font-medium text-primary transition-colors hover:bg-primary-soft"
        >
          <Play className="size-3.5" />
          从这里开始(上传材料后直接进入此阶段)
        </button>
      )}
      {status === "skipped" && (
        <p className="text-center text-[10px] text-faint">本次运行已跳过该节点</p>
      )}
    </div>
  );
}
