export const INITIAL_PAGE_COUNT = 3;
export const PAGE_BATCH_SIZE = 3;

export function initialRenderedPageCount(numPages: number): number {
  return Math.min(INITIAL_PAGE_COUNT, Math.max(0, numPages));
}

export function nextRenderedPageCount(current: number, numPages: number): number {
  return Math.min(numPages, current + PAGE_BATCH_SIZE);
}
