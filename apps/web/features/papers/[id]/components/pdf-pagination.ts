export const INITIAL_PAGE_COUNT = 3;
export const PAGE_BATCH_SIZE = 3;

export function initialRenderedPageCount(numPages: number): number {
  return Math.min(INITIAL_PAGE_COUNT, Math.max(0, numPages));
}

export function nextRenderedPageCount(current: number, numPages: number): number {
  return Math.min(numPages, current + PAGE_BATCH_SIZE);
}

/** Reaching the final page does not require scrolling to its last pixel. */
export function isFinalPageVisible(
  page: { top: number; bottom: number; height: number },
  viewport: { top: number; bottom: number; height: number },
): boolean {
  const overlap = Math.min(page.bottom, viewport.bottom) - Math.max(page.top, viewport.top);
  return overlap >= Math.min(page.height, viewport.height) * 0.15;
}
