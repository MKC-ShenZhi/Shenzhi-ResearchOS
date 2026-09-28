export interface KnowledgeFilters {
  yearFrom: number | null;
  yearTo: number | null;
  venue: string[];
  author: string[];
  keyword: string[];
  subject: string[];
}

export interface KnowledgeSearchParamsLike {
  get(name: string): string | null;
  getAll(name: string): string[];
}

export interface KnowledgeSearchUrlState {
  query: string;
  page: number;
  filters: KnowledgeFilters;
}

function readYear(value: string | null): number | null {
  if (!value) return null;
  const year = Number(value);
  return Number.isInteger(year) ? year : null;
}

function readPage(value: string | null): number {
  if (!value) return 1;
  const page = Number(value);
  return Number.isInteger(page) && page > 0 ? page : 1;
}

function readValues(searchParams: KnowledgeSearchParamsLike, name: string): string[] {
  return searchParams
    .getAll(name)
    .map((value) => value.trim())
    .filter((value, index, values) => value.length > 0 && values.indexOf(value) === index);
}

export function readKnowledgeSearchUrlState(
  searchParams: KnowledgeSearchParamsLike,
): KnowledgeSearchUrlState {
  return {
    query: searchParams.get("q")?.trim() ?? "",
    page: readPage(searchParams.get("page")),
    filters: {
      yearFrom: readYear(searchParams.get("yearFrom")),
      yearTo: readYear(searchParams.get("yearTo")),
      venue: readValues(searchParams, "venue"),
      author: readValues(searchParams, "author"),
      keyword: readValues(searchParams, "keyword"),
      subject: readValues(searchParams, "subject"),
    },
  };
}

function appendValues(params: URLSearchParams, name: string, values: string[]) {
  for (const value of values) {
    const normalized = value.trim();
    if (normalized) params.append(name, normalized);
  }
}

export function buildKnowledgeSearchUrl(state: KnowledgeSearchUrlState): string {
  const params = new URLSearchParams();
  const query = state.query.trim();

  if (query) params.set("q", query);
  if (query) params.set("page", String(Math.max(1, state.page)));
  if (state.filters.yearFrom !== null) {
    params.set("yearFrom", String(state.filters.yearFrom));
  }
  if (state.filters.yearTo !== null) {
    params.set("yearTo", String(state.filters.yearTo));
  }
  appendValues(params, "venue", state.filters.venue);
  appendValues(params, "author", state.filters.author);
  appendValues(params, "keyword", state.filters.keyword);
  appendValues(params, "subject", state.filters.subject);

  const serialized = params.toString();
  return `/knowledge/search${serialized ? `?${serialized}` : ""}`;
}
