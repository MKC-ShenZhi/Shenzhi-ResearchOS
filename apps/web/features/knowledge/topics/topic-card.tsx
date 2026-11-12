"use client";

import Image from "next/image";
import Link from "next/link";
import { BookOpen, Network } from "lucide-react";
import { TopicCover } from "./topic-cover";
import { TopicFollowButton } from "@/features/knowledge/interactions/components/topic-follow-button";
import { TopicFollowerCount } from "@/features/knowledge/interactions/components/topic-follower-count";
import type { KnowledgeTopic } from "@/clients/knowledge";
import { topicHref } from "./topic-url-state";

function formatEnglishTitle(value: string) {
  const trimmed = value.trim();
  if (!trimmed || trimmed !== trimmed.toUpperCase()) return trimmed;

  return trimmed.split(/\s+/).map((word) => word.split("-").map((part) => {
    const normalized = part.toLocaleLowerCase();
    if (normalized.length <= 3) return normalized.toLocaleUpperCase();
    return `${normalized.slice(0, 1).toLocaleUpperCase()}${normalized.slice(1)}`;
  }).join("-")).join(" ");
}

function CreatorLogo() {
  return (
    <span className="flex size-4 shrink-0 items-center justify-center overflow-hidden rounded-full border border-line bg-panel">
      <Image src="/brand/logo-night.png" alt="" width={20} height={20} className="size-full object-contain dark:hidden" />
      <Image src="/brand/logo-day.png" alt="" width={20} height={20} className="hidden size-full object-contain dark:block" />
    </span>
  );
}

export function TopicCard({
  topic,
  returnTo,
  featured = false,
}: {
  topic: KnowledgeTopic;
  returnTo: string;
  featured?: boolean;
}) {
  const author = typeof topic.author === "string" ? { name: topic.author } : topic.author;
  const authorName = author?.name;
  const description = topic.descriptionZh || topic.descriptionEn;
  const href = topicHref(topic.id, returnTo);

  return (
    <article className="group flex h-full min-w-0 flex-col overflow-hidden rounded-2xl border border-line bg-card shadow-card transition duration-200 hover:-translate-y-0.5 hover:shadow-pop">
      <Link href={href} className="relative block aspect-[3.6/1] overflow-hidden bg-chip" aria-label={`查看主题：${topic.nameZh}`}>
        <TopicCover key={topic.id} topicId={topic.id} name={topic.nameZh} eager={featured} className="transition duration-500 group-hover:scale-[1.03]" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/10 to-transparent" />
        <div className="absolute bottom-3 left-4 flex size-11 items-center justify-center rounded-xl border border-line bg-card/90 text-primary shadow-sm backdrop-blur"><Network className="size-5" strokeWidth={1.8} aria-hidden="true" /></div>
      </Link>
      <div className="flex flex-1 flex-col p-3">
        <div className="mb-1.5 min-w-0"><Link href={href} className="block"><h3 className="truncate text-lg font-semibold leading-6 tracking-tight text-ink transition group-hover:text-primary">{topic.nameZh}</h3><p className="mt-0.5 truncate text-[11px] font-medium leading-4 tracking-[0.02em] text-muted">{formatEnglishTitle(topic.nameEn)}</p></Link></div>
        <p className="mb-2 line-clamp-2 min-h-10 text-[13px] leading-5 text-muted" title={description}>{description}</p>
        <div className="mb-2 min-h-7">{authorName && <span className="inline-flex h-7 items-center gap-2 rounded-lg bg-primary/8 px-2.5 text-xs text-primary" title={`创作者：${authorName}`}><CreatorLogo /><span>{authorName}</span></span>}</div>
        <div className="mt-auto flex items-center justify-between gap-2 border-t border-line/60 pt-2.5"><div className="flex min-w-0 items-center gap-2.5 text-xs text-muted"><span className="inline-flex items-center gap-1.5 whitespace-nowrap" title="目录收录时的论文统计"><BookOpen className="size-3.5" />目录统计 {topic.paperCount.toLocaleString()} 篇</span><TopicFollowerCount topicId={topic.id} className="whitespace-nowrap" /></div><TopicFollowButton topicId={topic.id} /></div>
      </div>
    </article>
  );
}

