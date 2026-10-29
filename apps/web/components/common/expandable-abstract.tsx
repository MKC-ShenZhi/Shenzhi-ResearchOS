"use client";

import { useEffect, useId, useRef, useState } from "react";
import { recordPaperBehavior } from "@/clients/backend/behavior";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type BehaviorSource = "discovery" | "recommendation" | "search" | "paper_detail";

export function ExpandableAbstract({
  abstract,
  paperId,
  source,
  userId,
  className,
  collapsedClassName,
}: {
  abstract: string;
  paperId: string;
  source: BehaviorSource;
  /** Signed-in owner for the positive-intent event; empty for anonymous readers. */
  userId: string;
  className?: string;
  collapsedClassName: string;
}) {
  const abstractId = useId();
  const abstractRef = useRef<HTMLParagraphElement>(null);
  const reportedRef = useRef(false);
  const [expanded, setExpanded] = useState(false);
  const [canExpand, setCanExpand] = useState(false);

  useEffect(() => {
    const element = abstractRef.current;
    if (!element) return;

    const measureOverflow = () => {
      setCanExpand(expanded || element.scrollHeight > element.clientHeight + 1);
    };
    measureOverflow();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measureOverflow);
      return () => window.removeEventListener("resize", measureOverflow);
    }
    const observer = new ResizeObserver(measureOverflow);
    observer.observe(element);
    return () => observer.disconnect();
  }, [abstract, collapsedClassName, expanded]);

  if (!abstract.trim()) return null;

  const toggleExpanded = () => {
    if (userId && !expanded && !reportedRef.current) {
      recordPaperBehavior({ userId, eventType: "abstract_expand", paperId, source });
      reportedRef.current = true;
    }
    setExpanded((current) => !current);
  };

  return (
    <div>
      <p
        ref={abstractRef}
        id={abstractId}
        className={cn(className, !expanded && collapsedClassName)}
      >
        {abstract}
      </p>
      {canExpand && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="mt-1 h-7 px-0 text-xs text-primary hover:bg-transparent hover:underline"
          aria-expanded={expanded}
          aria-controls={abstractId}
          onClick={toggleExpanded}
        >
          {expanded ? "收起摘要" : "展开摘要"}
        </Button>
      )}
    </div>
  );
}
