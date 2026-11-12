import type { ScholarProfilePage } from "../../../clients/knowledge/scholar-profiles";

export const SCHOLAR_BATCH_SIZE = 8;

export function nextScholarOffset(batch: ScholarProfilePage): number | undefined {
  return batch.has_more && batch.items.length > 0 ? batch.offset + batch.items.length : undefined;
}
