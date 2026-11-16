import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import katex from "katex";
import { normalizeMathDelimiters } from "../../features/agent-chat/math-delimiters";

test("Agent markdown enables KaTeX rendering for inline and display dollar math", () => {
  const source = readFileSync("features/agent-chat/shenzhi-ai-page.tsx", "utf8");
  const inline = "The distance is $d(x,y)=\\sqrt{x^2+y^2}$.";
  const display = "$$\n\\sum_{i=1}^{n} x_i\n$$";

  assert.match(source, /remarkPlugins=\{\[remarkGfm, remarkMath\]\}/);
  assert.match(source, /rehypePlugins=\{\[\[rehypeKatex,/);
  assert.match(source, /import "katex\/dist\/katex\.min\.css"/);
  assert.equal(normalizeMathDelimiters(inline), inline);
  assert.equal(normalizeMathDelimiters(display), display);
  assert.match(katex.renderToString("d(x,y)=\\sqrt{x^2+y^2}"), /class="katex"/);
  assert.match(katex.renderToString("\\sum_{i=1}^{n} x_i", { displayMode: true }), /class="katex-display"/);
});

test("Agent markdown converts LaTeX inline and standalone display delimiters", () => {
  assert.equal(
    normalizeMathDelimiters(String.raw`The distance is \( d(x,y)=\sqrt{x^2+y^2} \).`),
    "The distance is $d(x,y)=\\sqrt{x^2+y^2}$.",
  );
  assert.equal(
    normalizeMathDelimiters(String.raw`Before
\[
\sum_{i=1}^{n} x_i
\]
After`),
    ["Before", "$$", String.raw`\sum_{i=1}^{n} x_i`, "$$", "After"].join("\n"),
  );
});

test("Agent math delimiter conversion leaves markdown, code, and prose intact", () => {
  const markdown = [
    "**Bold text** and `\(code\)`.",
    "```latex",
    String.raw`\(x^2\) and \[y^2\]`,
    "```",
    String.raw`The value is \(x^2\), and \emph{emphasis} stays unchanged.`,
  ].join("\n");

  assert.equal(
    normalizeMathDelimiters(markdown),
    [
      "**Bold text** and `\(code\)`.",
      "```latex",
      String.raw`\(x^2\) and \[y^2\]`,
      "```",
      String.raw`The value is $x^2$, and \emph{emphasis} stays unchanged.`,
    ].join("\n"),
  );
});
