"use client";

import { useState } from "react";
import { FileText } from "lucide-react";
import { NODE_MAP } from "@/features/auto-research/research-pipeline";
import { FAILURE_MODES, PASSPORT_LEVELS, type Artifact } from "@/features/auto-research/research-run";
import { cn } from "@/lib/utils";

type Tab = "artifacts" | "passport" | "integrity";

const KIND_BADGE: Record<Artifact["kind"], string> = {
  json: "bg-primary-soft text-primary",
  xlsx: "bg-success-soft text-success",
  md: "bg-chip text-muted",
  docx: "bg-primary-soft text-primary",
  pdf: "bg-danger-soft text-danger",
  tex: "bg-brand-violet/10 text-brand-violet",
  pptx: "bg-[#d97706]/10 text-[#d97706]",
  script: "bg-chip text-muted",
  figure: "bg-brand-cyan/10 text-brand-cyan",
};

/** 产物档案 —— 交付物 / 材料护照 / 诚信报告 */
export function ArtifactsPanel({
  artifacts,
  integrityPassed,
}: {
  artifacts: Artifact[];
  integrityPassed: { g1: boolean; g2: boolean };
}) {
  const [tab, setTab] = useState<Tab>("artifacts");

  return (
    <div>
      <div className="flex gap-1 rounded-xl bg-chip p-1">
        {(
          [
            ["artifacts", "交付物"],
            ["passport", "材料护照"],
            ["integrity", "诚信报告"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={cn(
              "flex-1 cursor-pointer rounded-lg px-2 py-1.5 text-xs font-medium transition-colors",
              tab === key ? "bg-card text-ink shadow-card" : "text-muted hover:text-ink-2",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="scrollbar-subtle mt-3 h-72 overflow-y-auto pr-1">
        {tab === "artifacts" &&
          (artifacts.length === 0 ? (
            <p className="flex h-full items-center justify-center text-xs text-faint">
              运行后,各节点交付物会按阶段归档在这里
            </p>
          ) : (
            <ul className="space-y-1.5">
              {artifacts.map((a) => {
                const node = NODE_MAP.get(a.nodeId);
                return (
                  <li
                    key={a.id}
                    className="flex items-center gap-2.5 rounded-xl border border-line bg-card px-3 py-2"
                  >
                    <FileText className="size-4 shrink-0 text-faint" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium text-ink-2">{a.name}</p>
                      <p className="text-[10px] text-faint">
                        {node ? `${node.index}${node.label}` : ""} · {a.version} · #{a.hash}
                      </p>
                    </div>
                    <span className={cn("shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase", KIND_BADGE[a.kind])}>
                      {a.kind}
                    </span>
                  </li>
                );
              })}
            </ul>
          ))}

        {tab === "passport" && (
          <div className="space-y-2">
            <p className="text-[10px] text-faint">
              数据访问级别随流水线推进单向跃迁,下游只消费更高级别的材料
            </p>
            {PASSPORT_LEVELS.map((p, i) => {
              const active =
                (p.level === "raw" && !integrityPassed.g1) ||
                (p.level === "redacted" && !integrityPassed.g1) ||
                (p.level === "verified_only" && integrityPassed.g1);
              return (
                <div
                  key={p.level}
                  className={cn(
                    "rounded-xl border px-3 py-2.5",
                    active && p.level === "verified_only"
                      ? "border-success bg-success-soft/40"
                      : "border-line bg-card",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-ink-2">
                      L{i} {p.label}
                    </p>
                    <span className="text-[10px] text-faint">{p.until}</span>
                  </div>
                  <p className="mt-0.5 text-[10px] text-muted">{p.desc}</p>
                </div>
              );
            })}
          </div>
        )}

        {tab === "integrity" &&
          (!integrityPassed.g1 ? (
            <p className="flex h-full items-center justify-center text-center text-xs text-faint">
              抵达 ✓G1 诚信核查门后,
              <br />
              7 类失败模式清单与引文核验结果显示在这里
            </p>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center justify-between rounded-xl bg-success-soft/50 px-3 py-2">
                <p className="text-xs font-semibold text-success">G1 通过 · 引文 112/112</p>
                <p className="text-[10px] text-faint">1 条部分支持已标注</p>
              </div>
              {integrityPassed.g2 && (
                <div className="flex items-center justify-between rounded-xl bg-success-soft/50 px-3 py-2">
                  <p className="text-xs font-semibold text-success">G2 终审通过 · 引文 118/118</p>
                  <p className="text-[10px] text-faint">零容忍 · 残留 0</p>
                </div>
              )}
              <p className="pt-1 text-[11px] font-medium text-ink-2">7 类 AI 失败模式清单</p>
              {FAILURE_MODES.map((m) => (
                <div key={m.id} className="flex items-center justify-between rounded-lg bg-panel px-2.5 py-1.5">
                  <span className="text-[11px] text-ink-2">
                    {m.id} {m.label}
                  </span>
                  <span
                    className={cn(
                      "rounded-md px-1.5 py-0.5 text-[10px] font-semibold",
                      m.status === "CLEAR" ? "bg-success-soft text-success" : "bg-danger-soft text-danger",
                    )}
                  >
                    {m.status}
                  </span>
                </div>
              ))}
            </div>
          ))}
      </div>
    </div>
  );
}
