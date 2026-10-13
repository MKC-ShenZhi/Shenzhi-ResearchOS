#!/usr/bin/env node
/** Compare identical pages in light/dark; calls the existing CDP screenshot tool. */
import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const args = {};
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i];
  if (!key.startsWith("--") || !process.argv[i + 1]) throw new Error(`Missing value: ${key}`);
  args[key.slice(2)] = process.argv[i + 1];
}
const primary = {
  "indigo-research": { light: "#51478a", dark: "#b5abe4" },
  "warm-indigo": { light: "#4f46e5", dark: "#a5b4fc" },
  "warm-teal": { light: "#1c7783", dark: "#7bd4d8" },
};
if (!primary[args.scheme] || !args.out || !args.session) {
  throw new Error("Required: --scheme indigo-research|warm-indigo|warm-teal --out directory --session session-id");
}
const base = new URL(args.base || "http://localhost:3100");
if (!["localhost", "127.0.0.1", "[::1]"].includes(base.hostname)) {
  throw new Error("This visual comparison tool only accesses a local development server");
}
const script = join(dirname(fileURLToPath(import.meta.url)), "shot-cdp.mjs");
const pages = [
  { name: "home", path: "/", wait: args["home-wait"] || "发现" },
  { name: "agent-session", path: "/agents", params: { session: args.session }, wait: args["agent-wait"] || "配色验收" },
  { name: "knowledge-search", path: "/knowledge/search", params: { q: "diffusion" }, wait: args["knowledge-wait"] || "Diffusion" },
];
const out = resolve(args.out);
mkdirSync(out, { recursive: true });
const results = [];
for (const page of pages) {
  for (const theme of ["light", "dark"]) {
    const url = new URL(page.path, base);
    for (const [key, value] of Object.entries(page.params || {})) url.searchParams.set(key, value);
    url.searchParams.set("theme", theme);
    const file = join(out, `${page.name}-${theme}.png`);
    const command = [script, "--url", url.href, "--out", file,
      "--width", "1440", "--height", "1100", "--wait-text", page.wait,
      "--theme", theme, "--expected-primary", primary[args.scheme][theme], "--settle", "2000"];
    if (args["response-fixture"]) command.push("--response-fixture", resolve(args["response-fixture"]));
    const result = spawnSync(process.execPath, command, { stdio: "inherit", windowsHide: true });
    results.push({ page: page.name, theme, file, passed: result.status === 0 });
    if (result.status !== 0) break;
  }
  if (results.some(result => !result.passed)) break;
}
writeFileSync(join(out, "manifest.json"), JSON.stringify({
  scheme: args.scheme,
  dataMode: args["response-fixture"] ? "browser-only visual fixtures; not live business validation" : "live",
  results,
}, null, 2));
if (results.length !== 6 || results.some(result => !result.passed)) process.exitCode = 1;
