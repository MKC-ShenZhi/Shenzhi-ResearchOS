"use client";

import Image from "next/image";
import { useState } from "react";

export function TopicCover({ imagePath, name, sizes, eager = false, className = "" }: {
  imagePath: string | null;
  name: string;
  sizes: string;
  eager?: boolean;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  return imagePath && !failed ? (
    <Image src={imagePath} alt={`${name}主题封面`} fill sizes={sizes} loading={eager ? "eager" : "lazy"} className={`object-cover ${className}`} onError={() => setFailed(true)} />
  ) : (
    <div role="img" aria-label={`${name}默认封面`} className="absolute inset-0 bg-gradient-to-br from-primary/20 via-primary/5 to-accent/20" />
  );
}
