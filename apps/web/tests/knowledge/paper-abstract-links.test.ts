import assert from "node:assert/strict";
import test from "node:test";

import {
  LATEX_LINK_PLACEHOLDER,
  replaceLatexLinks,
  splitLatexLinks,
} from "../../components/renderers/latex-links";

function links(text: string) {
  return splitLatexLinks(text).filter((segment) => segment.type === "link").map((segment) => segment.text);
}

test("abstract links drop sentence punctuation after the URL", () => {
  assert.deepEqual(links("Code is available at https://github.com/CoCoRessa/MoECLIP."), [
    "https://github.com/CoCoRessa/MoECLIP",
  ]);
  assert.deepEqual(links("Our code: https://github.com/yyliu01/GroupRevision ."), [
    "https://github.com/yyliu01/GroupRevision",
  ]);
  assert.deepEqual(links("项目地址：https://example.org/a，欢迎使用。"), ["https://example.org/a"]);
});

test("abstract links keep balanced parentheses but strip wrapping ones", () => {
  assert.deepEqual(links("(see https://github.com/org/repo)"), ["https://github.com/org/repo"]);
  assert.deepEqual(links("https://en.wikipedia.org/wiki/Mixture_(probability)"), [
    "https://en.wikipedia.org/wiki/Mixture_(probability)",
  ]);
});

test("abstract links keep project pages and multiple URLs as plain links", () => {
  const text = "Project page: https://YukinoWan.github.io/Speech-Hands/ and code https://github.com/a/b_c#readme";
  assert.deepEqual(links(text), [
    "https://YukinoWan.github.io/Speech-Hands/",
    "https://github.com/a/b_c#readme",
  ]);
  assert.equal(splitLatexLinks(text).map((segment) => segment.text).join(""), text);
});

test("abstract links ignore text without a usable http URL", () => {
  assert.deepEqual(links("We use ftp://example.org and javascript:alert(1)"), []);
  assert.deepEqual(links("Visit https:// later"), []);
  assert.deepEqual(splitLatexLinks("No links here."), [{ type: "text", text: "No links here." }]);
});

test("LaTeX source replaces URLs with placeholders that map back to the original text", () => {
  const { source, links: found } = replaceLatexLinks("See https://github.com/a_b/diff%20x~y and https://x.org/q.");
  assert.doesNotMatch(source, /https?:/);
  assert.doesNotMatch(source, /[_%~]/);
  assert.deepEqual(found.map((link) => link.text), ["https://github.com/a_b/diff%20x~y", "https://x.org/q"]);
  const restored = source.replace(new RegExp(LATEX_LINK_PLACEHOLDER, "g"), (_, index) => found[Number(index)].text);
  assert.equal(restored, "See https://github.com/a_b/diff%20x~y and https://x.org/q.");
});

test("LaTeX URL commands are replaced as a whole so inline math can still render", () => {
  const input = String.raw`The parameter is $\beta$. Code: \url{https://example.org/a_b%20c~d!}.`;
  const url = "https://example.org/a_b%20c~d!";
  const link = { type: "link", text: url, href: url };

  assert.deepEqual(replaceLatexLinks(input), {
    source: String.raw`The parameter is $\beta$. Code: SZLINK0TOKEN.`,
    links: [link],
  });
  assert.deepEqual(splitLatexLinks(input), [
    { type: "text", text: String.raw`The parameter is $\beta$. Code: ` },
    link,
    { type: "text", text: "." },
  ]);
});
