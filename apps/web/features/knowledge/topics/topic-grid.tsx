"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { KnowledgeTopic } from "@/clients/knowledge";
import { TopicCard } from "./topic-card";

const carouselButtonClass = "absolute top-1/2 z-10 hidden size-10 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 shadow-[0_3px_12px_rgba(23,33,43,0.12)] transition-[color,background-color,border-color,transform,box-shadow] duration-200 hover:scale-105 hover:border-primary hover:bg-primary hover:text-primary-foreground hover:shadow-[0_6px_16px_rgba(23,33,43,0.18)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 active:scale-95 md:flex";
const CAROUSEL_BATCH_SIZE = 6;

interface TopicGridProps {
  topics: KnowledgeTopic[];
  returnTo: string;
  featured?: boolean;
  carousel?: boolean;
  deferred?: boolean;
}

// Keep one row's space while offscreen categories wait to mount their cards.
function TopicRowPlaceholder() {
  return (
    <div aria-hidden="true" className="scrollbar-subtle flex gap-4 overflow-x-scroll pb-1 xl:gap-5">
      {[0, 1, 2].map((index) => (
        <div key={index} className={`${index ? "hidden md:block" : ""} min-w-0 flex-1 overflow-hidden rounded-2xl border border-slate-200 bg-white`}>
          <div className="aspect-[3.6/1] bg-slate-100" />
          <div className="h-[12.5rem] space-y-3 p-3"><div className="h-6 w-1/2 rounded bg-slate-100" /><div className="h-10 rounded bg-slate-50" /></div>
        </div>
      ))}
    </div>
  );
}

export function TopicGrid({ deferred = false, ...props }: TopicGridProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(!deferred);

  useEffect(() => {
    if (!deferred || ready) return;
    if (typeof IntersectionObserver === "undefined") {
      const frame = requestAnimationFrame(() => setReady(true));
      return () => cancelAnimationFrame(frame);
    }
    const container = containerRef.current;
    if (!container) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setReady(true);
        observer.disconnect();
      }
    }, { rootMargin: "300px 0px" });
    observer.observe(container);
    return () => observer.disconnect();
  }, [deferred, ready]);

  if (!deferred) return <TopicCardList {...props} />;

  return (
    <div ref={containerRef} tabIndex={0} role="region" aria-label={`${props.topics[0]?.category ?? "分类"}主题`} onFocusCapture={() => setReady(true)} className="rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-primary/20">
      {ready ? <TopicCardList {...props} /> : <TopicRowPlaceholder />}
    </div>
  );
}

function TopicCardList({ topics, returnTo, featured = false, carousel = false }: Omit<TopicGridProps, "deferred">) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [visibleCount, setVisibleCount] = useState(CAROUSEL_BATCH_SIZE);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const displayedTopics = carousel ? topics.slice(0, visibleCount) : topics;

  useEffect(() => {
    if (!carousel) return;
    const viewport = viewportRef.current;
    if (!viewport) return;

    // One scroll/resize burst may append only one batch. The next effect uses
    // the extended scroll width, so repeated events cannot mount the full list.
    let requestedMore = false;
    const updateScrollState = () => {
      const maxScrollLeft = viewport.scrollWidth - viewport.clientWidth;
      const remaining = maxScrollLeft - viewport.scrollLeft;
      const firstCard = viewport.firstElementChild;
      const preloadDistance = firstCard instanceof HTMLElement ? firstCard.offsetWidth : viewport.clientWidth;
      setCanScrollLeft(viewport.scrollLeft > 1);
      setCanScrollRight(remaining > 1);
      if (!requestedMore && visibleCount < topics.length && remaining <= preloadDistance) {
        requestedMore = true;
        setVisibleCount((count) => Math.min(count + CAROUSEL_BATCH_SIZE, topics.length));
      }
    };

    updateScrollState();
    viewport.addEventListener("scroll", updateScrollState, { passive: true });
    const resizeObserver = new ResizeObserver(updateScrollState);
    resizeObserver.observe(viewport);

    return () => {
      viewport.removeEventListener("scroll", updateScrollState);
      resizeObserver.disconnect();
    };
  }, [carousel, topics.length, visibleCount]);

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
        {canScrollLeft ? <button type="button" aria-label="向左查看主题" onClick={() => scrollCards(-1)} className={`${carouselButtonClass} -left-4 2xl:-left-14`}><ChevronLeft className="size-[18px]" strokeWidth={2.2} /></button> : null}
        <div ref={viewportRef} tabIndex={0} role="region" aria-label="主题卡片列表，可横向滚动" className="scrollbar-subtle flex snap-x snap-mandatory gap-4 overflow-x-auto pb-1 outline-none focus-visible:ring-2 focus-visible:ring-primary/20 xl:gap-5">
          {displayedTopics.map((topic) => <div key={topic.id} data-topic-card className="min-w-0 shrink-0 basis-full snap-start md:basis-[calc((100%-2rem)/3)] xl:basis-[calc((100%-2.5rem)/3)]"><TopicCard topic={topic} returnTo={returnTo} featured={featured} /></div>)}
        </div>
        {canScrollRight ? <button type="button" aria-label="向右查看主题" onClick={() => scrollCards(1)} className={`${carouselButtonClass} -right-4 2xl:-right-14`}><ChevronRight className="size-[18px]" strokeWidth={2.2} /></button> : null}
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 xl:gap-5">
      {topics.map((topic) => (
        <TopicCard key={topic.id} topic={topic} returnTo={returnTo} featured={featured} />
      ))}
    </div>
  );
}

