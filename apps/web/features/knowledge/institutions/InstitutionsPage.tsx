import { InstitutionsBrowser } from "@/features/knowledge/institutions/components/institutions-browser";

/**
 * V1 暂停正式接入：知识底座尚无支撑独立产品页的稳定机构实体能力。
 * 原型与兼容路由保留，后续随科研能力重新启用或重构。
 */
export function InstitutionsPage() {
  return (
    <div className="mx-auto max-w-[960px] px-8 py-6">
      <InstitutionsBrowser />
    </div>
  );
}
