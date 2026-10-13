"use client";

import Link from "next/link";
import { ArrowLeft, RotateCw, Tag } from "lucide-react";
import { KnowledgeClientError } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { TopicCover } from "../topic-cover";
import { TopicRelatedPapers } from "./topic-related-papers";
import { useTopicDetail } from "./use-topic-detail";

export function TopicDetailPage({ topicId }: { topicId: string }) {
  const { data: topic, error, isPending, isError, refetch } =
    useTopicDetail(topicId);

  if (isPending && !topic) {
    return (
      <main className="min-h-screen bg-background px-4 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[980px] animate-pulse">
          <div className="h-5 w-28 rounded bg-muted" />
          <div className="mt-8 rounded-3xl border border-line p-8">
            <div className="h-6 w-24 rounded-full bg-muted" />
            <div className="mt-5 h-10 w-2/3 rounded bg-muted" />
            <div className="mt-3 h-5 w-1/2 rounded bg-muted" />
            <div className="mt-7 h-24 rounded bg-muted" />
          </div>
        </div>
      </main>
    );
  }

  if (isError && !topic) {
    const notFound =
      error instanceof KnowledgeClientError && error.code === "NOT_FOUND";

    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-6">
        <div className="max-w-md text-center">
          <h1 className="text-2xl font-semibold text-foreground">
            {notFound ? "没有找到这个主题" : "主题加载失败"}
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            {notFound
              ? "该主题可能已下线，或者链接中的主题编号不正确。"
              : "暂时无法取得主题信息，请稍后重新尝试。"}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href="/knowledge/topics"
              className="inline-flex h-9 items-center rounded-lg border border-line px-4 text-sm font-medium text-foreground"
            >
              返回主题广场
            </Link>
            {!notFound ? (
              <Button type="button" size="sm" onClick={() => void refetch()}>
                <RotateCw className="size-3.5" />
                重新加载
              </Button>
            ) : null}
          </div>
        </div>
      </main>
    );
  }

  if (!topic) return null;

  const description =
    topic.descriptionDetail?.trim() ||
    topic.descriptionZh.trim() ||
    topic.descriptionEn.trim();

  return (
    <main className="min-h-screen bg-background px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[980px]">
        <Link
          href="/knowledge/topics"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground transition hover:text-primary"
        >
          <ArrowLeft className="size-4" />
          返回主题广场
        </Link>

        <article className="mt-5 overflow-hidden rounded-3xl border border-line bg-card shadow-[0_8px_30px_rgba(23,33,43,0.06)]">
          <div className="relative aspect-[3.6/1] bg-muted">
            <TopicCover key={topic.imagePath} imagePath={topic.imagePath} name={topic.nameZh} sizes="(max-width: 980px) 100vw, 980px" eager />
          </div>
          <div className="p-6 sm:p-8">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
              <Tag className="size-3.5" />
              {topic.category}
            </span>

            <h1 className="mt-5 text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              {topic.nameZh}
            </h1>
            <p className="mt-2 text-base font-medium text-muted-foreground">
              {topic.nameEn}
            </p>
            <p className="mt-6 whitespace-pre-line text-sm leading-7 text-muted-foreground sm:text-base">
              {description}
            </p>

            <div className="mt-7 flex flex-wrap gap-3 border-t border-line pt-5 text-sm text-muted-foreground">
              <span>创建者：{typeof topic.author === "string" ? topic.author : topic.author.name}</span>
              <span className="rounded-full bg-muted px-3 py-1">
                分类：{topic.category}
              </span>
            </div>
          </div>
        </article>

        <TopicRelatedPapers
          key={topic.id}
          topicId={topic.id}
          subjectQuery={topic.subjectQuery}
        />
      </div>
    </main>
  );
}
