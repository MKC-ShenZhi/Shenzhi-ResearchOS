"use client";

import { useState } from "react";
import { ComposerShell } from "./composer";

/** 底部提问输入框 —— 支持追问 / 上传 PDF / arXiv 链接 */
export function FollowUpInput() {
  const [value, setValue] = useState("");

  return (
    <div className="sticky bottom-4">
      <ComposerShell
        value={value}
        onChange={setValue}
        onSend={() => setValue("")}
        placeholder="继续提问,或上传 PDF / arXiv 链接以扩展上下文…"
      />
      <p className="mt-2 text-[11px] text-faint">
        支持上传 PDF / arXiv 链接 · 对话可保存到知识库 · 引用 [N] 可点击跳转
      </p>
    </div>
  );
}
