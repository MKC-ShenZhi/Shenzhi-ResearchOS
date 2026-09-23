import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Bookmark,
  Landmark,
  Network,
  Tags,
  Users,
  type LucideIcon,
} from "lucide-react";

const CAPABILITIES: Array<{
  title: string;
  description: string;
  href: string;
  icon: LucideIcon;
  tone: string;
}> = [
  {
    title: "论文库",
    description: "检索和探索学术论文",
    href: "/knowledge/search",
    icon: BookOpen,
    tone: "bg-primary-soft text-primary",
  },
  {
    title: "我的文献",
    description: "管理收藏与个人科研文献",
    href: "/knowledge/papers",
    icon: Bookmark,
    tone: "bg-brand-violet/10 text-brand-violet",
  },
  {
    title: "学者库",
    description: "搜索学者、研究主题与论文成果",
    href: "/knowledge/scholars",
    icon: Users,
    tone: "bg-success-soft text-success",
  },
  {
    title: "主题库",
    description: "按科研主题探索相关论文",
    href: "/knowledge/topics",
    icon: Tags,
    tone: "bg-brand-cyan/10 text-brand-cyan",
  },
  {
    title: "项目基金库",
    description: "浏览基金并探索关联科研论文",
    href: "/knowledge/funding",
    icon: Landmark,
    tone: "bg-brand-gold/20 text-ink",
  },
  {
    title: "关系图谱",
    description: "从论文出发探索引用和知识关系",
    href: "/knowledge/graph",
    icon: Network,
    tone: "bg-primary-soft text-primary",
  },
];

/** 能力入口型首页：不展示无法由真实 API 支撑的跨库统计或搜索结果。 */
export function KnowledgeDashboard() {
  return (
    <div className="mx-auto max-w-[1080px] px-6 py-8 lg:px-8 lg:py-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-ink">知识库</h1>
        <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">
          通过知识底座检索论文、学者与科研主题，并管理你的个人文献和论文关系图谱。
        </p>
      </header>

      <section className="mt-7 grid gap-5 md:grid-cols-2 xl:grid-cols-3" aria-label="知识库能力入口">
        {CAPABILITIES.map((capability) => {
          const Icon = capability.icon;
          return (
            <Link
              key={capability.href}
              href={capability.href}
              className="group flex min-h-44 flex-col rounded-2xl bg-card p-6 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-pop"
            >
              <span className={`flex size-12 items-center justify-center rounded-xl ${capability.tone}`}>
                <Icon className="size-5" strokeWidth={1.8} />
              </span>
              <h2 className="mt-5 text-[17px] font-bold text-ink group-hover:text-primary">
                {capability.title}
              </h2>
              <p className="mt-1.5 flex-1 text-sm leading-relaxed text-muted">
                {capability.description}
              </p>
              <span className="mt-5 inline-flex items-center gap-1.5 text-xs font-medium text-primary">
                进入
                <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          );
        })}
      </section>
    </div>
  );
}
