export const COMING_SOON_MESSAGE = "功能暂未上线";

export const COMING_SOON_NOTICE = {
  param: "notice",
  value: "coming-soon",
} as const;

/**
 * V1 暂未开放的路由集中配置。
 *
 * exactPaths 只匹配完整路径，避免误伤已上线的论文关系图谱；
 * pathPrefixes 同时匹配栏目首页和其下的全部子路由。
 */
export const FEATURE_AVAILABILITY = {
  exactPaths: ["/knowledge/graph"],
  pathPrefixes: ["/projects", "/submit"],
  agentSessionPath: "/agents",
} as const;

type SearchParamsReader = Pick<URLSearchParams, "get">;

function isPathOrDescendant(pathname: string, prefix: string) {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/** `/agents?session=...` 是已上线的 Session Chat，其余 Agent 页面暂不开放。 */
export function isUnavailableFeatureRoute(
  pathname: string,
  searchParams: SearchParamsReader = new URLSearchParams(),
) {
  if (FEATURE_AVAILABILITY.exactPaths.some((path) => pathname === path)) {
    return true;
  }

  if (
    FEATURE_AVAILABILITY.pathPrefixes.some((prefix) =>
      isPathOrDescendant(pathname, prefix),
    )
  ) {
    return true;
  }

  if (pathname === FEATURE_AVAILABILITY.agentSessionPath) {
    return !searchParams.get("session");
  }

  return pathname.startsWith(`${FEATURE_AVAILABILITY.agentSessionPath}/`);
}

export function isUnavailableFeatureHref(href: string) {
  if (!href.startsWith("/") || href.startsWith("//")) return false;

  const url = new URL(href, "https://shenzhi.local");
  return isUnavailableFeatureRoute(url.pathname, url.searchParams);
}

export function comingSoonRedirectPath() {
  const searchParams = new URLSearchParams({
    [COMING_SOON_NOTICE.param]: COMING_SOON_NOTICE.value,
  });
  return `/?${searchParams.toString()}`;
}
