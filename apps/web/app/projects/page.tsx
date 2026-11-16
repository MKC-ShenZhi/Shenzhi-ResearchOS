import { redirect } from "next/navigation";
import { projects } from "@/features/projects/data";

/** `/projects` 无独立主页面,重定向到第一个项目 */
export default function ProjectsIndexPage() {
  redirect(`/projects/${projects[0].id}`);
}
