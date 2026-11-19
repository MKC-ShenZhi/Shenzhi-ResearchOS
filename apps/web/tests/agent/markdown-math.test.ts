import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import katex from "katex";
import { normalizeMathDelimiters } from "../../components/renderers/math-delimiters";

test("Agent markdown enables KaTeX rendering for inline and display dollar math", () => {
  const page = readFileSync("features/agent-chat/shenzhi-ai-page.tsx", "utf8");
  const timeline = readFileSync("features/agent-chat/timeline-view.tsx", "utf8");
  const source = readFileSync("components/renderers/streamdown-renderer.tsx", "utf8");
  const inline = "The distance is $d(x,y)=\\sqrt{x^2+y^2}$.";
  const display = "$$\n\\sum_{i=1}^{n} x_i\n$$";

  assert.match(page, /<StreamdownRenderer content=\{turn\.content\} isStreaming=/);
  assert.match(timeline, /function ThinkingBlock\b[\s\S]*?<StreamdownRenderer\s+content=\{text\}\s+isStreaming=\{live\}/);
  assert.match(source, /<Streamdown\b/);
  assert.match(source, /remarkPlugins:[^\n]*\[remarkGfm, remarkMath\]/);
  assert.match(source, /\[rehypeKatex, \{ trust: false,/);
  assert.doesNotMatch(source, /from "react-markdown"|<MarkdownRenderer\b/);
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
