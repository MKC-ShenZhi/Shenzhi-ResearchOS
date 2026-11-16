"use client";

import type { ComponentProps } from "react";
import { FeatureNavigationLink } from "@/components/common/feature-availability-provider";
import { useSearchRestorationHref } from "@/hooks/use-search-restoration";

/** Opt-in navigation restoration; retains Next Link, keyboard and new-tab behavior. */
export function SearchNavigationLink({ href, ...props }: ComponentProps<typeof FeatureNavigationLink>) {
  const restoredHref = useSearchRestorationHref(href);
  return <FeatureNavigationLink {...props} href={restoredHref} />;
}
