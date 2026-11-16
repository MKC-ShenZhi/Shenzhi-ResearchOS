/** Presentation helpers shared by the markdown renderer and the comparison table. */

type Lang = "zh" | "en";

export function imageFailureLabel(alt: string, lang: Lang): string {
  const fallback = lang === "zh" ? "图片加载失败" : "Image failed to load";
  const subject = alt.trim();
  return subject ? `${fallback}: ${subject}` : fallback;
}

/** Minimum natural dimensions for a report figure; rejects icons and error thumbnails. */
export function isUsableReportImage(width: number, height: number): boolean {
  return width >= 240 && height >= 160;
}
