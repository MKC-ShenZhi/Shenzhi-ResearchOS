import { ExternalLink } from "lucide-react";
import type { Reference } from "../../../clients/backend/agent-message";
import type { CitationTarget } from "./citation-markers";
import { doiUrl, referenceAnchor, referenceDetails, REFERENCE_TYPE, safeReferenceUrl } from "./message-presentation";

export function ReferencesRenderer({ references, anchorPrefix, citations }: {
  references: readonly Reference[]; anchorPrefix: string; citations: readonly CitationTarget[];
}) {
  if (references.length === 0) return null;
  return (
    <section aria-label="参考来源" className="mt-5 border-t border-line pt-4">
      <h3 className="mb-1 text-sm font-semibold text-ink">参考来源（{references.length}）</h3>
      <ol className="divide-y divide-line">
        {references.map((reference) => {
          const number = citations.find((citation) => citation.id === reference.id)!.number;
          const href = safeReferenceUrl(reference.url) ?? doiUrl(reference.doi);
          const details = referenceDetails(reference);
          return (
            <li key={reference.id} id={referenceAnchor(anchorPrefix, number)} tabIndex={-1}
              className="flex scroll-mt-24 gap-2 rounded-lg py-3 outline-none target:bg-primary-soft/50 focus-visible:ring-2 focus-visible:ring-primary sm:gap-3">
              <span className="shrink-0 text-sm leading-6 text-muted">[{number}]</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-start gap-2 sm:gap-3">
                  <div className="min-w-0 flex-1 break-words text-sm font-semibold leading-6 text-ink">
                    {href ? <a href={href} target="_blank" rel="noopener noreferrer" className="hover:text-primary hover:underline">{reference.title}</a> : reference.title}
                  </div>
                  <span className="mt-0.5 shrink-0 rounded-full bg-chip px-2 py-0.5 text-[11px] font-normal text-ink-2">{REFERENCE_TYPE[reference.type]}</span>
                  {href && <a href={href} target="_blank" rel="noopener noreferrer"
                    aria-label={`打开来源：${reference.title}`} className="mt-1 shrink-0 text-muted hover:text-primary">
                    <ExternalLink className="size-4" aria-hidden />
                  </a>}
                </div>
                {details && <p className="mt-1 break-words text-xs leading-5 text-muted" title={reference.authors?.join("、")}>{details}</p>}
                {reference.doi && <p className="mt-0.5 break-all text-xs leading-5 text-muted">
                  <a href={doiUrl(reference.doi)!} target="_blank" rel="noopener noreferrer" className="hover:text-primary hover:underline">DOI：{reference.doi}</a>
                </p>}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
