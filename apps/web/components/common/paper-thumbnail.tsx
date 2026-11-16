"use client";

import Image from "next/image";
import { Maximize2 } from "lucide-react";
import { useRef, useState } from "react";

import { PaperImagePreview } from "@/components/common/paper-image-preview";
import { cn } from "@/lib/utils";

export const PAPER_THUMBNAIL_FALLBACK_SRC =
  "/images/papers/paper-thumbnail-fallback.webp";

interface PaperThumbnailProps {
  src?: string | null;
  title: string;
  className?: string;
  eager?: boolean;
  /** Optional frame ratio; otherwise adapt to the loaded figure as before. */
  aspectRatio?: number;
}

/** Preserve complete figures in a landscape frame, with a local fallback. */
export function PaperThumbnail({ src, title, className, eager = false, aspectRatio }: PaperThumbnailProps) {
  const normalizedSrc = src?.trim() || null;
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const [loadedImage, setLoadedImage] = useState<{ src: string; ratio: number } | null>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const [preview, setPreview] = useState<{ src: string; thumbnail: string | null } | null>(null);
  const imageSrc =
    normalizedSrc && failedSrc !== normalizedSrc
      ? normalizedSrc
      : PAPER_THUMBNAIL_FALLBACK_SRC;
  const isFallback = imageSrc === PAPER_THUMBNAIL_FALLBACK_SRC;
  // Give taller figures more height without letting extreme ratios dominate a card.
  const adaptiveAspectRatio = !isFallback && loadedImage?.src === imageSrc
    ? Math.max(4 / 3, Math.min(2, loadedImage.ratio))
    : 16 / 10;

  return (
    <div
      className={cn(
        "group relative w-full overflow-hidden rounded-xl bg-chip",
        className,
      )}
      style={{ aspectRatio: aspectRatio ?? adaptiveAspectRatio }}
    >
      <Image
        ref={imageRef}
        src={imageSrc}
        alt={`${title} 的论文缩略图`}
        fill
        sizes="320px"
        loading={eager ? "eager" : "lazy"}
        className="object-contain"
        unoptimized={isFallback}
        onLoad={(event) => {
          if (!isFallback && aspectRatio === undefined) {
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
        <button
          type="button"
          onClick={() => {
            const image = imageRef.current;
            setPreview({
              src: imageSrc,
              thumbnail: image?.complete && image.naturalWidth > 0 ? image.currentSrc : null,
            });
          }}
          aria-label={`查看 ${title} 的原图`}
          aria-haspopup="dialog"
          className="absolute inset-0 cursor-zoom-in rounded-xl focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
        >
          <span className="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-md bg-card/95 px-2 py-1 text-xs text-ink opacity-0 shadow-card transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            <Maximize2 className="size-3" />
            查看原图
          </span>
        </button>
      )}
      {!isFallback && preview?.src === imageSrc && (
        <PaperImagePreview
          key={imageSrc}
          src={imageSrc}
          previewSrc={preview.thumbnail}
          title={title}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}
