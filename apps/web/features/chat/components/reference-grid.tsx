"use client";

import Link from "next/link";
import { useState } from "react";
import { ExternalLink, FileText, Globe } from "lucide-react";
import type { ChatReference, KnowledgeGroundingState } from "@/types/ai-search";
import { cn } from "@/lib/utils";
import { useCurrentInternalPath } from "@/hooks/use-current-internal-path";
import {
  citedReferenceIds,
  paperReferenceHref,
  referenceIdOf,
  resourceIdOf,
  resourceTypeOf,
} from "../services/reference-navigation";
import { useCitation } from "./citations";

function displayAuthors(reference: ChatReference): string {
  return reference.metadata?.authors?.join(" · ") ?? reference.authors ?? "";
}

/** B's real-source grid; deliberately no mock fallback for an empty result. */
export function ReferenceGrid({
  references,
  answer,
  knowledgeGrounding,
}: {
  references: ChatReference[];
  answer: string;
  knowledgeGrounding?: KnowledgeGroundingState;
}) {
  const [all, setAll] = useState(false);
  const { active, jump } = useCitation();
  const returnTo = useCurrentInternalPath();
  if (!references.length) return null;

  const citedIds = new Set(citedReferenceIds(answer, references));
  const degraded = knowledgeGrounding === "unavailable" || knowledgeGrounding === "unverified";
  const citedReferences = references.filter((reference) => {
    const referenceId = referenceIdOf(reference);
    return referenceId !== null && citedIds.has(referenceId);
  });
  const displayedReferences = degraded || all ? references : citedReferences;
  const hasUncitedEvidence = citedReferences.length < references.length;

  return (
    <section className="mt-4 rounded-2xl border border-line bg-card p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium">
            {degraded ? "检索资料" : `引用来源 · ${citedReferences.length}`}
          </h3>
          {knowledgeGrounding === "unverified" && (
            <p className="mt-1 text-xs text-muted">检索资料未用于形成可验证引用</p>
          )}
          {knowledgeGrounding === "unavailable" && (
            <p className="mt-1 text-xs text-muted">本轮未使用知识底座资料</p>
          )}
        </div>
        {!degraded && hasUncitedEvidence && (
          <button
            type="button"
            onClick={() => setAll(!all)}
            className="text-xs text-primary"
          >
            {all ? "收起检索资料" : `查看全部检索资料（${references.length}）`}
          </button>
        )}
      </div>

      {displayedReferences.length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {displayedReferences.map((ref) => {
            const referenceId = referenceIdOf(ref);
            const ordinal = referenceId ? Number(referenceId) : NaN;
            const canFocus = !degraded && Number.isInteger(ordinal) && ordinal > 0;
            const resourceType = resourceTypeOf(ref);
            const resourceId = resourceIdOf(ref);
            const detailHref = paperReferenceHref(ref, returnTo);
            const venue = ref.metadata?.venue ?? ref.venue;
            const url = resourceType !== "paper" && ref.url && /^https?:\/\//i.test(ref.url)
              ? ref.url
              : undefined;
            const Icon = resourceType === "web" ? Globe : FileText;
            const kindLabel = resourceType === "web"
              ? "网页"
              : resourceType === "paper"
                ? "论文"
                : "资料";
            const cardKey = `${referenceId ?? "unknown"}-${resourceId ?? "missing"}`;

            return (
              <article
                key={cardKey}
                data-source-citation={canFocus ? ordinal : undefined}
                className={cn(
                  "rounded-xl border border-line p-3",
                  canFocus && active === ordinal && "border-primary bg-primary-soft",
                )}
              >
                {canFocus ? (
                  <button
                    type="button"
                    onClick={() => jump(ordinal, "text")}
                    className="w-full text-left"
                    aria-label={`定位正文引用 ${referenceId}`}
                  >
                    <span className="text-xs text-primary">
                      {degraded ? `资料 ${referenceId}` : `[${referenceId}]`} <Icon className="inline size-3" /> {kindLabel}
                    </span>
                  </button>
                ) : (
                  <span className="text-xs text-muted">
                    {referenceId ? `${degraded ? "资料 " : "["}${referenceId}${degraded ? "" : "]"} ` : ""}
                    <Icon className="inline size-3" /> {kindLabel}
                  </span>
                )}

                {detailHref ? (
                  <Link
                    href={detailHref}
                    className="group mt-1 block line-clamp-2 text-[13px] font-medium"
                  >
                    <span className="transition-colors group-hover:text-primary">{ref.title}</span>
                  </Link>
                ) : (
                  <span className="mt-1 block line-clamp-2 text-[13px] font-medium">{ref.title}</span>
                )}
                <p className="mt-1 truncate text-xs text-muted">
                  {[displayAuthors(ref), venue].filter(Boolean).join(" · ")}
                </p>
                {url && (
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-xs text-primary"
                  >
                    打开来源 <ExternalLink className="size-3" />
                  </a>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
