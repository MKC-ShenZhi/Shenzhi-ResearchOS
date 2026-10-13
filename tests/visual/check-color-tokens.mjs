#!/usr/bin/env node
/** Validate complete interchangeable palettes and the intended opaque text/surface pairs. */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function luminance(hex) {
  return [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255)
    .map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
    .reduce((total, value, index) => total + value * [0.2126, 0.7152, 0.0722][index], 0);
}
const pairs = [
  ["primary-foreground", "primary"], ["primary-foreground", "primary-deep"],
  ["primary", "primary-soft"], ["selected-foreground", "selected"],
  ["neutral-foreground", "neutral-action"], ["neutral-foreground", "neutral-action-hover"],
  ["danger-foreground", "danger"], ["danger-foreground", "danger-hover"], ["danger", "danger-soft"],
  ["success", "success-soft"], ["success-foreground", "success"],
  ["agent", "agent-soft"], ["agent-foreground", "agent"],
  ["warning", "warning-soft"], ["brand-gold-foreground", "brand-gold"],
  ["selection-foreground", "selection"],
];
for (const text of ["ink", "body", "ink-2", "muted", "faint"]) {
  for (const background of ["background", "card", "popover", "sidebar", "topbar", "chip", "panel", "selected"]) {
    pairs.push([text, background]);
  }
}
let referenceKeys;
const summaries = [];
const failures = [];
for (const scheme of ["indigo-research", "warm-indigo", "warm-teal"]) {
  const file = fileURLToPath(new URL(`../../apps/web/styles/themes/${scheme}.css`, import.meta.url));
  const source = readFileSync(file, "utf8");
  for (const [mode, pattern] of [["light", /@theme\s*\{([^}]+)\}/], ["dark", /\.dark\s*\{([^}]+)\}/]]) {
    const block = source.match(pattern)?.[1];
    if (!block) throw new Error(`Missing ${scheme}/${mode}`);
    const colors = Object.fromEntries([...block.matchAll(/--color-([\w-]+):\s*(#[\da-f]{6});/gi)]
      .map(match => [match[1], match[2]]));
    const keys = Object.keys(colors).sort().join(",");
    referenceKeys ??= keys;
    if (keys !== referenceKeys) failures.push({ scheme, mode, error: "Palette token names differ" });
    let minimum = Infinity;
    for (const [foreground, background] of pairs) {
      if (!colors[foreground] || !colors[background]) throw new Error(`Missing token: ${foreground}/${background}`);
      const first = luminance(colors[foreground]), second = luminance(colors[background]);
      const ratio = (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
      minimum = Math.min(minimum, ratio);
      if (ratio < 4.5) failures.push({ scheme, mode, foreground, background, ratio });
    }
    summaries.push({ scheme, mode, tokenCount: Object.keys(colors).length, checkedPairs: pairs.length, minimumContrast: minimum });
  }
}
console.log(JSON.stringify({ summaries, failures, scope: "Opaque token pairs only; opacity and composed backgrounds require browser inspection" }, null, 2));
if (failures.length) process.exitCode = 1;
