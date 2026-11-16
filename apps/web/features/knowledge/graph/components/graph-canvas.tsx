"use client";

import { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import { RGProvider, RelationGraph } from "@relation-graph/react";
import type { RGNodeSlotProps, RGOptions, RelationGraphInstance } from "@relation-graph/react";
import "@relation-graph/react/style.css";
import type { KnowledgeGraph } from "@/clients/knowledge";
import { Minus, Plus, Scan, RotateCcw } from "lucide-react";
import { kindLabel, nodeColor } from "../lib/graph-utils";
import type { NodePositions } from "../lib/layouts";
import { fitGraphViewBox } from "../lib/graph-viewport";
import { toRelationGraphData } from "../lib/relation-graph-adapter";

interface GraphCanvasProps {
  graph: KnowledgeGraph;
  positions: NodePositions;
  selectedId: string | null;
  hoveredId: string | null;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
  onCanvasClick: () => void;
}

const GRAPH_OPTIONS: RGOptions = {
  showToolBar: false,
  backgroundColor: "transparent",
  wheelEventAction: "zoom",
  dragEventAction: "move",
  disableDragNode: false,
  defaultNodeShape: 0,
  defaultLineColor: "#94a3b8",
  defaultExpandHolderPosition: "hide",
  layout: { layoutName: "fixed" },
};

function shortenLabel(label: string): string {
  return label.length > 18 ? `${label.slice(0, 17)}…` : label;
}

const HoveredNodeContext = createContext<string | null>(null);

type GraphCallbacks = Pick<GraphCanvasProps, "onSelect" | "onHover" | "onCanvasClick">;
type StableGraphProps = Pick<GraphCanvasProps, "graph" | "positions"> & {
  callbacksRef: RefObject<GraphCallbacks>;
  instanceRef: RefObject<RelationGraphInstance | null>;
  selectedRef: RefObject<string | null>;
};

function GraphSurface({
  graph,
  positions,
  callbacksRef,
  instanceRef,
  selectedRef,
}: StableGraphProps) {
  const hoveredId = useContext(HoveredNodeContext);
  const [instance, setInstance] = useState<RelationGraphInstance | null>(null);
  const data = useMemo(() => toRelationGraphData(graph, positions), [graph, positions]);

  useEffect(() => {
    if (!instance) return;
    let cancelled = false;
    void instance.setJsonData(data).then(() => {
      if (cancelled) return;
      const selectedId = selectedRef.current;
      if (selectedId && graph.nodes.some((node) => node.id === selectedId)) {
        instance.setCheckedNode(selectedId);
      }
      instance.moveToCenter();
      instance.zoomToFit();
    });
    return () => { cancelled = true; };
  }, [instance, data, graph, selectedRef]);

  const nodeSlot = useCallback(({ node, checked }: RGNodeSlotProps) => {
    const dimmed = hoveredId !== null && node.id !== hoveredId;
    return (
      <span
        title={node.text}
        onMouseEnter={() => callbacksRef.current.onHover(node.id)}
        onMouseLeave={() => callbacksRef.current.onHover(null)}
        className="flex h-full w-full items-center justify-center rounded-full text-center text-[10px] font-semibold leading-tight text-white transition-opacity"
        style={{ opacity: dimmed ? 0.55 : 1, outline: checked ? "2px dashed var(--color-primary)" : undefined, outlineOffset: checked ? 5 : undefined }}
      >
        <span className="max-w-[58px] break-words px-1">{shortenLabel(node.text ?? node.id)}</span>
      </span>
    );
  }, [hoveredId, callbacksRef]);

  const fit = () => {
    const bounds = fitGraphViewBox(positions);
    if (!Number.isFinite(bounds.width) || !Number.isFinite(bounds.height)) return;
    instance?.moveToCenter();
    instance?.zoomToFit();
  };

  return (
    <div
      className="relative min-h-0 flex-1 overflow-hidden rounded-xl border border-line/70 bg-card/30"
      role="img"
      aria-label="论文关系图谱"
      onWheel={(event) => event.stopPropagation()}
      onPointerMove={(event) => { if (event.target === event.currentTarget) callbacksRef.current.onHover(null); }}
    >
      <RelationGraph
        options={GRAPH_OPTIONS}
        onReady={(readyInstance) => {
          instanceRef.current = readyInstance;
          setInstance(readyInstance);
        }}
        onNodeClick={(node) => callbacksRef.current.onSelect(node.id)}
        onCanvasClick={() => callbacksRef.current.onCanvasClick()}
        nodeSlot={nodeSlot}
      />
      <div className="absolute right-3 top-3 z-10 flex items-center gap-1 rounded-lg border border-line/70 bg-card/95 p-1 shadow-card backdrop-blur">
        <button type="button" aria-label="缩小图谱" title="缩小图谱" onClick={() => instance?.zoom(-15)} className="flex size-7 items-center justify-center rounded-md text-muted hover:bg-panel hover:text-ink"><Minus className="size-3.5" /></button>
        <button type="button" aria-label="放大图谱" title="放大图谱" onClick={() => instance?.zoom(15)} className="flex size-7 items-center justify-center rounded-md text-muted hover:bg-panel hover:text-ink"><Plus className="size-3.5" /></button>
        <button type="button" aria-label="适应视图" title="适应视图" onClick={fit} className="ml-1 flex h-7 items-center gap-1 rounded-md px-2 text-[10px] text-muted hover:bg-panel hover:text-ink"><Scan className="size-3.5" />适应视图</button>
        <button type="button" aria-label="重置视图" title="重置视图" onClick={() => { instance?.setZoom(100); instance?.moveToCenter(); }} className="flex size-7 items-center justify-center rounded-md text-muted hover:bg-panel hover:text-ink"><RotateCcw className="size-3.5" /></button>
      </div>
    </div>
  );
}

// The installed RGProvider creates a graph instance when it renders. Keep this
// subtree mounted across hover/selection updates; the workbench remounts the
// canvas with a new key when graph data, layout or filters change.
const StableRelationGraph = memo(function StableRelationGraph(props: StableGraphProps) {
  return <RGProvider><GraphSurface {...props} /></RGProvider>;
});

export function GraphCanvas(props: GraphCanvasProps) {
  const callbacksRef = useRef<GraphCallbacks>({
    onSelect: props.onSelect,
    onHover: props.onHover,
    onCanvasClick: props.onCanvasClick,
  });
  const instanceRef = useRef<RelationGraphInstance | null>(null);
  const selectedRef = useRef(props.selectedId);

  useEffect(() => {
    callbacksRef.current = {
      onSelect: props.onSelect,
      onHover: props.onHover,
      onCanvasClick: props.onCanvasClick,
    };
  }, [props.onSelect, props.onHover, props.onCanvasClick]);

  useEffect(() => {
    selectedRef.current = props.selectedId;
    if (props.selectedId && props.graph.nodes.some((node) => node.id === props.selectedId)) {
      instanceRef.current?.setCheckedNode(props.selectedId);
    }
  }, [props.selectedId, props.graph]);

  const kinds = Array.from(new Set(props.graph.nodes.map((node) => node.kind)));
  return (
    <div className="flex h-full min-h-0 flex-col">
      <HoveredNodeContext.Provider value={props.hoveredId}>
        <StableRelationGraph
          graph={props.graph}
          positions={props.positions}
          callbacksRef={callbacksRef}
          instanceRef={instanceRef}
          selectedRef={selectedRef}
        />
      </HoveredNodeContext.Provider>
      <div className="mt-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 px-2 text-[11px] text-faint">
        {kinds.map((kind) => (
          <span key={kind} className="flex items-center gap-1.5"><span className="size-2.5 rounded-full" style={{ backgroundColor: nodeColor(kind) }} />{kindLabel(kind)}</span>
        ))}
        <span className="flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 bg-[#8492a6]" />箭头 = 引用方向</span>
      </div>
    </div>
  );
}
