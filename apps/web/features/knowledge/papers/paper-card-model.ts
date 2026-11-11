import type { PaperCardModel } from "../../../types";
import type { PaperTopic } from "../../../clients/knowledge/types";

const VENUE_TONES: PaperCardModel["venueTone"][] = ["violet", "amber", "green"];

/** 按论文 ID 取色，同一篇论文在首页与检索中颜色一致。 */
export function paperVenueTone(id: string): PaperCardModel["venueTone"] {
  let hash = 0;
  for (const character of id) hash = (hash + character.charCodeAt(0)) % VENUE_TONES.length;
  return VENUE_TONES[hash];
}

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
