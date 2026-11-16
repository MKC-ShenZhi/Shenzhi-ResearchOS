"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  Building2,
  Network,
  Search,
  Users,
} from "lucide-react";
import { scholars } from "@/features/knowledge/data-scholars";
import { cn } from "@/lib/utils";

const positions: Record<string, { x: number; y: number }> = {
  "kaiming-he": { x: 370, y: 250 },
  "geoffrey-hinton": { x: 185, y: 125 },
  "yoshua-bengio": { x: 565, y: 115 },
  "fei-fei-li": { x: 620, y: 340 },
  "pieter-abbeel": { x: 355, y: 430 },
  "ilya-sutskever": { x: 125, y: 345 },
};

const edges = [
  { source: "kaiming-he", target: "geoffrey-hinton", label: "视觉表征", strength: 3 },
  { source: "kaiming-he", target: "fei-fei-li", label: "计算机视觉", strength: 4 },
  { source: "kaiming-he", target: "pieter-abbeel", label: "具身智能", strength: 2 },
  { source: "geoffrey-hinton", target: "yoshua-bengio", label: "深度学习", strength: 5 },
  { source: "geoffrey-hinton", target: "ilya-sutskever", label: "神经网络", strength: 4 },
  { source: "yoshua-bengio", target: "ilya-sutskever", label: "生成模型", strength: 3 },
  { source: "yoshua-bengio", target: "pieter-abbeel", label: "强化学习", strength: 2 },
  { source: "fei-fei-li", target: "pieter-abbeel", label: "机器人学习", strength: 4 },
];

const directions = ["全部", "计算机视觉", "机器学习", "强化学习", "机器人学"];

export function ScholarNetwork() {
  const [selectedId, setSelectedId] = useState("kaiming-he");
  const [direction, setDirection] = useState("全部");
  const [query, setQuery] = useState("");

  const selected = scholars.find((scholar) => scholar.id === selectedId) ?? scholars[0];
  const visibleIds = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return new Set(
      scholars
        .filter((scholar) => direction === "全部" || scholar.tags.includes(direction))
        .filter((scholar) => !keyword || `${scholar.nameCn} ${scholar.nameEn} ${scholar.affiliation}`.toLowerCase().includes(keyword))
        .map((scholar) => scholar.id),
    );
  }, [direction, query]);

  const connected = edges.filter((edge) => edge.source === selected.id || edge.target === selected.id);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="flex flex-wrap items-center gap-4 border-b border-line bg-card px-6 py-4 lg:px-8">
        <Link href="/knowledge/scholars" className="flex size-9 items-center justify-center rounded-lg border border-line text-muted hover:bg-chip hover:text-primary">
          <ArrowLeft className="size-4" />
        </Link>
        <span className="flex size-10 items-center justify-center rounded-xl bg-primary-soft"><Network className="size-5 text-primary" /></span>
        <div>
          <h1 className="text-lg font-bold text-ink">学者合作网络</h1>
          <p className="text-xs text-faint">基于共同研究方向与合作脉络的交互示例</p>
        </div>
        <div className="ml-auto flex gap-2 text-xs">
          <span className="rounded-full bg-panel px-3 py-1.5 text-muted"><b className="text-ink">{scholars.length}</b> 位学者</span>
          <span className="rounded-full bg-panel px-3 py-1.5 text-muted"><b className="text-ink">{edges.length}</b> 条关系</span>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[230px_minmax(0,1fr)_300px]">
        <aside className="border-r border-line bg-card p-5">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索学者…" className="h-10 w-full rounded-xl border border-line bg-panel pl-9 pr-3 text-xs text-ink outline-none placeholder:text-faint focus:border-primary/50" />
          </div>
          <p className="mt-6 text-[11px] font-medium tracking-wide text-faint">研究方向</p>
          <div className="mt-2 space-y-1">
            {directions.map((item) => (
              <button key={item} type="button" onClick={() => setDirection(item)} className={cn("flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs", direction === item ? "bg-primary-soft font-medium text-primary" : "text-muted hover:bg-panel")}>
                {item}<span>{item === "全部" ? scholars.length : scholars.filter((scholar) => scholar.tags.includes(item)).length}</span>
              </button>
            ))}
          </div>
        </aside>

        <main className="relative min-h-[620px] overflow-hidden bg-[radial-gradient(circle_at_center,var(--color-card)_0,var(--color-background)_68%)] p-5">
          <div className="absolute left-5 top-5 z-10 rounded-xl bg-card/90 px-4 py-3 shadow-card backdrop-blur">
            <p className="text-xs font-semibold text-ink">AI 学者合作网络 · 示例</p>
            <p className="mt-0.5 text-[10px] text-faint">点击节点探索关系</p>
          </div>
          <svg viewBox="0 0 740 540" className="h-full min-h-[580px] w-full" aria-label="学者合作关系图">
            <defs>
              <filter id="node-shadow"><feDropShadow dx="0" dy="4" stdDeviation="5" floodOpacity="0.14" /></filter>
            </defs>
            {edges.map((edge) => {
              const source = positions[edge.source];
              const target = positions[edge.target];
              const visible = visibleIds.has(edge.source) && visibleIds.has(edge.target);
              const active = edge.source === selected.id || edge.target === selected.id;
              return (
                <g key={`${edge.source}-${edge.target}`} className={visible ? "opacity-100" : "opacity-10"}>
                  <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke={active ? "var(--color-primary)" : "var(--color-line)"} strokeWidth={active ? edge.strength : Math.max(1.5, edge.strength / 1.6)} />
                  {active && <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 7} textAnchor="middle" fill="var(--color-muted)" fontSize="10">{edge.label}</text>}
                </g>
              );
            })}
            {scholars.map((scholar) => {
              const position = positions[scholar.id];
              const visible = visibleIds.has(scholar.id);
              const active = scholar.id === selected.id;
              return (
                <g key={scholar.id} onClick={() => visible && setSelectedId(scholar.id)} className={cn("cursor-pointer transition-opacity", visible ? "opacity-100" : "pointer-events-none opacity-15")} role="button" tabIndex={visible ? 0 : -1}>
                  {active && <circle cx={position.x} cy={position.y} r="48" fill="none" stroke="var(--color-primary)" strokeWidth="2" strokeDasharray="5 5" opacity="0.45" />}
                  <circle cx={position.x} cy={position.y} r={active ? 35 : 30} fill={scholar.avatarColor} stroke="var(--color-card)" strokeWidth="5" filter="url(#node-shadow)" />
                  <text x={position.x} y={position.y + 5} textAnchor="middle" fill="white" fontSize="14" fontWeight="700">{scholar.initials}</text>
                  <text x={position.x} y={position.y + 51} textAnchor="middle" fill="var(--color-ink)" fontSize="12" fontWeight="600">{scholar.nameCn}</text>
                  <text x={position.x} y={position.y + 67} textAnchor="middle" fill="var(--color-faint)" fontSize="9">h-index {scholar.hIndex}</text>
                </g>
              );
            })}
          </svg>
        </main>

        <aside className="border-l border-line bg-card p-5">
          <div className="flex items-center gap-3">
            <span className="flex size-12 items-center justify-center rounded-full text-sm font-bold text-white" style={{ backgroundColor: selected.avatarColor }}>{selected.initials}</span>
            <div className="min-w-0"><h2 className="truncate text-sm font-bold text-ink">{selected.nameCn}</h2><p className="truncate text-xs text-faint">{selected.nameEn}</p></div>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-muted">{selected.bio}</p>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <div className="rounded-xl bg-panel p-3"><p className="text-lg font-bold text-ink">{selected.citations}</p><p className="text-[10px] text-faint">总引用</p></div>
            <div className="rounded-xl bg-panel p-3"><p className="text-lg font-bold text-ink">{selected.hIndex}</p><p className="text-[10px] text-faint">h-index</p></div>
          </div>
          <div className="mt-5 space-y-3 text-xs">
            <p className="flex items-start gap-2 text-muted"><Building2 className="mt-0.5 size-4 shrink-0 text-faint" />{selected.affiliation}</p>
            <p className="flex items-center gap-2 text-muted"><Users className="size-4 text-faint" />{connected.length} 条示例关联</p>
            <p className="flex items-center gap-2 text-muted"><BookOpen className="size-4 text-faint" />研究方向：{selected.tags.slice(0, 2).join("、")}</p>
          </div>
          <div className="mt-5 flex flex-wrap gap-1.5">{selected.tags.map((tag) => <span key={tag} className="rounded-md bg-chip px-2 py-1 text-[10px] text-muted">{tag}</span>)}</div>
          <Link href={`/scholars/${selected.id}`} className="mt-6 flex h-10 w-full items-center justify-center rounded-xl bg-primary text-xs font-medium text-white hover:bg-primary-deep">查看完整学者画像</Link>
          <div className="mt-6 border-t border-line pt-4">
            <p className="text-[11px] font-semibold text-ink-2">当前关联</p>
            <div className="mt-2 space-y-2">
              {connected.map((edge) => {
                const otherId = edge.source === selected.id ? edge.target : edge.source;
                const other = scholars.find((scholar) => scholar.id === otherId)!;
                return <button key={otherId} type="button" onClick={() => setSelectedId(otherId)} className="flex w-full items-center gap-2 rounded-lg bg-panel px-2.5 py-2 text-left hover:bg-chip"><span className="size-2 rounded-full" style={{ backgroundColor: other.avatarColor }} /><span className="flex-1 truncate text-[11px] text-ink-2">{other.nameCn}</span><span className="text-[9px] text-faint">{edge.label}</span></button>;
              })}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
