import assert from "node:assert/strict";
import test from "node:test";
import {
  createCustomThemeVariables,
  DEFAULT_CUSTOM_THEME,
  normalizeCustomThemeConfig,
} from "../../lib/custom-theme";

test("custom theme normalizes invalid persisted values", () => {
  assert.deepEqual(normalizeCustomThemeConfig({ accent: "invalid", appearance: "light" }), DEFAULT_CUSTOM_THEME);
  assert.deepEqual(normalizeCustomThemeConfig({ accent: "#00a67e", appearance: "dark" }), {
    accent: "#00A67E",
    appearance: "dark",
  });
});

test("custom theme derives complete light and dark semantic surfaces", () => {
  const light = createCustomThemeVariables({ accent: "#F59E0B", appearance: "light" });
  const dark = createCustomThemeVariables({ accent: "#315EFB", appearance: "dark" });

  for (const variables of [light, dark]) {
    for (const token of [
      "--color-background",
      "--color-sidebar",
      "--color-card",
      "--color-primary",
      "--color-primary-soft",
      "--color-ink",
      "--color-panel",
      "--color-line",
      "--page-wallpaper",
      "--surface-card-image",
      "--surface-sidebar-image",
    ]) {
      assert.equal(typeof variables[token], "string", token);
      assert.ok(variables[token].length > 0, token);
    }
  }

  assert.notEqual(light["--color-background"], dark["--color-background"]);
  assert.notEqual(light["--color-card"], dark["--color-card"]);
});
