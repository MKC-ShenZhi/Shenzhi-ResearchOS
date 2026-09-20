import {
  CalendarDays,
  CheckCircle2,
  Circle,
  Github,
  Globe,
  Link2,
  Loader,
  Pencil,
  Settings2,
  UserRound,
  Users,
} from "lucide-react";
import { AppShell } from "@/components/common/layout/app-shell";
import { Button } from "@/components/ui/button";
import { getProject, type MilestoneStatus } from "@/features/projects/data";

const STATUS_STYLE: Record<MilestoneStatus, { label: string; className: string }> = {
  done: { label: "已完成", className: "bg-primary-soft text-primary" },
  doing: { label: "进行中", className: "bg-brand-gold/25 text-ink" },
  todo: { label: "未开始", className: "bg-chip text-muted" },
};

function MilestoneIcon({ status }: { status: MilestoneStatus }) {
  if (status === "done") return <CheckCircle2 className="size-4.5 text-primary" />;
  if (status === "doing") return <Loader className="size-4.5 text-brand-gold" />;
  return <Circle className="size-4.5 text-faint" />;
}

/**
 * 科研项目详情页 `/projects/[id]` —— 演示态项目管理页
 * 项目由用户建立;样例「深知」数据取自仓库 README(features/projects/data.ts)
 */
export function ProjectDetailPage({ projectId }: { projectId: string }) {
  const project = getProject(projectId);
  const doneCount = project.milestones.filter((m) => m.status === "done").length;

  return (
    <AppShell>
      <div className="mx-auto max-w-[1080px] space-y-5 px-8 py-8">
        {/* 头部:名称 / 状态 / 进度 / 操作 */}
        <header className="rounded-2xl bg-card p-7 shadow-card">
          <div className="flex items-start gap-5">
            <span className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-primary-soft text-xl font-bold text-primary">
              {project.name.slice(0, 1)}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-3">
                <h1 className="text-[22px] font-bold text-ink">{project.name}</h1>
                <span className="rounded-full bg-primary-soft px-2.5 py-1 text-xs font-medium text-primary">
                  {project.status}
                </span>
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">
                {project.tagline}
              </p>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button variant="outline" size="sm">
                <Pencil className="size-3.5" />
                编辑
              </Button>
              <Button variant="outline" size="sm">
                <Settings2 className="size-3.5" />
                项目设置
              </Button>
            </div>
          </div>

          <div className="mt-5 flex items-center gap-3">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-chip">
              <div
                className="h-full rounded-full bg-primary transition-[width]"
                style={{ width: `${project.progress}%` }}
              />
            </div>
            <span className="text-sm font-semibold text-ink">
              {project.progress}%
            </span>
            <span className="text-xs text-faint">
              里程碑 {doneCount}/{project.milestones.length}
            </span>
          </div>
        </header>

        <div className="grid items-start gap-5 xl:grid-cols-[1fr_300px]">
          {/* 左列:简介 + 里程碑 */}
          <div className="space-y-5">
            <section className="rounded-2xl bg-card p-6 shadow-card">
              <h2 className="text-[15px] font-semibold text-ink">项目简介</h2>
              {project.overview.map((paragraph, i) => (
                <p key={i} className="mt-3 text-sm leading-relaxed text-muted">
                  {paragraph}
                </p>
              ))}
              <div className="mt-4 flex flex-wrap gap-2.5">
                {project.techStack.map((tech) => (
                  <span
                    key={tech}
                    className="rounded-lg bg-chip px-3 py-1.5 text-xs text-muted"
                  >
                    {tech}
                  </span>
                ))}
              </div>
            </section>

            <section className="rounded-2xl bg-card p-6 shadow-card">
              <h2 className="text-[15px] font-semibold text-ink">里程碑</h2>
              <ul className="mt-4 space-y-1">
                {project.milestones.map((m) => (
                  <li
                    key={m.title}
                    className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-chip"
                  >
                    <MilestoneIcon status={m.status} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-ink">{m.title}</p>
                      <p className="mt-0.5 text-xs text-muted">{m.detail}</p>
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_STYLE[m.status].className}`}
                    >
                      {STATUS_STYLE[m.status].label}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          {/* 右列:信息 / 成员 / 链接 */}
          <div className="space-y-5">
            <section className="rounded-2xl bg-card p-5 shadow-card">
              <h3 className="text-[15px] font-semibold text-ink">项目信息</h3>
              <ul className="mt-3 space-y-2.5 text-[13px]">
                <li className="flex items-center gap-2.5 text-muted">
                  <UserRound className="size-4 text-faint" />
                  负责人
                  <span className="ml-auto text-ink">{project.owner}</span>
                </li>
                <li className="flex items-center gap-2.5 text-muted">
                  <CalendarDays className="size-4 text-faint" />
                  创建时间
                  <span className="ml-auto text-ink">{project.createdAt}</span>
                </li>
              </ul>
            </section>

            <section className="rounded-2xl bg-card p-5 shadow-card">
              <h3 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
                <Users className="size-4 text-muted" />
                成员
                <span className="text-xs font-normal text-faint">
                  {project.members.length} 人
                </span>
              </h3>
              <ul className="mt-3 space-y-2.5">
                {project.members.map((member) => (
                  <li key={member.name} className="flex items-center gap-2.5">
                    <span className="flex size-8 items-center justify-center rounded-full bg-primary-soft text-xs font-semibold text-primary">
                      {member.name.slice(0, 1)}
                    </span>
                    <span className="flex-1 text-[13px] text-ink">
                      {member.name}
                    </span>
                    <span className="text-xs text-faint">{member.role}</span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="rounded-2xl bg-card p-5 shadow-card">
              <h3 className="flex items-center gap-2 text-[15px] font-semibold text-ink">
                <Link2 className="size-4 text-muted" />
                相关链接
              </h3>
              <ul className="mt-3 space-y-2.5">
                {project.links.map((link) => {
                  const Icon = link.label.includes("GitHub") || link.label.includes("GHCR") ? Github : Globe;
                  return (
                    <li key={link.label}>
                      <a
                        href={link.href}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-2.5 text-[13px] text-ink-2 transition-colors hover:text-primary"
                      >
                        <Icon className="size-4 text-muted" />
                        {link.label}
                        <span className="truncate text-xs text-faint">
                          {link.href.replace(/^https?:\/\//, "")}
                        </span>
                      </a>
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
