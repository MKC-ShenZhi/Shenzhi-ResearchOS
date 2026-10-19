"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { ScholarProfile } from "../types";

export function ScholarBiography({ scholar }: { scholar: ScholarProfile }) {
  const chinese = scholar.bio_zh?.trim();
  const english = scholar.bio_en?.trim();
  const [language, setLanguage] = useState<"zh" | "en">(chinese ? "zh" : "en");
  const bilingual = Boolean(chinese && english);

  return (
    <section className="min-w-0" aria-labelledby="about-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2
          id="about-title"
          className="text-lg font-semibold tracking-tight text-ink"
        >
          关于学者{" "}
          <span className="ml-2 text-xs font-normal tracking-normal text-muted">
            About
          </span>
        </h2>
        {bilingual ? (
          <div className="flex gap-1" role="group" aria-label="简介语言">
            {([
              ["zh", "中文"],
              ["en", "English"],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={language === value}
                aria-controls="scholar-biography"
                onClick={() => setLanguage(value)}
                className={cn(
                  "min-h-8 rounded-md px-2.5 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
                  language === value
                    ? "bg-primary-soft font-medium text-primary"
                    : "text-muted hover:text-ink",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <p
        id="scholar-biography"
        lang={!chinese && !english ? "zh-CN" : language === "zh" ? "zh-CN" : "en"}
        className="mt-4 whitespace-pre-line break-words text-[15px] leading-7 text-ink-2"
      >
        {(language === "zh" ? chinese : english) || "个人简介暂无数据。"}
      </p>
    </section>
  );
}
