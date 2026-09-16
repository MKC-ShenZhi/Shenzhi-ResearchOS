import Link from "next/link";
import {
  ArrowLeft,
  Github,
  Globe,
  Mail,
  MapPin,
  UserRoundCheck,
} from "lucide-react";
import { AppShell } from "@/components/common/layout/app-shell";
import { Button } from "@/components/ui/button";
import { FollowButton } from "@/features/scholars/components/follow-button";
import { CitationChart } from "@/features/scholars/[id]/components/citation-chart";
import { PublicationList } from "@/features/scholars/[id]/components/publication-list";
import { scholarDetail, scholars } from "@/features/knowledge/data-scholars";
import { cn } from "@/lib/utils";

const LINK_ICONS = [Globe, Globe, Github, Mail];

/**
 * 学者详情页 `/scholars/[id]` —— 对应「深知-学者详情页.svg」
 * (原型阶段均以何恺明主页为示例数据)
 */
export function ScholarDetailPage({ scholarId }: { scholarId: string }) {
  const scholar = scholars.find((s) => s.id === scholarId) ?? scholars[0];
  const detail = scholarDetail;

  return (
    <AppShell>
      <div className="mx-auto max-w-[1180px] space-y-5 px-8 py-6">
        {/* 返回 + 速览锚点 */}
        <div className="flex items-center gap-6">
          <Link href="/scholars">
            <Button variant="outline" size="sm" className="rounded-lg">
              <ArrowLeft className="size-3.5" />
              返回学者列表
            </Button>
          </Link>
          <nav className="flex gap-5 text-[13px]">
            {detail.toc.map((item) => (
              <a
                key={item.id}
                href={`#${item.id}`}
                className={cn(
                  "transition-colors",
                  item.active
                    ? "border-l-2 border-primary pl-2 font-medium text-primary"
                    : "text-muted hover:text-ink-2",
                )}
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>

        {/* 头部卡片 */}
        <header className="flex items-center gap-6 rounded-2xl bg-card p-7 shadow-card">
          <span
            className="flex size-24 shrink-0 items-center justify-center rounded-full text-3xl font-bold text-white"
            style={{ backgroundColor: scholar.avatarColor }}
          >
            {scholar.initials}
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="text-[26px] font-bold text-ink">
              {scholar.nameCn} · {scholar.nameEn}
            </h1>
            <p className="mt-1.5 text-sm text-muted">
              {scholar.role} · {scholar.affiliation}
            </p>
            <div className="mt-2 flex items-center gap-5 text-xs text-muted">
              <span className="flex items-center gap-1.5">
                <MapPin className="size-3.5 text-faint" />
                {detail.location}
              </span>
              <span className="flex items-center gap-1.5">
                <Mail className="size-3.5 text-faint" />
                {detail.email}
              </span>
            </div>
          </div>
          <div className="flex shrink-0 gap-2.5">
            <FollowButton scholarId={scholar.id} defaultFollowing={scholar.followed} />
            <Button variant="dark" size="sm" className="rounded-full px-4">
              <UserRoundCheck className="size-3.5" />
              认领此主页
            </Button>
          </div>
        </header>

        <div className="grid items-start gap-5 xl:grid-cols-[1fr_300px]">
          {/* 左列:简介 + 研究成果 */}
          <div className="space-y-5">
            <section id="intro" className="rounded-2xl bg-card p-6 shadow-card">
              <h2 className="text-[17px] font-bold text-ink">个人简介</h2>
              {detail.bio.map((paragraph, i) => (
                <p
                  key={i}
                  className="mt-3 text-sm leading-relaxed text-muted"
                >
                  {paragraph}
                </p>
              ))}
              <div className="mt-4 flex flex-wrap gap-2.5">
                {detail.introTags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-lg bg-chip px-3 py-1.5 text-xs text-muted"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </section>

            <PublicationList />
          </div>

          {/* 右列:指标 / 方向 / 年度引用 / 外链 */}
          <div className="space-y-5">
            <section className="rounded-2xl bg-card p-5 shadow-card">
              <h3 className="text-[15px] font-semibold text-ink">学术指标</h3>
              <div className="mt-3 grid grid-cols-3">
                <div>
                  <p className="text-xl font-bold text-ink">
                    {detail.metrics.totalCitations}
                  </p>
                  <p className="mt-0.5 text-xs text-faint">总引用</p>
                </div>
                <div>
                  <p className="text-xl font-bold text-ink">
                    {detail.metrics.hIndex}
                  </p>
                  <p className="mt-0.5 text-xs text-faint">h-index</p>
                </div>
                <div>
                  <p className="text-xl font-bold text-ink">
                    {detail.metrics.i10Index}
                  </p>
                  <p className="mt-0.5 text-xs text-faint">i10-index</p>
                </div>
              </div>
            </section>

            <section className="rounded-2xl bg-card p-5 shadow-card">
              <h3 className="text-[15px] font-semibold text-ink">研究方向</h3>
              <div className="mt-3 flex flex-wrap gap-2.5">
                {scholar.tags.slice(0, 2).map((tag) => (
                  <span
                    key={tag}
                    className="rounded-lg bg-chip px-3 py-1.5 text-xs text-muted"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </section>

            <CitationChart
              years={detail.yearlyCitations.years}
              values={detail.yearlyCitations.values}
              highlight={detail.yearlyCitations.highlight}
            />

            <section className="rounded-2xl bg-card p-5 shadow-card">
              <h3 className="text-[15px] font-semibold text-ink">外链</h3>
              <ul className="mt-3 space-y-2.5">
                {detail.links.map((link, i) => {
                  const Icon = LINK_ICONS[i] ?? Globe;
                  return (
                    <li key={link}>
                      <button
                        type="button"
                        className="flex w-full cursor-pointer items-center gap-2.5 text-[13px] text-ink-2 transition-colors hover:text-primary"
                      >
                        <Icon className="size-4 text-muted" />
                        {link}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
