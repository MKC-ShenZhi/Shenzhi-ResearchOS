export const KNOWLEDGE_SEARCH_PAGE_SIZE = 20;

export type KnowledgePaginationItem = number | "ellipsis";

export function knowledgeSearchOffset(page: number): number {
  return (Math.max(1, page) - 1) * KNOWLEDGE_SEARCH_PAGE_SIZE;
}

/**
 * The upstream search response has no total count. Keep the first page,
 * nearby known pages, and the look-ahead page visible without inventing a
 * final page number.
 */
export function knowledgePaginationItems(
  currentPage: number,
  hasMore: boolean,
): KnowledgePaginationItem[] {
  const lastKnownPage = currentPage + (hasMore ? 1 : 0);
  const pages = Array.from(new Set([
    1,
    currentPage - 1,
    currentPage,
    lastKnownPage,
  ]))
    .filter((page) => page >= 1 && page <= lastKnownPage)
    .sort((a, b) => a - b);

  const items: KnowledgePaginationItem[] = [];
  pages.forEach((page, index) => {
    if (index > 0 && page - pages[index - 1] > 1) items.push("ellipsis");
    items.push(page);
  });
  return items;
}
