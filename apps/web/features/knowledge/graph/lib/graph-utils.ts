/**
 * 知识底座图谱工具 —— CITES 方向推导、节点类型颜色、标签、关联论文。
 *
 * 统一语义（Contract）：
 *   sourceId 引用了 targetId
 *   sourceId === rootId → 当前论文引用的论文（References）
 *   targetId === rootId → 引用了当前论文的论文（Citations）
 */
import type {
  KnowledgeGraph,
  KnowledgeGraphDepth,
  KnowledgeGraphNode,
  KnowledgeRelatedPaper,
  KnowledgeRelationDirection,
} from "@/clients/knowledge";

/** 画布(viewBox)尺寸 */
export const VIEW_W = 1080;
export const VIEW_H = 780;
export const CENTER_X = VIEW_W / 2;
export const CENTER_Y = VIEW_H / 2 - 30;

/** 图谱节点类型颜色（未知类型使用默认灰色） */
export const KNOWLEDGE_NODE_COLORS: Record<string, string> = {
  Paper: "#174a7e",
  Author: "#059669",
  Method: "#7c3aed",
  Topic: "#d97706",
  Conference: "#0e7490",
  Funding: "#a16207",
  Institution: "#be185d",
  Venue: "#0f766e",
};

export const KNOWLEDGE_KIND_LABELS: Record<string, string> = {
  Paper: "论文",
  Author: "作者",
  Method: "方法",
  Topic: "主题",
  Conference: "会议",
  Funding: "基金",
  Institution: "机构",
  Venue: "会议",
};

export function nodeColor(kind: string): string {
  return KNOWLEDGE_NODE_COLORS[kind] ?? "#6b7280";
}

export function kindLabel(kind: string): string {
  return KNOWLEDGE_KIND_LABELS[kind] ?? kind;
}

export function nodeById(graph: KnowledgeGraph): Map<string, KnowledgeGraphNode> {
  return new Map(graph.nodes.map((node) => [node.id, node]));
}

/** 节点连边数量（图谱内度数） */
export function degreeOf(nodeId: string, edges: KnowledgeGraph["edges"]): number {
  let count = 0;
  for (const edge of edges) {
    if (edge.sourceId === nodeId || edge.targetId === nodeId) count += 1;
  }
  return count;
}

function isCitesBetween(edge: { sourceId: string; targetId: string; relation: string }, a: string, b: string): boolean {
  return edge.relation === "CITES" &&
    ((edge.sourceId === a && edge.targetId === b) || (edge.sourceId === b && edge.targetId === a));
}

/** 节点与 root 的引用方向（仅 Paper 且与 root 有 CITES 边时返回） */
export function relationDirectionOf(
  nodeId: string,
  graph: KnowledgeGraph,
): KnowledgeRelationDirection | null {
  if (nodeId === graph.rootId) return null;
  const edges = graph.edges.filter((edge) => isCitesBetween(edge, nodeId, graph.rootId));
  if (edges.length === 0) return null;
  const asReference = edges.some((edge) => edge.sourceId === graph.rootId && edge.targetId === nodeId);
  const asCitation = edges.some((edge) => edge.sourceId === nodeId && edge.targetId === graph.rootId);
  if (asReference && asCitation) return "both";
  return asReference ? "reference" : "citation";
}

const DIRECTION_ORDER: Record<KnowledgeRelationDirection, number> = { reference: 0, citation: 1, both: 2 };

/** 图谱方向筛选（列表 / 图谱统一） */
export type GraphDirectionFilter = "all" | KnowledgeRelationDirection;

export const MAX_VISIBLE_GRAPH_NODES = 50;

/** 从中心论文逐层选取节点，按类型轮流取样，避免高频类型占满画布。 */
export function limitGraphNodes(
  graph: KnowledgeGraph,
  depth: KnowledgeGraphDepth,
  nodesPerLayer: number,
): KnowledgeGraph {
  const nodeMap = nodeById(graph);
  if (!nodeMap.has(graph.rootId)) return { ...graph, nodes: [], edges: [] };

  const adjacency = new Map<string, Set<string>>();
  for (const edge of graph.edges) {
    if (!nodeMap.has(edge.sourceId) || !nodeMap.has(edge.targetId)) continue;
    if (!adjacency.has(edge.sourceId)) adjacency.set(edge.sourceId, new Set());
    if (!adjacency.has(edge.targetId)) adjacency.set(edge.targetId, new Set());
    adjacency.get(edge.sourceId)!.add(edge.targetId);
    adjacency.get(edge.targetId)!.add(edge.sourceId);
  }

  const selected = new Set<string>([graph.rootId]);
  let frontier = [graph.rootId];
  for (let level = 1; level <= depth && selected.size < MAX_VISIBLE_GRAPH_NODES; level += 1) {
    const candidates = [...new Set(frontier.flatMap((id) => [...(adjacency.get(id) ?? [])]))]
      .filter((id) => !selected.has(id))
      .map((id) => nodeMap.get(id))
      .filter((node): node is KnowledgeGraphNode => Boolean(node));
    const groups = new Map<string, KnowledgeGraphNode[]>();
    for (const node of candidates) {
      const group = groups.get(node.kind) ?? [];
      group.push(node);
      groups.set(node.kind, group);
    }

    const chosen: KnowledgeGraphNode[] = [];
    const limit = Math.min(nodesPerLayer, MAX_VISIBLE_GRAPH_NODES - selected.size);
    while (chosen.length < limit && [...groups.values()].some((group) => group.length > 0)) {
      for (const group of groups.values()) {
        const node = group.shift();
        if (node) chosen.push(node);
        if (chosen.length === limit) break;
      }
    }
    for (const node of chosen) selected.add(node.id);
    frontier = chosen.map((node) => node.id);
    if (frontier.length === 0) break;
  }

  return {
    ...graph,
    nodes: graph.nodes.filter((node) => selected.has(node.id)),
    edges: graph.edges.filter((edge) => selected.has(edge.sourceId) && selected.has(edge.targetId)),
  };
}

/** 左栏关联论文列表：与 root 通过 CITES 直接相连的 Paper 节点 */
export function relatedPapers(graph: KnowledgeGraph): KnowledgeRelatedPaper[] {
  const list: KnowledgeRelatedPaper[] = [];
  for (const node of graph.nodes) {
    if (node.id === graph.rootId || node.kind !== "Paper") continue;
    const direction = relationDirectionOf(node.id, graph);
    if (!direction) continue;
    list.push({
      id: node.id,
      title: node.label,
      year: node.properties.year ?? null,
      venue: node.properties.venue ?? null,
      authors: node.properties.authors ?? [],
      citationCount: null,
      relationDirection: direction,
    });
  }
  list.sort((a, b) => {
    const dirDiff = DIRECTION_ORDER[a.relationDirection] - DIRECTION_ORDER[b.relationDirection];
    if (dirDiff !== 0) return dirDiff;
    return (b.year ?? 0) - (a.year ?? 0);
  });
  return list;
}

/** 按方向筛选关联论文（all 表示全部） */
export function filterByDirection(
  list: KnowledgeRelatedPaper[],
  direction: "all" | KnowledgeRelationDirection,
): KnowledgeRelatedPaper[] {
  if (direction === "all") return list;
  return list.filter((item) => item.relationDirection === direction || item.relationDirection === "both");
}

/**
 * 按引用方向过滤图谱（列表与图谱统一规则）。
 * 非 Paper 节点作为上下文保留；Paper 节点仅保留与 root 引用方向匹配的。
 */
export function filterGraphByDirection(
  graph: KnowledgeGraph,
  direction: GraphDirectionFilter,
): KnowledgeGraph {
  if (direction === "all") return graph;
  const keep = new Set<string>([graph.rootId]);
  for (const node of graph.nodes) {
    if (node.kind !== "Paper") keep.add(node.id);
  }
  for (const node of graph.nodes) {
    if (node.kind !== "Paper") continue;
    const dir = relationDirectionOf(node.id, graph);
    if (dir === "both" || dir === direction) keep.add(node.id);
  }
  return {
    ...graph,
    rootId: graph.rootId,
    nodes: graph.nodes.filter((node) => keep.has(node.id)),
    edges: graph.edges.filter(
      (edge) => keep.has(edge.sourceId) && keep.has(edge.targetId),
    ),
  };
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** 节点在画布上的短标签（两行） */
export function nodeLabelLines(node: KnowledgeGraphNode): [string, string] {
  if (node.kind === "Paper") {
    const authors = node.properties.authors ?? [];
    const surname = authors.length ? authors[authors.length - 1].split(/\s+/).pop() ?? "" : "";
    const line1 = surname || truncate(node.label, 14);
    const line2 = node.properties.year ? String(node.properties.year) : "Paper";
    return [line1, line2];
  }
  if (node.kind === "Author") {
    return [truncate(node.label, 12), "作者"];
  }
  const second =
    typeof node.properties.year === "number"
      ? String(node.properties.year)
      : kindLabel(node.kind);
  return [truncate(node.label, 12), second];
}

/** 节点半径：root 更大，其余按度数 */
export function nodeRadiusOf(node: KnowledgeGraphNode, graph: KnowledgeGraph, isRoot = false): number {
  if (isRoot) return 30;
  const degree = degreeOf(node.id, graph.edges);
  return 16 + Math.min(degree, 8) * 2.4;
}
