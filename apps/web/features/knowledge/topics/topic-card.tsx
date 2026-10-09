"use client";

import Image from "next/image";
import Link from "next/link";
import { BookOpen, BrainCircuit, Languages, Network, Plus, Sparkles, Users } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { KnowledgeTopic } from "@/clients/knowledge";

const categoryIcons = { "机器学习": BrainCircuit, "自然语言处理": Languages } as const;

function TopicIcon({ category }: { category: string }) {
  const Icon = categoryIcons[category as keyof typeof categoryIcons] ?? Network;
  return <Icon className="size-5" strokeWidth={1.8} />;
}

export function TopicCard({ topic, featured = false }: { topic: KnowledgeTopic; featured?: boolean }) {
  const [imageFailed, setImageFailed] = useState(false);
  return (
    <article className="group flex min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card transition duration-200 hover:-translate-y-0.5 hover:shadow-pop">
      <Link href={`/knowledge/topics/${encodeURIComponent(topic.id)}`} className="relative block aspect-[3/1] overflow-hidden bg-muted/20" aria-label={`查看主题：${topic.nameZh}`}>
        {!imageFailed && topic.imagePath ? <Image src={topic.imagePath} alt="" fill sizes={featured ? "(max-width: 768px) 100vw, 50vw" : "(max-width: 768px) 100vw, 33vw"} className="object-cover transition duration-500 group-hover:scale-[1.03]" onError={() => setImageFailed(true)} /> : <div className="h-full w-full bg-gradient-to-br from-primary/20 via-primary/5 to-accent/20" />}
        <div className="absolute inset-0 bg-gradient-to-t from-black/10 to-transparent" />
        <div className="absolute bottom-3 left-4 flex size-11 items-center justify-center rounded-xl border border-white/70 bg-white/90 text-primary shadow-sm backdrop-blur"><TopicIcon category={topic.category} /></div>
      </Link>
      <div className="flex flex-1 flex-col p-5">
        <div className="mb-3 flex items-start justify-between gap-3"><div className="min-w-0"><Link href={`/knowledge/topics/${encodeURIComponent(topic.id)}`} className="block"><h3 className="truncate text-lg font-semibold tracking-tight text-foreground transition group-hover:text-primary">{topic.nameZh}</h3><p className="mt-0.5 truncate text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">{topic.nameEn}</p></Link></div><span className="shrink-0 rounded-full bg-primary/8 px-2.5 py-1 text-xs font-medium text-primary">{topic.category}</span></div>
        <p className="mb-3 line-clamp-2 min-h-10 text-sm leading-5 text-muted-foreground">{topic.descriptionZh}</p>
        <p className="mb-5 flex items-center gap-1.5 text-xs text-muted-foreground"><Sparkles className="size-3.5 text-primary/70" />由 <span className="font-medium text-foreground">{topic.author}</span> 初期维护</p>
        <div className="mt-auto flex items-center justify-between gap-3 border-t border-border/80 pt-4"><div className="flex items-center gap-3 text-xs text-muted-foreground"><span className="inline-flex items-center gap-1.5" title="关联论文数量"><BookOpen className="size-3.5" />{topic.paperCount.toLocaleString()} 篇</span><span className="inline-flex items-center gap-1.5" title="关注人数"><Users className="size-3.5" />{topic.followersCount.toLocaleString()}</span></div><Button type="button" variant="outline" size="sm" disabled title="关注功能将在后续版本开放"><Plus className="size-3.5" />关注</Button></div>
      </div>
    </article>
  );
}

