"use client";

import Image from "next/image";
import { Maximize2 } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

export const PAPER_THUMBNAIL_FALLBACK_SRC =
  "/images/papers/paper-thumbnail-fallback.webp";

interface PaperThumbnailProps {
  src?: string | null;
  title: string;
  className?: string;
}

/** Preserve complete figures in a landscape frame, with a local fallback. */
export function PaperThumbnail({ src, title, className }: PaperThumbnailProps) {
  const normalizedSrc = src?.trim() || null;
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const [loadedImage, setLoadedImage] = useState<{ src: string; ratio: number } | null>(null);
  const imageSrc =
    normalizedSrc && failedSrc !== normalizedSrc
      ? normalizedSrc
      : PAPER_THUMBNAIL_FALLBACK_SRC;
  const isFallback = imageSrc === PAPER_THUMBNAIL_FALLBACK_SRC;
  // Give taller figures more height without letting extreme ratios dominate a card.
  const aspectRatio = !isFallback && loadedImage?.src === imageSrc
    ? Math.max(4 / 3, Math.min(2, loadedImage.ratio))
    : 16 / 10;

  return (
    <div
      className={cn(
        "group relative w-full overflow-hidden rounded-xl bg-chip",
        className,
      )}
      style={{ aspectRatio }}
    >
      <Image
        src={imageSrc}
        alt={`${title} 的论文缩略图`}
        fill
        sizes="(min-width: 640px) 320px, 100vw"
        className="object-contain"
        unoptimized
        onLoad={(event) => {
          if (!isFallback) {
            const { naturalWidth, naturalHeight } = event.currentTarget;
            if (naturalHeight > 0) {
              setLoadedImage({ src: imageSrc, ratio: naturalWidth / naturalHeight });
            }
          }
        }}
        onError={() => {
          if (imageSrc !== PAPER_THUMBNAIL_FALLBACK_SRC) {
            setFailedSrc(imageSrc);
          }
        }}
      />
      {!isFallback && (
        <a
          href={imageSrc}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`查看 ${title} 的原图（新标签页）`}
          className="absolute inset-0 rounded-xl focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
        >
          <span className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-md bg-card/95 px-2 py-1 text-xs text-ink opacity-0 shadow-card transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            <Maximize2 className="size-3" />
            查看原图
          </span>
        </a>
      )}
    </div>
  );
}
