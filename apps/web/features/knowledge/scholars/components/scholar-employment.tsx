"use client";

import { useState } from "react";
import { Building2, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ScholarProfile } from "../types";

const initialCount = 5;

function formatDate(value: string | null) {
  if (!value) return "";
  const date = /^(\d{4})(?:-(\d{2})(?:-\d{2})?)?$/.exec(value);
  if (!date) return value;
  return date[2] ? `${date[1]}年${Number(date[2])}月` : `${date[1]}年`;
}

export function ScholarEmployment({ entries }: { entries: NonNullable<ScholarProfile["employment"]> }) {
  const [expanded, setExpanded] = useState(false);
  const sorted = [...entries].sort((a, b) => (b.start_date ?? "").localeCompare(a.start_date ?? ""));
  const visible = expanded ? sorted : sorted.slice(0, initialCount);

  return (
    <section className="border-b border-line py-8" aria-labelledby="employment-title">
      <div className="mb-6 flex flex-wrap items-baseline gap-3">
        <h2 id="employment-title" className="text-lg font-semibold text-ink">任职经历</h2>
        <span className="text-xs text-muted">未经验证</span>
      </div>
      <ol id="employment-list" className="relative space-y-6 before:absolute before:inset-y-4 before:left-5 before:border-l before:border-line">
        {visible.map(({ organization, role_title, department, start_date, end_date }, index) => {
          const details = [role_title ? organization : null, department].filter(Boolean).join(" · ");
          const dates = [formatDate(start_date), formatDate(end_date)].filter(Boolean).join(" – ");
          return (
            <li key={index} className="relative grid grid-cols-[2.5rem_minmax(0,1fr)] items-start gap-x-4 gap-y-1 sm:grid-cols-[2.5rem_minmax(0,1fr)_auto]">
              <span className="row-span-2 grid size-10 place-items-center rounded-lg border border-line bg-card text-muted sm:row-span-1">
                <Building2 aria-hidden="true" className="size-5" />
              </span>
              <div className="min-w-0 break-words">
                <h3 className="font-semibold text-ink">{role_title || organization}</h3>
                {details ? <p className="mt-0.5 text-sm text-muted">{details}</p> : null}
              </div>
              {dates ? <p className="col-start-2 text-sm text-muted sm:col-start-auto">{dates}</p> : null}
            </li>
          );
        })}
      </ol>
      {entries.length > initialCount ? (
        <Button className="mt-4 ml-10" variant="ghost" aria-expanded={expanded} aria-controls="employment-list" onClick={() => setExpanded(!expanded)}>
          {expanded ? "收起较早经历" : `显示另外 ${entries.length - initialCount} 条经历`}
          <ChevronDown aria-hidden="true" className={expanded ? "rotate-180" : undefined} />
        </Button>
      ) : null}
    </section>
  );
}
