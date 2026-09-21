import { PatentsBrowser } from "@/features/knowledge/patents/components/patents-browser";

/**
 * V1 暂停正式接入：知识底座尚无支撑独立产品页的稳定专利实体能力。
 * 原型与兼容路由保留，后续随科研能力重新启用或重构。
 */
export function PatentsPage() {
  return (
    <div className="flex min-h-[calc(100vh)] items-stretch">
      <PatentsBrowser />
    </div>
  );
}
