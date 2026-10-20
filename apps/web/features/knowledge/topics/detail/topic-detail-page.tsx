"use client";

import Link from "next/link";
import { ArrowLeft, RotateCw, Tag } from "lucide-react";
import { KnowledgeClientError } from "@/clients/knowledge";
import { Button } from "@/components/ui/button";
import { TopicFollowButton } from "@/features/knowledge/interactions/components/topic-follow-button";
import { TopicFollowerCount } from "@/features/knowledge/interactions/components/topic-follower-count";
import { TopicCover } from "../topic-cover";
import { TopicRelatedPapers } from "./topic-related-papers";
import { useTopicDetail } from "./use-topic-detail";
import { topicSquareHref } from "../topic-url-state";

export function TopicDetailPage({ topicId, returnTo }: { topicId: string; returnTo?: string | null }) {
  const squareHref = topicSquareHref(returnTo);
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
          <h1 className="text-2xl font-semibold text-ink">
            {notFound ? "没有找到这个主题" : "主题加载失败"}
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted">
            {notFound
              ? "该主题可能已下线，或者链接中的主题编号不正确。"
              : "暂时无法取得主题信息，请稍后重新尝试。"}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href={squareHref}
              className="inline-flex h-9 items-center rounded-lg border border-line px-4 text-sm font-medium text-ink"
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
          href={squareHref}
          className="inline-flex items-center gap-2 text-sm text-muted transition hover:text-primary"
        >
          <ArrowLeft className="size-4" />
          返回主题广场
        </Link>

        <article className="mt-5 grid grid-cols-[96px_minmax(0,1fr)] gap-x-4 gap-y-3 rounded-2xl border border-line bg-card p-4 sm:p-5 md:grid-cols-[240px_minmax(0,1fr)] md:gap-x-6 md:gap-y-0">
          <div className="relative aspect-[4/3] self-start overflow-hidden rounded-xl bg-muted md:row-span-3">
            <TopicCover key={topic.imagePath} imagePath={topic.imagePath} name={topic.nameZh} sizes="(min-width: 768px) 240px, 96px" eager />
          </div>
          <div className="min-w-0 [overflow-wrap:anywhere]">
            <h1 className="text-2xl font-semibold leading-tight tracking-tight text-ink md:text-[30px]">
              {topic.nameZh}
            </h1>
            <p className="mt-1 text-sm leading-5 text-muted md:text-[15px]">
              {topic.nameEn}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-primary/5 px-2.5 py-1 text-xs text-muted">
                <Tag className="size-3 shrink-0" />
                {topic.category}
              </span>
              <TopicFollowerCount topicId={topic.id} />
              <TopicFollowButton topicId={topic.id} className="h-7" />
            </div>
          </div>
          <p className="col-span-2 line-clamp-3 min-w-0 whitespace-pre-line text-sm leading-6 text-muted [overflow-wrap:anywhere] md:col-span-1 md:mt-3 md:text-[15px]" title={description}>
            {description}
          </p>
          <p className="col-span-2 min-w-0 text-xs leading-5 text-muted [overflow-wrap:anywhere] md:col-span-1 md:mt-3 md:text-[13px]">
            创建者：{typeof topic.author === "string" ? topic.author : topic.author.name}
          </p>
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
