import type { KnowledgeConference } from "../../../../clients/knowledge/types";
import { buildPaperBrowseUrl, readPaperBrowseState, resolveConference, resolveConferenceYear } from "./conference-state";

export interface BrowseNavigationBrowser {
  location: Pick<Location, "pathname" | "search" | "hash">;
  history: Pick<History, "pushState" | "replaceState">;
}

type BrowseChange = { conference: string } | { year: number } | { page: number };

function writeUrl(browser: BrowseNavigationBrowser, href: string, replace = false) {
  const { pathname, search, hash } = browser.location;
  if (href === `${pathname}${search}${hash}`) return;
  // Next integrates native History with useSearchParams. These filters only
  // change the client query; waiting for an RSC navigation leaves old UI active.
  browser.history[replace ? "replaceState" : "pushState"](null, "", href);
}

/** Read the live URL so consecutive clicks cannot reuse an old render's meeting. */
export function updateConferenceBrowse(items: KnowledgeConference[], change: BrowseChange, browser: BrowseNavigationBrowser = window): void {
  if (browser.location.pathname !== "/knowledge/search") return;
  const state = readPaperBrowseState(new URLSearchParams(browser.location.search));
  if (state.mode !== "conference") return;
  const selected = resolveConference(items, "conference" in change ? change.conference : state.conference);
  if (!selected) return;
  const year = resolveConferenceYear(selected, "conference" in change ? 0 : "year" in change ? change.year : state.year);
  if (!year) return;
  const page = "page" in change ? change.page : 1;
  writeUrl(browser, buildPaperBrowseUrl(selected.name, year, page));
}

/** Effects may run after a newer click; normalize the current URL, not a closure. */
export function normalizeConferenceBrowse(items: KnowledgeConference[], browser: BrowseNavigationBrowser = window): void {
  if (browser.location.pathname !== "/knowledge/search") return;
  const state = readPaperBrowseState(new URLSearchParams(browser.location.search));
  if (state.mode !== "conference") return;
  const selected = resolveConference(items, state.conference);
  if (!selected) return;
  const year = resolveConferenceYear(selected, state.year);
  if (year && (state.conference !== selected.name || state.year !== year)) {
    const page = year === state.year ? state.page : 1;
    writeUrl(browser, buildPaperBrowseUrl(selected.name, year, page), true);
  }
}
