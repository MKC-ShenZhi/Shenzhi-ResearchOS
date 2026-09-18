const ARXIV_PAPER_ID_PATTERN =
  /^paper:(\d{4}\.\d{4,5}(?:v[1-9]\d*)?)$/;

/** Extracts a modern arXiv identifier without changing the opaque paper id. */
export function extractArxivId(paperId: string): string | null {
  return ARXIV_PAPER_ID_PATTERN.exec(paperId)?.[1] ?? null;
}

/** Returns a same-origin local thumbnail URL when the MVP feature is enabled. */
export function getPaperThumbnailUrl(paperId: string): string | null {
  if (process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED !== "true") {
    return null;
  }

  const arxivId = extractArxivId(paperId);
  return arxivId === null ? null : `/api/paper-thumbnail/${arxivId}`;
}
