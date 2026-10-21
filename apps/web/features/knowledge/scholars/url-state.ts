export const SCHOLAR_PAGE_SIZE = 20;
export function scholarPage(value: string | null): number {
  const page = Number(value);
  return Number.isSafeInteger(page) && page > 0 && page <= 1_000_000 ? page : 1;
}
