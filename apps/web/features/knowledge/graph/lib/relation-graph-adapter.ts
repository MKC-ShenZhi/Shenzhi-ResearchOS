import { RGLineShape, RGNodeShape } from "@relation-graph/react";
import type { RGJsonData } from "@relation-graph/react";
import type { KnowledgeGraph } from "@/clients/knowledge";
import type { NodePositions } from "./layouts";
import { nodeColor } from "./graph-utils";

const RELATION_COLORS: Record<string, string> = {
  CITES: "#8492a6",
  AUTHORED_BY: "#34d399",
  PROPOSES: "#a78bfa",
  USES_AS_BASELINE: "#fbbf24",
  HAS_TOPIC: "#38bdf8",
  PUBLISHED_IN: "#2dd4bf",
  FUNDED_BY: "#fcd34d",
  AFFILIATED_WITH: "#fb7185",
};

/** Only adapt the stable KnowledgeGraph contract; IDs and CITES direction stay unchanged. */
export function toRelationGraphData(graph: KnowledgeGraph, positions: NodePositions): RGJsonData {
  const nodeIds = new Set(graph.nodes.map((node) => node.id));
  return {
    rootId: graph.rootId,
    nodes: graph.nodes.map((node) => {
      const position = positions.get(node.id);
      const isRoot = node.id === graph.rootId;
      return {
        id: node.id,
        text: node.label,
        type: node.kind,
        x: position?.x ?? 0,
        y: position?.y ?? 0,
        nodeShape: RGNodeShape.circle,
        width: isRoot ? 68 : 50,
        height: isRoot ? 68 : 50,
        color: nodeColor(node.kind),
        borderColor: isRoot ? "#ffffff" : "#e2e8f0",
        borderWidth: isRoot ? 3 : 2,
        fontColor: "#ffffff",
        data: { kind: node.kind },
      };
    }),
    lines: graph.edges
      .filter((edge) => nodeIds.has(edge.sourceId) && nodeIds.has(edge.targetId))
      .map((edge, index) => ({
        id: `${edge.sourceId}:${edge.relation}:${edge.targetId}:${index}`,
        from: edge.sourceId,
        to: edge.targetId,
        type: edge.relation,
        text: edge.relation === "CITES" ? "" : edge.description ?? "",
        color: RELATION_COLORS[edge.relation] ?? "#94a3b8",
        lineWidth: edge.relation === "CITES" ? 1.8 : 1.4,
        lineShape: RGLineShape.StandardStraight,
        showEndArrow: edge.relation === "CITES",
        dashType: edge.relation === "CITES" ? 0 : 4,
        opacity: 0.75,
      })),
  };
}
