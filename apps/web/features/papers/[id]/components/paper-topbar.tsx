"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { ArrowLeft, Network } from "lucide-react";
import type { KnowledgePaperDetail } from "@/clients/knowledge";
import { paperHref } from "@/lib/navigation/paper";
import { navigateBackFromPaper } from "../paper-back-navigation";

export function PaperBackButton({ returnTo }: { returnTo?: string | null }) {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => navigateBackFromPaper(router, returnTo)}
      className="inline-flex items-center gap-1"
    >
      <ArrowLeft className="size-4" />
      返回
    </button>
  );
}

export function PaperTopbar({
  paper,
  returnTo,
  children,
}: {
  paper: KnowledgePaperDetail;
  returnTo?: string | null;
  children: ReactNode;
}) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-line bg-card px-4">
      <div className="flex min-w-0 items-center gap-3 text-xs text-primary">
        <PaperBackButton returnTo={returnTo} />
        {children}
      </div>
      <Link
        href={paperHref(paper.id, { mode: "preserve", returnTo, graph: true })}
        className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1.5 text-xs text-primary hover:bg-chip"
      >
        <Network className="size-4" />关系图谱
      </Link>
    </header>
  );
}
