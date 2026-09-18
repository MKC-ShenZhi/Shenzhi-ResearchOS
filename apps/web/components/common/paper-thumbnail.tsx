"use client";

import Image from "next/image";
import { useState } from "react";

import { cn } from "@/lib/utils";

export const PAPER_THUMBNAIL_FALLBACK_SRC =
  "/images/papers/paper-thumbnail-fallback.webp";

interface PaperThumbnailProps {
  src?: string | null;
  title: string;
  className?: string;
}

/** Shared paper image with a local fallback for missing or failed sources. */
export function PaperThumbnail({ src, title, className }: PaperThumbnailProps) {
  const normalizedSrc = src?.trim() || null;
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const imageSrc =
    normalizedSrc && failedSrc !== normalizedSrc
      ? normalizedSrc
      : PAPER_THUMBNAIL_FALLBACK_SRC;

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl bg-chip",
        className,
      )}
    >
      <Image
        src={imageSrc}
        alt={`${title} 的论文缩略图`}
        fill
        sizes="(min-width: 768px) 200px, 168px"
        className="object-cover"
        unoptimized
        onError={() => {
          if (imageSrc !== PAPER_THUMBNAIL_FALLBACK_SRC) {
            setFailedSrc(imageSrc);
          }
        }}
      />
    </div>
  );
}
