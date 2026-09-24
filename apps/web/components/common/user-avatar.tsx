"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

export function UserAvatar({
  src,
  name,
  alt,
  className,
}: {
  src: string | null;
  name: string;
  alt: string;
  className?: string;
}) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const showImage = Boolean(src && failedSrc !== src);
  const initial = name.trim().slice(0, 1) || "?";

  return (
    <span
      role="img"
      aria-label={alt}
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary-soft font-semibold text-primary",
        className,
      )}
    >
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element -- Better Auth may provide an external avatar URL.
        <img
          src={src ?? undefined}
          alt=""
          className="size-full object-cover"
          onError={() => setFailedSrc(src)}
        />
      ) : (
        <span aria-hidden="true">{initial}</span>
      )}
    </span>
  );
}
