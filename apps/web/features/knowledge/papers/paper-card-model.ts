import type { PaperCardModel } from "../../../types";
import type { KnowledgePaperHit, PaperTopic } from "../../../clients/knowledge/types";
import { getPaperThumbnailUrl } from "../../../lib/paper-thumbnail";

export function formatPaperYear(year: number | null): string {
  return year === null ? "年份未知" : String(year);
}

export function formatPaperAuthors(authors: string[]): string {
  if (authors.length === 0) return "作者未知";
  const visible = authors.slice(0, 5).join(" · ");
  return authors.length > 5 ? `${visible} 等` : visible;
}

/** 按底座顺序取最多五个有名称的不同主题。 */
export function pickPaperTopics(topics?: PaperTopic[]): PaperTopic[] {
  const visible = new Map<string, PaperTopic>();
  for (const topic of Array.isArray(topics) ? topics : []) {
    const id = typeof topic?.id === "string" ? topic.id.trim() : "";
    const nameZh = typeof topic?.nameZh === "string" ? topic.nameZh.trim() : "";
    const nameEn = typeof topic?.nameEn === "string" ? topic.nameEn.trim() : "";
    if (!id || id === "." || id === ".." || (!nameZh && !nameEn) || visible.has(id)) continue;
    visible.set(id, { id, nameZh: nameZh || null, nameEn });
    if (visible.size === 5) break;
  }
  return [...visible.values()];
}

export function toPaperCardModel(
  paper: Pick<KnowledgePaperHit, "id" | "year" | "venue" | "authors" | "title" | "abstract" | "topics">
    & Partial<Pick<KnowledgePaperHit, "imageId">>,
): PaperCardModel {
  return {
    id: paper.id,
    date: formatPaperYear(paper.year),
    venue: paper.venue,
    authors: formatPaperAuthors(paper.authors),
    title: paper.title,
    abstract: paper.abstract ?? "",
    topics: pickPaperTopics(paper.topics),
    thumbnailUrl: getPaperThumbnailUrl(paper.imageId),
  };
}
