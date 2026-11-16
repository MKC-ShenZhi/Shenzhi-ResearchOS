"use client";

import { motion } from "framer-motion";
import {
  MODULES,
  NODE_H,
  NODE_W,
  NODE_MAP,
  PIPELINE_EDGES,
  PIPELINE_NODES,
  VIEW_H,
  VIEW_W,
  type NodeStatus,
  type PipelineNode,
} from "@/features/auto-research/research-pipeline";

interface FlowCanvasProps {
  status: Record<string, NodeStatus>;
  /** 运行中节点的当前动作副标题 */
  currentAction: Record<string, string>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  reviewRound: number;
  artifactCount: Record<string, number>;
}

/** 状态副标题文案 */
function statusLine(
  s: NodeStatus,
  node: PipelineNode,
  currentAction: Record<string, string>,
  artifactCount: Record<string, number>,
): string {
  switch (s) {
    case "running":
      return currentAction[node.id] ?? "执行中…";
    case "waiting_user":
      return "等待你的决策";
    case "done":
      return `已交付 ${artifactCount[node.id] ?? node.deliverables.length} 项产物`;
    case "blocked":
      return "门禁未通过";
    case "stalled":
      return "停滞,转向中";
    case "skipped":
      return "已跳过";
    case "ready":
      return "可从这里进入";
    default:
      return "未到达";
  }
}

/** 节点描边/填充按状态 */
function nodePaint(s: NodeStatus, moduleColor: string, selected: boolean) {
  const base = {
    idle: { fill: "var(--color-card)", stroke: "var(--color-line)", dash: "6 4", width: 1.5, textClass: "fill-faint" },
    ready: { fill: "var(--color-card)", stroke: "var(--color-primary)", dash: "6 4", width: 2, textClass: "fill-ink-2" },
    running: { fill: "var(--color-primary-soft)", stroke: "var(--color-primary)", dash: undefined, width: 2.5, textClass: "fill-ink" },
    waiting_user: { fill: "var(--color-card)", stroke: "#d97706", dash: undefined, width: 3, textClass: "fill-ink" },
    blocked: { fill: "var(--color-danger-soft)", stroke: "var(--color-danger)", dash: undefined, width: 2.5, textClass: "fill-ink" },
    done: { fill: "var(--color-card)", stroke: moduleColor, dash: undefined, width: 2, textClass: "fill-ink-2" },
    stalled: { fill: "var(--color-card)", stroke: "#d97706", dash: "3 3", width: 2.5, textClass: "fill-ink-2" },
    skipped: { fill: "var(--color-panel)", stroke: "var(--color-line)", dash: "4 4", width: 1.5, textClass: "fill-faint" },
  }[s];
  return { ...base, width: selected ? base.width + 1 : base.width };
}

/** 六边形顶点(诚信门) */
function hexPoints(x: number, y: number, w: number, h: number): string {
  const hw = w / 2;
  const hh = h / 2;
  const c = 14;
  return [
    [x - hw + c, y - hh],
    [x + hw - c, y - hh],
    [x + hw, y],
    [x + hw - c, y + hh],
    [x - hw + c, y + hh],
    [x - hw, y],
  ]
    .map((p) => p.join(","))
    .join(" ");
}

/** 关卡角标:决策=红菱形 / 确认=橙六边 / 机器=灰方块 */
function GateBadge({ node }: { node: PipelineNode }) {
  if (!node.gate) return null;
  const cx = node.x + NODE_W / 2 - 6;
  const cy = node.y - NODE_H / 2 + 2;
  if (node.gate === "decision")
    return (
      <polygon
        points={`${cx},${cy - 7} ${cx + 7},${cy} ${cx},${cy + 7} ${cx - 7},${cy}`}
        fill="var(--color-card)"
        stroke="#dc2626"
        strokeWidth={2}
      />
    );
  if (node.gate === "confirm")
    return (
      <polygon
        points={hexPoints(cx, cy, 14, 12)}
        fill="var(--color-card)"
        stroke="#d97706"
        strokeWidth={2}
      />
    );
  return (
    <rect
      x={cx - 6}
      y={cy - 6}
      width={12}
      height={12}
      rx={2}
      fill="var(--color-card)"
      stroke="var(--color-faint)"
      strokeWidth={2}
    />
  );
}

/** 流程画布 —— 纯 SVG,节点状态机 + 关卡角标 + 评审回路 */
export function FlowCanvas({
  status,
  currentAction,
  selectedId,
  onSelect,
  reviewRound,
  artifactCount,
}: FlowCanvasProps) {
  return (
    <div>
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className="h-auto w-full select-none"
        role="img"
        aria-label="Auto Research 流水线"
      >
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--color-faint)" />
          </marker>
          <marker id="arrow-active" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--color-primary)" />
          </marker>
        </defs>

        {/* 边(全部轴对齐);标签收集后最后绘制,避免被节点压住 */}
        {PIPELINE_EDGES.map((e) => {
          const a = NODE_MAP.get(e.from);
          const b = NODE_MAP.get(e.to);
          if (!a || !b) return null;
          const off = e.offset ?? 0;
          let x1: number, y1: number, x2: number, y2: number;
          if (a.y === b.y) {
            // 水平:右缘 → 左缘(或反向)
            const dir = b.x > a.x ? 1 : -1;
            x1 = a.x + (dir * NODE_W) / 2;
            y1 = a.y;
            x2 = b.x - (dir * NODE_W) / 2;
            y2 = b.y;
          } else {
            // 垂直:底缘 → 顶缘(或反向),offset 用于回路双线
            const dir = b.y > a.y ? 1 : -1;
            x1 = a.x + off;
            y1 = a.y + (dir * NODE_H) / 2;
            x2 = b.x + off;
            y2 = b.y - (dir * NODE_H) / 2;
          }
          const aActive = status[e.from] === "running" || status[e.from] === "waiting_user";
          const traversed = status[e.from] === "done" && status[e.to] !== "idle";
          const stroke = aActive || traversed ? "var(--color-primary)" : "var(--color-line)";
          return (
            <line
              key={`${e.from}-${e.to}-${off}`}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={stroke}
              strokeWidth={aActive ? 2 : 1.5}
              strokeDasharray={e.dashed ? "5 4" : undefined}
              markerEnd={`url(#${aActive || traversed ? "arrow-active" : "arrow"})`}
              opacity={status[e.from] === "skipped" ? 0.3 : 1}
            />
          );
        })}

        {/* 节点 */}
        {PIPELINE_NODES.map((node, i) => {
          const s = status[node.id] ?? "idle";
          const moduleColor = MODULES[node.module].color;
          const selected = node.id === selectedId;
          const paint = nodePaint(s, moduleColor, selected);
          const running = s === "running";
          const waiting = s === "waiting_user";
          return (
            <motion.g
              key={node.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03, duration: 0.3 }}
              style={{ cursor: "pointer" }}
              onClick={() => onSelect(node.id)}
            >
              {/* 运行/等待的呼吸光环 */}
              {(running || waiting) && (
                <motion.rect
                  x={node.x - NODE_W / 2 - 5}
                  y={node.y - NODE_H / 2 - 5}
                  width={NODE_W + 10}
                  height={NODE_H + 10}
                  rx={14}
                  fill="none"
                  stroke={waiting ? "#d97706" : "var(--color-primary)"}
                  animate={{ opacity: [0.7, 0.15, 0.7] }}
                  transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
                  strokeWidth={2}
                />
              )}

              {node.shape === "integrity" ? (
                <polygon
                  points={hexPoints(node.x, node.y, NODE_W + 8, NODE_H)}
                  fill={paint.fill}
                  stroke={paint.stroke}
                  strokeWidth={paint.width}
                  strokeDasharray={paint.dash}
                />
              ) : (
                <rect
                  x={node.x - NODE_W / 2}
                  y={node.y - NODE_H / 2}
                  width={NODE_W}
                  height={NODE_H}
                  rx={12}
                  fill={paint.fill}
                  stroke={paint.stroke}
                  strokeWidth={paint.width}
                  strokeDasharray={paint.dash}
                />
              )}

              {/* 模块色条 */}
              <rect
                x={node.x - NODE_W / 2}
                y={node.y - NODE_H / 2 + 8}
                width={4}
                height={NODE_H - 16}
                rx={2}
                fill={moduleColor}
                opacity={s === "idle" || s === "skipped" ? 0.35 : 0.9}
              />

              {/* 完成勾选 */}
              {s === "done" && (
                <g>
                  <circle cx={node.x - NODE_W / 2 + 2} cy={node.y - NODE_H / 2 + 2} r={8} fill="var(--color-success)" />
                  <text x={node.x - NODE_W / 2 + 2} y={node.y - NODE_H / 2 + 5.5} textAnchor="middle" fontSize={10} fill="#fff">
                    ✓
                  </text>
                </g>
              )}

              <text
                x={node.x + 4}
                y={node.y + (node.shape === "integrity" ? 1 : -2)}
                textAnchor="middle"
                fontSize={13}
                fontWeight={600}
                className={paint.textClass}
                style={s === "skipped" ? { textDecoration: "line-through" } : undefined}
              >
                {node.index} {node.label}
              </text>
              <text x={node.x + 4} y={node.y + 15} textAnchor="middle" fontSize={9.5} className="fill-faint">
                {MODULES[node.module].label}
              </text>

              <GateBadge node={node} />

              {/* 状态副标题 */}
              <text
                x={node.x}
                y={node.y + NODE_H / 2 + 16}
                textAnchor="middle"
                fontSize={10}
                className={waiting ? "fill-[#d97706]" : running ? "fill-primary" : "fill-faint"}
              >
                {statusLine(s, node, currentAction, artifactCount).slice(0, 16)}
              </text>
            </motion.g>
          );
        })}
        {/* 边标签(最后绘制,浮于节点之上;垂直回路双线分置左右) */}
        {PIPELINE_EDGES.map((e) => {
          const a = NODE_MAP.get(e.from);
          const b = NODE_MAP.get(e.to);
          if (!a || !b || !e.label) return null;
          const off = e.offset ?? 0;
          const vertical = a.y !== b.y;
          const text =
            e.dashed && reviewRound > 0 ? `复审 · 第 ${reviewRound} 轮/上限 2` : e.label;
          const x = vertical ? a.x + off + (off < 0 ? -8 : 8) : (a.x + b.x) / 2;
          const y = vertical ? (a.y + b.y) / 2 + 4 : a.y - 8;
          return (
            <text
              key={`label-${e.from}-${e.to}-${off}`}
              x={x}
              y={y}
              textAnchor={vertical ? (off < 0 ? "end" : "start") : "middle"}
              fontSize={10}
              className="fill-faint"
            >
              {text}
            </text>
          );
        })}
      </svg>

      {/* 图例 */}
      <div className="mt-2 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-faint">
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-full border-2 border-primary" /> 运行中
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rotate-45 border-2 border-[#dc2626]" /> 决策关卡
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 border-2 border-[#d97706]" style={{ clipPath: "polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%)" }} /> 诚信门
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-[2px] border-2 border-faint" /> 机器门
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-full bg-success" /> 已交付
        </span>
        <span>点击节点查看详情与「从这里开始」</span>
      </div>
    </div>
  );
}
