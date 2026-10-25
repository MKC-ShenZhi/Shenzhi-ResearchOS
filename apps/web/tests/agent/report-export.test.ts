import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildReportDocument, reportFileName } from "../../features/agent-chat/report/export-document";

const DIALOG_SOURCE = readFileSync("features/agent-chat/report-dialog.tsx", "utf8");
const REPORT_SOURCE = readFileSync("features/agent-chat/report/report-view.tsx", "utf8");
const TABLE_SOURCE = readFileSync("features/agent-chat/report/comparison-table.tsx", "utf8");

const documentInput = {
  title: "研究报告",
  bodyHtml: '<article><h1>完整报告</h1><p>最后一段</p></article>',
  cssText: ".report { color: blue; }",
};

test("报告导出构建完整独立文档并保留正文", () => {
  const html = buildReportDocument(documentInput);
  assert.match(html, /^<!doctype html>/i);
  assert.match(html, /<html lang="zh-CN">/);
  assert.ok(html.includes(`<div id="report-export-root">${documentInput.bodyHtml}</div>`));
  assert.match(html, /<meta charset="utf-8">/);
  assert.match(html, /<\/body><\/html>$/);
});

test("报告导出覆盖滚动、折叠与分页样式，且覆盖位于内联样式之后", () => {
  const html = buildReportDocument(documentInput);
  for (const rule of ["max-height: none !important", "[data-print-hide]", "[data-print-only]", "@page",
    "overflow: visible !important", "white-space: pre-wrap !important", "min-width: 0 !important"]) {
    assert.ok(html.includes(rule), `缺少 ${rule}`);
  }
  assert.ok(html.indexOf(documentInput.cssText) < html.indexOf("#report-export-root *"));
  assert.ok(html.indexOf("[data-print-only]") < html.indexOf("@media print"));
  assert.ok(html.indexOf("[data-print-only]") < html.indexOf("</head>"));
});

test("报告标题转义 HTML 特殊字符", () => {
  const html = buildReportDocument({ ...documentInput, title: 'a<b>&"c' });
  assert.match(html, /<title>a&lt;b&gt;&amp;&quot;c<\/title>/);
  assert.ok(!html.includes("<b>"));
});

test("报告保留主题属性并使用不带 dark class 的 html 标签", () => {
  const html = buildReportDocument({ ...documentInput, themeAttr: "gpt" });
  assert.match(html, /<html lang="zh-CN" data-theme="gpt">/);
  const htmlTag = html.match(/<html\b[^>]*>/)?.[0] ?? "";
  assert.doesNotMatch(htmlTag, /class="dark"/);
  const escapedTheme = buildReportDocument({ ...documentInput, themeAttr: 'gpt" onload="bad' });
  assert.match(escapedTheme, /data-theme="gpt&quot; onload=&quot;bad"/);
});

test("报告文件名替换所有非法字符", () => {
  assert.equal(reportFileName('a\\/:*?"<>|b', "html"), "a_________b.html");
});

test("报告文件名先将标题截断至 60 字符，再附加扩展名", () => {
  assert.equal(reportFileName("长".repeat(80), "html"), `${"长".repeat(60)}.html`);
});

test("报告空标题使用默认文件名", () => {
  assert.equal(reportFileName(undefined, "html"), "report.html");
  assert.equal(reportFileName("", "pdf"), "report.pdf");
});

test("打印与 HTML 导出共用文档构建，打印入口不再直接打印当前页面", () => {
  assert.doesNotMatch(DIALOG_SOURCE, /onClick=\{\(\) => window\.print\(\)\}/);
  assert.match(DIALOG_SOURCE, /onClick=\{printReport\} disabled=\{printing\}/);
  assert.match(DIALOG_SOURCE, /printReportDocument\(await createReportDocument\(\)\)/);
  assert.match(DIALOG_SOURCE, /const html = await createReportDocument\(\)/);
  assert.match(DIALOG_SOURCE, /iframe\.srcdoc = html/);
});

test("参考文献折叠区域保留完整条目并复用条目渲染", () => {
  assert.match(REPORT_SOURCE, /data-print-hide/);
  assert.match(REPORT_SOURCE, /className="hidden space-y-1\.5" data-print-only/);
  assert.match(REPORT_SOURCE, /ordered\.slice\(0, visibleCount\)\.map\(renderReference\)/);
  assert.match(REPORT_SOURCE, /ordered\.slice\(visibleCount\)\.map\(renderReference\)/);
});

test("比较表保留屏幕分页，导出完整列时复用表格渲染", () => {
  assert.match(TABLE_SOURCE, /data-print-hide/);
  assert.match(TABLE_SOURCE, /data-print-only/);
  assert.match(TABLE_SOURCE, /renderTable\(visibleColumns\)/);
  assert.match(TABLE_SOURCE, /renderTable\(allColumns\)/);
});
