"use client";

import { Suspense, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type { PaperGraph } from "@/types";
import { concentricLayout, strataLayout } from "@/lib/graph-layout";
import { GraphCanvas } from "./graph-canvas";
import { RelatedPaperList } from "./related-paper-list";
import { NodeAbstractCard } from "./node-abstract-card";

interface GraphPageLayoutProps {
  graph: PaperGraph;
  mode: "concentric" | "strata";
  backHref: string;
  backLabel: string;
  title: string;
  headerExtra?: ReactNode;
}

/** 知识图谱三栏骨架 —— 顶栏 / 左关联论文 / 中图谱 / 右摘要(小屏堆叠,图谱优先) */
export function GraphPageLayout({
  graph,
  mode,
  backHref,
  backLabel,
  title,
  headerExtra,
}: GraphPageLayoutProps) {
  const [selectedId, setSelectedId] = useState(graph.origin.id);
  const layout = useMemo(
    () =>
      mode === "concentric" ? concentricLayout(graph) : strataLayout(graph),
    [graph, mode],
  );
  const selected =
    [graph.origin, ...graph.nodes].find((n) => n.id === selectedId) ??
    graph.origin;

  return (
    <>
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-card px-5">
        <Link
          href={backHref}
          className="flex shrink-0 items-center gap-1.5 text-[13px] text-muted transition-colors hover:text-primary"
        >
          <ArrowLeft className="size-4" />
          {backLabel}
        </Link>
        <h1 className="min-w-0 flex-1 truncate text-center text-[15px] font-semibold text-ink">
          {title}
        </h1>
        <div className="flex shrink-0 items-center">{headerExtra}</div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
        <aside className="order-2 w-full shrink-0 border-line bg-card p-4 lg:order-1 lg:w-72 lg:overflow-y-auto lg:border-r">
          <RelatedPaperList
            graph={graph}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </aside>
        <main className="order-1 min-w-0 flex-1 p-6 lg:order-2 lg:overflow-y-auto">
          <GraphCanvas
            graph={graph}
            layout={layout}
            variant={mode}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </main>
        <aside className="order-3 w-full shrink-0 border-line bg-card p-5 lg:w-80 lg:overflow-y-auto lg:border-l">
          <Suspense fallback={<p className="text-xs text-faint">正在加载论文信息…</p>}>
            <NodeAbstractCard node={selected} />
          </Suspense>
        </aside>
      </div>
    </>
  );
}
