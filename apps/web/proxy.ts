import { type NextRequest, NextResponse } from "next/server";
import {
  comingSoonRedirectPath,
  isUnavailableFeatureRoute,
} from "@/lib/feature-availability";

export function proxy(request: NextRequest) {
  if (
    !isUnavailableFeatureRoute(
      request.nextUrl.pathname,
      request.nextUrl.searchParams,
    )
  ) {
    return NextResponse.next();
  }

  return NextResponse.redirect(new URL(comingSoonRedirectPath(), request.url));
}

export const config = {
  matcher: [
    "/agents/:path*",
    "/knowledge/graph",
    "/projects/:path*",
    "/submit/:path*",
  ],
};
