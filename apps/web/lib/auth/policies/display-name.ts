export const DISPLAY_NAME_MAX_LENGTH = 80;

export type DisplayNameValidation =
  | { valid: true; normalized: string }
  | { valid: false; code: "DISPLAY_NAME_REQUIRED" | "DISPLAY_NAME_TOO_LONG" };

export function validateDisplayName(value: string): DisplayNameValidation {
  const normalized = value.trim();
  if (!normalized) return { valid: false, code: "DISPLAY_NAME_REQUIRED" };
  if (normalized.length > DISPLAY_NAME_MAX_LENGTH) {
    return { valid: false, code: "DISPLAY_NAME_TOO_LONG" };
  }
  return { valid: true, normalized };
}
