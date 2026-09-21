import { Share, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatInput } from "@/features/chat/components/chat-input";
import { ResearchNav } from "@/features/search/deep-search/components/research-nav";
import { AnswerCard } from "@/features/search/deep-search/components/answer-card";
import { ReferenceGrid } from "@/features/search/deep-search/components/reference-grid";
import { FollowUps } from "@/features/search/deep-search/components/follow-ups";
import { agentSession } from "@/features/search/deep-search/data";

/**
 * 深度搜索结果页 `/agents/deep-search` —— 对应「深知-AI研究助手.svg」,
 * 发现页「深度搜索」按钮的跳转目标(由 /agents/deep-research 迁移而来)
 */
export function DeepSearchPage() {
  return (
    <>
      <div className="mx-auto flex max-w-[1180px] items-start gap-8 px-8 py-6">
        <ResearchNav />

        <div className="min-w-0 flex-1 space-y-5">
          {/* 会话顶栏 */}
          <div className="flex items-center gap-2.5">
            <span className="size-2 rounded-full bg-success" />
            <h1 className="text-sm font-medium text-ink">{agentSession.topic}</h1>
            <span className="text-xs text-faint">{agentSession.mode}</span>
            <div className="ml-auto flex gap-2">
              <Button variant="dark" size="sm" className="rounded-lg">
                <Star className="size-3.5 fill-brand-gold text-brand-gold" />
                Pro 模式
              </Button>
              <Button variant="outline" size="sm" className="rounded-lg">
                <Share className="size-3.5" />
                分享
              </Button>
            </div>
          </div>

          {/* 用户提问 */}
          <section>
            <p className="text-xs text-faint">你的提问</p>
            <p className="mt-1.5 text-lg font-semibold leading-relaxed text-ink">
              {agentSession.question}
            </p>
          </section>

          <AnswerCard />
          <ReferenceGrid />
          <FollowUps />
          <ChatInput />
        </div>
      </div>
    </>
  );
}
