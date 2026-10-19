"use client";

import Image from "next/image";
import Link from "next/link";
import { AudioLines, BookOpen, Boxes, BrainCircuit, Bot, Check, Eye, Languages, Network, Plus, Sparkles, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { TopicCover } from "./topic-cover";
import { Button } from "@/components/ui/button";
import type { KnowledgeTopic } from "@/clients/knowledge";
import { useUserPreferences } from "@/stores/user-preferences";
import { topicHref } from "./topic-url-state";

const categoryIcons: Record<string, LucideIcon> = {
  "机器学习": BrainCircuit,
  "自然语言处理": Languages,
  "大语言模型": Languages,
  "智能体": Bot,
  "计算机视觉": Eye,
  "语音/音频处理": AudioLines,
  "生成式AI": Sparkles,
  "多模态": Boxes,
  network: Network,
  brain: BrainCircuit,
  language: Languages,
};

function TopicIcon({ category, iconKey }: { category: string; iconKey?: string | null }) {
  const Icon = (iconKey ? categoryIcons[iconKey] : undefined) ?? categoryIcons[category] ?? Network;
  return <Icon className="size-5" strokeWidth={1.8} />;
}

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
    <span className="flex size-4 shrink-0 items-center justify-center overflow-hidden rounded-full border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
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
  const following = useUserPreferences((state) => state.followedTopics[topic.id] ?? topic.isFollowing ?? false);
  const toggleTopicFollow = useUserPreferences((state) => state.toggleTopicFollow);
  const author = typeof topic.author === "string" ? { name: topic.author } : topic.author;
  const authorName = author.name.toLocaleLowerCase() === "shenzhi" ? "ShenZhi" : author.name;
  const href = topicHref(topic.id, returnTo);

  return (
    <article className="group flex h-full min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_2px_8px_rgba(23,33,43,0.05)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_10px_28px_rgba(23,33,43,0.10)]">
      <Link href={href} className="relative block aspect-[3.6/1] overflow-hidden bg-slate-100" aria-label={`查看主题：${topic.nameZh}`}>
        <TopicCover key={topic.imagePath} imagePath={topic.imagePath} name={topic.nameZh} sizes={featured ? "(max-width: 768px) 100vw, 50vw" : "(max-width: 768px) 100vw, 33vw"} eager={featured} className="transition duration-500 group-hover:scale-[1.03]" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/10 to-transparent" />
        <div className="absolute bottom-3 left-4 flex size-11 items-center justify-center rounded-xl border border-white/80 bg-white/90 text-primary shadow-sm backdrop-blur"><TopicIcon category={topic.category} iconKey={topic.iconKey} /></div>
      </Link>
      <div className="flex flex-1 flex-col p-3">
        <div className="mb-1.5 min-w-0"><Link href={href} className="block"><h3 className="truncate text-lg font-semibold leading-6 tracking-tight text-foreground transition group-hover:text-primary">{topic.nameZh}</h3><p className="mt-0.5 truncate text-[11px] font-medium leading-4 tracking-[0.02em] text-muted-foreground">{formatEnglishTitle(topic.nameEn)}</p></Link></div>
        <p className="mb-2 line-clamp-2 min-h-10 text-[13px] leading-5 text-muted-foreground" title={topic.descriptionZh}>{topic.descriptionZh}</p>
        <div className="mb-2"><span className="inline-flex h-7 items-center gap-2 rounded-lg bg-primary/8 px-2.5 text-xs text-primary" title={`创作者：${authorName}`}><CreatorLogo /><span>{authorName}</span></span></div>
        <div className="mt-auto flex items-center justify-between gap-2 border-t border-slate-100 pt-2.5"><div className="flex min-w-0 items-center gap-2.5 text-xs text-muted-foreground"><span className="inline-flex items-center gap-1.5 whitespace-nowrap" title="目录收录时的论文统计"><BookOpen className="size-3.5" />目录统计 {topic.paperCount.toLocaleString()} 篇</span><span className="inline-flex items-center gap-1.5 whitespace-nowrap" title="关注人数"><Users className="size-3.5" />{topic.followersCount.toLocaleString()} 人关注</span></div><Button type="button" variant={following ? "soft" : "default"} size="sm" aria-pressed={following} onClick={() => toggleTopicFollow(topic.id, topic.isFollowing)} title={following ? "取消关注主题" : "关注主题"}>{following ? <Check className="size-3.5" /> : <Plus className="size-3.5" />}{following ? "已关注" : "关注"}</Button></div>
      </div>
    </article>
  );
}

