"use client";

import { usePathname, useSearchParams } from "next/navigation";

/** Current same-origin route, including its query string when present. */
export function useCurrentInternalPath(): string {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const query = searchParams.toString();

  return query ? `${pathname}?${query}` : pathname;
}
