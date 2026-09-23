/**
 * V1 暂停正式接入：知识底座尚无支撑独立产品页的稳定专利实体能力。
 * 原型与兼容路由保留，后续随科研能力重新启用或重构。
 */
export function PatentsPage() {
  return (
    <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-[980px] items-center justify-center px-6 py-8">
      <div className="rounded-2xl border border-dashed border-line bg-card px-8 py-12 text-center shadow-card">
        <h1 className="text-xl font-semibold text-ink">专利库</h1>
        <p className="mt-3 text-sm text-muted">当前知识底座暂未提供专利实体检索能力。</p>
      </div>
    </div>
  );
}
