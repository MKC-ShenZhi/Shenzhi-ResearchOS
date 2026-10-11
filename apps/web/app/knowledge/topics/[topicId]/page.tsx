import { TopicDetailPage } from "@/features/knowledge/topics/detail/topic-detail-page";

export default async function Page({
  params,
}: {
  params: Promise<{ topicId: string }>;
}) {
  const { topicId } = await params;
  return <TopicDetailPage topicId={topicId} />;
}
