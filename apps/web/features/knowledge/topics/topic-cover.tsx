"use client";

import Image from "next/image";
import { useState } from "react";

export function TopicCover({ topicId, name, eager = false, className = "" }: {
  topicId: string;
  name: string;
  eager?: boolean;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  // Match the filename-safe suffix used by the cover generator.
  const openAlexId = /^openalex:topic:(T[0-9]+)$/.exec(topicId)?.[1];
  return openAlexId && !failed ? (
    <Image
      src={`/topic-covers/${openAlexId}.webp`}
      alt={`${name}主题封面`}
      fill
      loading={eager ? "eager" : "lazy"}
      unoptimized
      className={`object-cover ${className}`}
      onError={() => setFailed(true)}
    />
  ) : (
    <div role="img" aria-label={`${name}默认封面`} className="absolute inset-0 bg-gradient-to-br from-primary/20 via-primary/5 to-brand-cyan/20" />
  );
}
