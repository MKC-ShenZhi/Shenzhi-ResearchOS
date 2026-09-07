"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { knowledgePaginationItems } from "../pagination";

export function KnowledgeSearchPagination({
  page,
  hasMore,
  onPageChange,
}: {
  page: number;
  hasMore: boolean;
  onPageChange: (page: number) => void;
}) {
  const items = knowledgePaginationItems(page, hasMore);

  return (
    <nav className="flex items-center justify-center gap-1.5 pt-2" aria-label="论文检索分页">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onPageChange(page - 1)}
        disabled={page === 1}
        aria-label="上一页"
      >
        <ChevronLeft />
        上一页
      </Button>

      {items.map((item, index) =>
        item === "ellipsis" ? (
          <span key={`ellipsis-${index}`} className="px-1 text-sm text-faint" aria-hidden="true">
            …
          </span>
        ) : (
          <Button
            key={item}
            type="button"
            variant={item === page ? "default" : "outline"}
            size="icon"
            className="size-8"
            onClick={() => onPageChange(item)}
            aria-label={`第 ${item} 页`}
            aria-current={item === page ? "page" : undefined}
          >
            {item}
          </Button>
        ),
      )}

      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onPageChange(page + 1)}
        disabled={!hasMore}
        aria-label="下一页"
      >
        下一页
        <ChevronRight />
      </Button>
    </nav>
  );
}
