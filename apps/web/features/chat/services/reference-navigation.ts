import type { ChatReference } from "@/types/ai-search";
import { paperHref } from "../../../lib/navigation/paper";

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized || null;
}

/** Read the canonical citation identity, with the existing persisted alias as fallback. */
export function referenceIdOf(reference: ChatReference): string | null {
  const canonical = nonEmptyString(reference.referenceId);
  if (canonical) return canonical;
  return Number.isInteger(reference.ordinal) ? String(reference.ordinal) : null;
}

export function resourceTypeOf(reference: ChatReference): string | null {
  return nonEmptyString(reference.resourceType) ?? nonEmptyString(reference.source_type);
}

export function resourceIdOf(reference: ChatReference): string | null {
  return nonEmptyString(reference.resourceId) ?? nonEmptyString(reference.source_id);
}

/** The unified Paper Detail route accepts the opaque resource ID. */
export function paperReferenceHref(reference: ChatReference, returnTo?: string | null): string | null {
  if (resourceTypeOf(reference) !== "paper") return null;
  const resourceId = resourceIdOf(reference);
  return resourceId
    ? paperHref(resourceId, returnTo)
    : null;
}

/**
 * Keep the MVP parser intentionally narrow: only standalone numeric [n]
 * markers count, and returned IDs are deduplicated in first-appearance order.
 */
export function citedReferenceIds(answer: string, references: ChatReference[]): string[] {
  const validIds = new Set(
    references.map(referenceIdOf).filter((id): id is string => id !== null),
  );
  const seen = new Set<string>();
  const cited: string[] = [];
  for (const match of answer.matchAll(/\[(\d+)\]/g)) {
    const id = match[1];
    if (validIds.has(id) && !seen.has(id)) {
      seen.add(id);
      cited.push(id);
    }
  }
  return cited;
}
