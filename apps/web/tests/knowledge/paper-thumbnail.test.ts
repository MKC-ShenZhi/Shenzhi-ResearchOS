import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import test from "node:test";

import {
  getPaperThumbnailUrl,
} from "../../lib/paper-thumbnail.js";

const THUMBNAIL_SOURCE = readFileSync(
  "components/common/paper-thumbnail.tsx",
  "utf8",
);
const FALLBACK_PATH = "public/images/papers/paper-thumbnail-fallback.webp";

test("paper thumbnail falls back for missing or failed sources without retrying the fallback", () => {
  assert.match(
    THUMBNAIL_SOURCE,
    /normalizedSrc && failedSrc !== normalizedSrc[\s\S]*?PAPER_THUMBNAIL_FALLBACK_SRC/,
  );
  assert.match(
    THUMBNAIL_SOURCE,
    /if \(imageSrc !== PAPER_THUMBNAIL_FALLBACK_SRC\)[\s\S]*?setFailedSrc\(imageSrc\)/,
  );
  assert.match(THUMBNAIL_SOURCE, /className="object-contain"/);
});

test("paper thumbnail fallback is a lightweight WebP asset", () => {
  const fallback = readFileSync(FALLBACK_PATH);

  assert.equal(fallback.subarray(0, 4).toString("ascii"), "RIFF");
  assert.equal(fallback.subarray(8, 12).toString("ascii"), "WEBP");
  assert.ok(statSync(FALLBACK_PATH).size < 50 * 1024);
});

test("getPaperThumbnailUrl uses real identifiers only when explicitly enabled", () => {
  const originalValue = process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED;
  const cases = [
    "CVPR_2026/2605.05077v2.png",
    "ICLR_2026/2506.10941.png",
    "ECCV_2026/2607.00409v1.png",
    "pdf_backfill_2026/4640138e89cd36ec780b_b120a9db2fcd7145.jpg",
    "ASPLOS_2026/10.1145_3779212.3790216_minimal.jpg",
    "OTHER_2026/paper.jpeg", "OTHER_2026/paper.webp",
  ];
  try {
    for (const flag of [undefined, "false", "TRUE", "1"]) {
      if (flag === undefined) delete process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED;
      else process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED = flag;
      for (const path of cases) assert.equal(getPaperThumbnailUrl(`/images/${path}`), null);
    }
    process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED = "true";
    for (const path of cases) {
      assert.equal(getPaperThumbnailUrl(`/images/${path}`), `/api/paper-images/${path}`);
    }
    for (const value of [null, undefined, "", "paper:2605.05077v2", "/images/../secret.png",
      "/images/%2e%2e/secret.png", "/images/%252e%252e/secret.png", "/images//a.png",
      "/images/a.png?x=1", "/images/a.png#x", "/images/a.svg",
      "https://example.com/images/a.png", "/home/user2/jiansuo/images/a.png"]) {
      assert.equal(getPaperThumbnailUrl(value), null, String(value));
    }
  } finally {
    if (originalValue === undefined) delete process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED;
    else process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED = originalValue;
  }
});

test("PaperThumbnail renders the fallback with the flag off and after onError", async () => {
  // Execute the real component with a small hook/JSX harness, without adding a DOM dependency.
  const { runInNewContext } = await import("node:vm");
  const { transpileModule, ModuleKind, JsxEmit } = await import("typescript");
  type Element = { type: unknown; props: Record<string, unknown> };
  const states: unknown[] = [];
  let cursor = 0;
  const exports: Record<string, unknown> = {};
  const jsx = (type: unknown, props: Record<string, unknown>): Element => ({ type, props });
  const stubs: Record<string, unknown> = {
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "react": {
      useState: (initial: unknown) => {
        const index = cursor++;
        if (!(index in states)) states[index] = initial;
        return [states[index], (value: unknown) => { states[index] = value; }];
      },
      useRef: () => ({ current: null }),
    },
    "next/image": { default: "Image", __esModule: true },
    "lucide-react": { Maximize2: "Maximize2" },
    "@/components/common/paper-image-preview": { PaperImagePreview: "Preview" },
    "@/lib/utils": { cn: () => "" },
  };
  runInNewContext(transpileModule(THUMBNAIL_SOURCE, {
    compilerOptions: { module: ModuleKind.CommonJS, jsx: JsxEmit.ReactJSX },
  }).outputText, {
    exports,
    require: (name: string) => {
      assert.ok(name in stubs, `unexpected import ${name}`);
      return stubs[name];
    },
  });
  const Thumbnail = exports.PaperThumbnail as (props: { src: string | null; title: string }) => Element;
  const render = (src: string | null) => {
    cursor = 0;
    return Thumbnail({ src, title: "Test paper" }).props.children as Element[];
  };
  const originalValue = process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED;
  try {
    process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED = "false";
    let children = render(getPaperThumbnailUrl("/images/CVPR_2026/paper.png"));
    assert.equal(children[0].props.src, exports.PAPER_THUMBNAIL_FALLBACK_SRC);
    assert.equal(children[1], false);
    process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED = "true";
    const src = getPaperThumbnailUrl("/images/CVPR_2026/paper.png");
    children = render(src);
    assert.equal(children[0].props.src, "/api/paper-images/CVPR_2026/paper.png");
    (children[0].props.onError as () => void)();
    children = render(src);
    assert.equal(children[0].props.src, exports.PAPER_THUMBNAIL_FALLBACK_SRC);
    assert.equal(children[0].props.unoptimized, true);
    assert.equal(children[1], false);
    (children[0].props.onError as () => void)();
    assert.equal(render(src)[0].props.src, exports.PAPER_THUMBNAIL_FALLBACK_SRC);
    assert.equal(render(null)[0].props.src, exports.PAPER_THUMBNAIL_FALLBACK_SRC);
    assert.equal(render("/api/paper-images/ICLR_2026/new.png")[0].props.src,
      "/api/paper-images/ICLR_2026/new.png");
  } finally {
    if (originalValue === undefined) delete process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED;
    else process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED = originalValue;
  }
});
