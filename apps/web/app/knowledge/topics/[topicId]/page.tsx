import { TopicDetailPage } from "@/features/knowledge/topics/detail/topic-detail-page";

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ topicId: string }>;
  searchParams: Promise<{ returnTo?: string | string[] }>;
}) {
  const [{ topicId }, { returnTo }] = await Promise.all([params, searchParams]);
  return <TopicDetailPage topicId={topicId} returnTo={typeof returnTo === "string" ? returnTo : null} />;
}
