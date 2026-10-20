export interface FundingSearchParamsLike {
  get(name: string): string | null;
  toString(): string;
}

export interface FundingUrlState {
  query: string;
  fundingId: string | null;
}

export function readFundingUrlState(searchParams: FundingSearchParamsLike): FundingUrlState {
  const query = searchParams.get("q")?.trim() ?? "";
  const fundingId = searchParams.get("funding");
  return {
    query,
    fundingId: fundingId || null,
  };
}

export function buildFundingUrl(
  currentSearchParams: FundingSearchParamsLike,
  query: string,
  fundingId: string | null,
): string {
  const next = new URLSearchParams(currentSearchParams.toString());
  const normalizedQuery = query.trim();

  if (normalizedQuery) next.set("q", normalizedQuery);
  else next.delete("q");

  if (fundingId) next.set("funding", fundingId);
  else next.delete("funding");

  const serialized = next.toString();
  return `/knowledge/funding${serialized ? `?${serialized}` : ""}`;
}

export function fundingLibraryHref(query: string): string {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  return `/knowledge/funding${params.size ? `?${params}` : ""}`;
}

export function fundingDetailHref(id: string, name: string, query = ""): string {
  const params = new URLSearchParams({ name });
  if (query.trim()) params.set("q", query.trim());
  return `/knowledge/funding/${encodeURIComponent(id)}?${params}`;
}
