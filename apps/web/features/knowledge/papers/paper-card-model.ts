import type { PaperCardModel } from "../../../types";

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

/** 卡片 Topic：优先上游关键词，否则学科主题，最多 5 个。 */
export function pickPaperTopics(keywords: string[] | undefined, subjects: string[] | undefined): string[] {
  return (keywords?.length ? keywords : subjects ?? []).slice(0, 5);
}
