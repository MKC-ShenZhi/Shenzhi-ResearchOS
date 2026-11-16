/** Citation IDs are references, never paper/resource IDs. */
export function isKnownCitation(
  referenceId: string,
  validReferenceIds: ReadonlySet<string>,
): boolean {
  return validReferenceIds.has(referenceId);
}
