import type { ScholarProfile } from "./types";

export const CITATION_END_YEAR = 2026;
export const CITATION_START_YEAR = CITATION_END_YEAR - 4;

export function scholarName(scholar: ScholarProfile): string {
  return scholar.name_zh?.trim() || scholar.name_en?.trim() || "姓名暂缺";
}

export function scholarInitials(name?: string | null): string {
  const words = name?.trim().split(/\s+/).filter(Boolean) ?? [];
  return words.length
    ? words
        .slice(0, 2)
        .map((word) => Array.from(word)[0])
        .join("")
        .toUpperCase()
    : "?";
}

export function formatScholarMetric(value?: number | null): string {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value.toLocaleString("en-US")
    : "暂无数据";
}

export function recentCitations(data: ScholarProfile["annual_citations"]) {
  return (data ?? [])
    .filter(
      (item): item is { year: number; count: number } =>
        Number.isInteger(item.year) &&
        item.year >= CITATION_START_YEAR &&
        item.year <= CITATION_END_YEAR &&
        typeof item.count === "number" &&
        Number.isFinite(item.count) &&
        item.count >= 0,
    )
    .slice()
    .sort((a, b) => a.year - b.year);
}
