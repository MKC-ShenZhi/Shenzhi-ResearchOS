import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import test from "node:test";

function sourceFiles(root: string): string[] {
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const path = join(root, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(?:ts|tsx)$/.test(entry.name) ? [path] : [];
  });
}

function moduleSpecifiers(source: string): string[] {
  return [...source.matchAll(/(?:from\s+|import\s*\()\s*["']([^"']+)["']/g)]
    .map((match) => match[1]);
}

test("lib never imports clients", () => {
  for (const file of sourceFiles("lib")) {
    const imports = moduleSpecifiers(readFileSync(file, "utf8"));
    assert.equal(
      imports.some((specifier) => specifier.includes("clients/")),
      false,
      `${relative(".", file)} must not depend on clients`,
    );
  }
});

test("clients do not depend on UI or feature layers", () => {
  for (const file of sourceFiles("clients")) {
    const imports = moduleSpecifiers(readFileSync(file, "utf8"));
    const invalid = imports.find((specifier) =>
      /(?:^|\/)(?:features|components|stores)(?:\/|$)/.test(specifier),
    );
    assert.equal(invalid, undefined, `${relative(".", file)} imports ${invalid}`);
  }
});

test("backend base files do not depend on module clients", () => {
  const baseFiles = sourceFiles("clients/backend").filter(
    (file) => relative("clients/backend", file).split(/[\\/]/).length === 1,
  );
  for (const file of baseFiles) {
    const imports = moduleSpecifiers(readFileSync(file, "utf8"));
    const invalid = imports.find((specifier) => /^\.\/(?:chat|profile|settings)(?:\/|$)/.test(specifier));
    assert.equal(invalid, undefined, `${relative(".", file)} imports ${invalid}`);
  }
});
