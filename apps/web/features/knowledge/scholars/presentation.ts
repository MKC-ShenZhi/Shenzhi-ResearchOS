import type { ScholarProfile } from "./types";

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
        item.year > 0 &&
        typeof item.count === "number" &&
        Number.isFinite(item.count) &&
        item.count >= 0,
    )
    .slice()
    .sort((a, b) => a.year - b.year)
    .slice(-5);
}

/** Failed images, unsafe URLs and missing paths share the initials fallback. */
export function scholarAvatarSource(value?: string | null, failedSrc?: string | null): string | null {
  const src = value?.trim();
  return src && src !== failedSrc && (
    src.startsWith("https://") ||
    src.startsWith("/images/") ||
    src.startsWith("/api/v1/knowledge/scholar-avatar?path=")
  ) ? src : null;
}
