export function nsfcDirectoryHref(query = "", page?: string | number, keyword = "") {
  const params = new URLSearchParams();
  if (query) params.set("projectQuery", query);
  if (keyword) params.set("keyword", keyword);
  if (page && page !== 1 && page !== "1") params.set("page", String(page));
  return params.size ? `/knowledge/funding?${params}` : "/knowledge/funding";
}
