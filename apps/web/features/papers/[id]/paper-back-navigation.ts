import { normalizeInternalReturnTo } from "../../../lib/navigation/internal-return-to";

export const PAPER_DETAIL_FALLBACK_ROUTE = "/";

type PaperBackRouter = {
  replace: (href: string) => void;
};

/** Return to an explicit same-origin route, or to the homepage for an unsafe/missing source. */
export function navigateBackFromPaper(router: PaperBackRouter, returnTo: unknown): void {
  router.replace(normalizeInternalReturnTo(returnTo) ?? PAPER_DETAIL_FALLBACK_ROUTE);
}
