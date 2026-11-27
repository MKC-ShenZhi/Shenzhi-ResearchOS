"use client";

import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "../../../components/ui/button";

export function MessageCopyButton({ text, label = "复制回复" }: { text: string; label?: string }) {
  const [result, setResult] = useState<"success" | "error" | null>(null);
  const [copying, setCopying] = useState(false);
  useEffect(() => {
    if (!result) return;
    const timer = setTimeout(() => setResult(null), 2500);
    return () => clearTimeout(timer);
  }, [result]);

  async function copy() {
    setCopying(true);
    setResult(null);
    try {
      await navigator.clipboard.writeText(text);
      setResult("success");
    } catch {
      setResult("error");
    } finally {
      setCopying(false);
    }
  }

  return <>
    <Button type="button" variant="ghost" size="icon" className="text-muted" title={result === "success" ? "已复制" : label}
      aria-label={result === "success" ? "已复制" : label} disabled={copying} onClick={copy}>
      {result === "success" ? <Check aria-hidden="true" className="text-primary" /> : <Copy aria-hidden="true" />}
    </Button>
    <span role="status" aria-live="polite" className="text-xs text-muted">
      {result === "success" ? "已复制" : result === "error" ? "复制失败，请重试或手动复制" : ""}
    </span>
  </>;
}
