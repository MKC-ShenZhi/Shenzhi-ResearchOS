/** Shared by the URL resolver and resource route; never decode a second time. */
export function isPaperImagePath(path: string[]): boolean {
  return path.length > 0 && path.length <= 16 &&
    path.every((part) => part.length <= 255 && /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(part)) &&
    /\.(png|jpe?g|webp)$/i.test(path[path.length - 1]);
}

/** Adapt only real upstream image identifiers; paper ids remain opaque. */
export function getPaperThumbnailUrl(imageId: string | null | undefined): string | null {
  if (process.env.NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED !== "true" ||
      !imageId?.startsWith("/images/")) {
    return null;
  }

  const path = imageId.slice("/images/".length).split("/");
  return isPaperImagePath(path) ? `/api/paper-images/${path.join("/")}` : null;
}
