import assert from "node:assert/strict";
import test from "node:test";

import {
  DISPLAY_NAME_MAX_LENGTH,
  validateDisplayName,
} from "../../lib/auth/policies/display-name";

test("display names are normalized and bounded by the shared policy", () => {
  assert.deepEqual(validateDisplayName("  Ada Lovelace  "), {
    valid: true,
    normalized: "Ada Lovelace",
  });
  assert.deepEqual(validateDisplayName("   "), {
    valid: false,
    code: "DISPLAY_NAME_REQUIRED",
  });
  assert.deepEqual(validateDisplayName("x".repeat(DISPLAY_NAME_MAX_LENGTH + 1)), {
    valid: false,
    code: "DISPLAY_NAME_TOO_LONG",
  });
});
