export function nsfcDirectoryHref(query = "", keyword = "") {
  const params = new URLSearchParams();
  if (query) params.set("projectQuery", query);
  if (keyword) params.set("keyword", keyword);
  return params.size ? `/knowledge/funding?${params}` : "/knowledge/funding";
}
