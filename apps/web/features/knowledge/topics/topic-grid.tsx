"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { KnowledgeTopic } from "@/clients/knowledge";
import { TopicCard } from "./topic-card";

const carouselButtonClass = "absolute top-1/2 z-10 hidden size-10 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-[0_3px_12px_rgba(23,33,43,0.12)] transition-[color,background-color,border-color,transform,box-shadow] duration-200 hover:scale-105 hover:border-primary hover:bg-primary hover:text-primary-foreground hover:shadow-[0_6px_16px_rgba(23,33,43,0.18)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 active:scale-95 md:flex";

export function TopicGrid({ topics, featured = false, carousel = false, onCreatorClick }: { topics: KnowledgeTopic[]; featured?: boolean; carousel?: boolean; onCreatorClick?: (creatorId: string) => void }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  useEffect(() => {
    if (!carousel) return;
    const viewport = viewportRef.current;
    if (!viewport) return;

    const updateScrollState = () => {
      const maxScrollLeft = viewport.scrollWidth - viewport.clientWidth;
      setCanScrollLeft(viewport.scrollLeft > 1);
      setCanScrollRight(maxScrollLeft - viewport.scrollLeft > 1);
    };

    updateScrollState();
    viewport.addEventListener("scroll", updateScrollState, { passive: true });
    const resizeObserver = new ResizeObserver(updateScrollState);
    resizeObserver.observe(viewport);

    return () => {
      viewport.removeEventListener("scroll", updateScrollState);
      resizeObserver.disconnect();
    };
  }, [carousel, topics.length]);

  const scrollCards = (direction: -1 | 1) => {
    const viewport = viewportRef.current;
    const firstCard = viewport?.firstElementChild;
    if (!viewport || !(firstCard instanceof HTMLElement)) return;

    const styles = getComputedStyle(viewport);
    const gap = Number.parseFloat(styles.columnGap || styles.gap) || 0;
    viewport.scrollBy({ left: direction * (firstCard.offsetWidth + gap), behavior: "smooth" });
  };

  if (carousel) {
    return (
      <div className="relative overflow-visible">
        {canScrollLeft ? <button type="button" aria-label="向左查看主题" onClick={() => scrollCards(-1)} className={`${carouselButtonClass} -left-14`}><ChevronLeft className="size-[18px]" strokeWidth={2.2} /></button> : null}
        <div ref={viewportRef} tabIndex={0} role="region" aria-label="主题卡片列表，可横向滚动" className="scrollbar-subtle flex snap-x snap-mandatory gap-4 overflow-x-auto pb-1 outline-none focus-visible:ring-2 focus-visible:ring-primary/20 xl:gap-5">
          {topics.map((topic) => <div key={topic.id} data-topic-card className="min-w-0 shrink-0 basis-full snap-start md:basis-[calc((100%-2rem)/3)] xl:basis-[calc((100%-2.5rem)/3)]"><TopicCard topic={topic} featured={featured} onCreatorClick={onCreatorClick} /></div>)}
        </div>
        {canScrollRight ? <button type="button" aria-label="向右查看主题" onClick={() => scrollCards(1)} className={`${carouselButtonClass} -right-14`}><ChevronRight className="size-[18px]" strokeWidth={2.2} /></button> : null}
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 xl:gap-5">
      {topics.map((topic) => (
        <TopicCard key={topic.id} topic={topic} featured={featured} onCreatorClick={onCreatorClick} />
      ))}
    </div>
  );
}

