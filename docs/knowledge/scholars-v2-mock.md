# 学者库 V2 · Mock 预览

## 范围与入口

沿用 `/knowledge/scholars` 和 `/knowledge/scholars/[scholarId]`。旧 `/scholars` 兼容重定向、AppShell、Sidebar、主题 Tokens 和全局 QueryProvider 保持原有实现。列表可直接浏览 6 位虚构学者，支持中英文姓名搜索、清空、卡片详情、返回搜索上下文；详情展示任职、简介、论文总数、总引用、2022—2026 年已提供的年度引用及演示论文成果。

参考 alphaXiv Researchers 的双列卡片、姓名与任职层次、留白和详情统计侧栏。移动端使用同一组组件纵向展示。所有页面均标注 `Mock Demo · 演示数据`，人物、机构、任职和统计均为虚构，不表示知识底座已验证。

不包含关注、收藏、认领、H-index、合作网络、完整履历或额外研究能力。原有未挂接到正式详情路由的原型文件未扩展。

## 数据组织

位置均在 `apps/web/features/knowledge/scholars/`：

- `types.ts`：V2 字段契约及 `ScholarProvider` 的 `search` / `detail` 边界。
- `mock-data.ts`：6 位虚构学者与独立的学者 ID → 论文 ID 关联表。
- `mock-provider.ts`：局部异步 Mock，提供姓名检索、精确 ID 详情、请求取消和克隆后的响应。未知 ID 返回 `null`，不回退到第一位学者。
- `provider.tsx`：本功能的数据源注入点；`app/knowledge/scholars/layout.tsx` 在路由子树中提供该 Provider。
- `presentation.ts`：姓名、首字母、统计缺省值与年度窗口规则。
- `components/`：卡片、头像、任职、指标、引用柱图、成果及加载/错误状态。

资料保留协议字段名：`scholar_id`、`name_zh`、`name_en`、`avatar_path`、`affiliations[].institution/position`、`bio_zh`、`bio_en`、`metrics.paper_count/citation_count`、`annual_citations[].year/count`、`updated_at`。可选字段接受缺省或 `null`。缺失统计显示“暂无数据”；真实 0 保留为 0。年度数据不补零，总引用不由年度数据求和。所有非空当前任职均展示。

演示样例包括英文姓名、多任职、可加载插画头像、头像缺省/加载失败、中文姓名、稀疏年份、缺少简介/统计及无论文。头像失败样例的 404 是刻意保留的测试场景。英文姓名缺失时，头像使用 `?` 占位，不伪造英文拼写。

论文元数据与类型直接复用 `clients/knowledge/mock-data.ts` 的 `mockPaperDetail` 和 `KnowledgePaperDetail`，没有复制论文数据库。虚构学者与这些论文的关联不代表真实作者关系；展示列表只是演示成果子集，不将展示数量解释为论文总数。Mock 论文 ID 未验证可被真实服务解析，因此成果卡片显示“论文详情暂不可用”，不生成必然失败的详情链接。

## 本地启动

在 `apps/web` 中使用现有 pnpm 锁文件与已安装依赖：

```sh
pnpm install --frozen-lockfile
pnpm dev
```

打开 `http://localhost:3000/knowledge/scholars`。不需要启动 FastAPI，也不需要将 `NEXT_PUBLIC_KNOWLEDGE_SOURCE` 设为 `mock`。公共外壳仍可能发起其原有登录态/会话请求，但本功能不依赖这些请求成功。

搜索示例：`林知遥`、`Avery`、`Chen`。点击卡片进入详情。请使用卡片生成的链接：ID 包含 `/`、`?` 和字面 `%2F`；沿用 `scholarHref` 编码和 `scholarIdFromRouteParam` 边界解码，不按姓名构造身份，不在 Provider 重复解码。

通过现有主题菜单切换亮色/暗色。建议检查 375px、768px 和 1280px CSS 视口。测试时需读取实际 CSS 宽度；内嵌浏览器的设定尺寸可能经过缩放。

## 与真实接口的边界

`KnowledgeClient`、`BffKnowledgeClient`、`MockKnowledgeClient`、FastAPI 与科研服务均未修改。其他知识库模块继续使用其原有数据源配置。本功能使用独立 `scholars-v2` Query Key，避免与旧 Scholar API 的缓存混用。

未来接真实资料时，在 `provider.tsx` 替换注入的 `ScholarProvider`，由 Adapter 通过 ShenZhi 自身 BFF / Backend 获取新版资料，并使用独立的 `cacheKey`。字段映射与论文 ID 关联归数据源处理，页面保持不变。旧版 Scholar API 不具备已确认的新版资料字段，当前未做兼容映射或伪造缺失内容。需等待新版接口、字段空值语义、头像可访问地址及稳定论文关联 ID 确认后再开展联调和开放论文跳转。

## 验证

在 `apps/web` 中执行：

```sh
npm run typecheck
npm run lint
npm test
npm run build
```

学者测试覆盖默认浏览、中英文搜索、独立详情、未知 ID、返回数据隔离、ID 关联复用论文、缺失值/真实零值、稀疏年份、不改写总引用、首字母头像、取消请求及路由编码。旧 Scholar BFF 请求测试继续保留。

该功能仅在 `feat/scholars-v2-mock` 预览。README 指定 `dev` 是 Vercel Production Branch；不得为预览直接推送或合并到 `dev` / `main`。需由产品负责人评审后决定下一阶段。

### 本轮结果（2026-10-20）

| 检查 | 结果 |
| --- | --- |
| TypeScript | `npm run typecheck` 通过 |
| ESLint | 0 errors；保留仓库原有 `use-chat-session`、`use-popover-placement` 两条 Hook 依赖警告 |
| 测试 | 329 / 329 通过，包含学者 V2 测试及旧 Scholar BFF 回归 |
| 生产构建 | `npm run build` 通过，完成 TypeScript 与静态页面生成 |
| 实际运行 | 既有开发服务及独立本地生产服务均能浏览列表并进入各自详情；生产预览无需登录 |
| 响应式与主题 | 实测 CSS 宽度 375、768、1280px；列表和详情没有横向溢出，亮暗主题已检查 |
| 关键交互 | 中英文搜索、清空、空结果、详情返回保留查询、头像失败回退、稀疏引用、缺失统计、无成果、特殊字符 ID、未知 ID 均已检查；旧 `/scholars/[id]` 重定向可用 |

加载错误与重试入口有代码回归检查，未在浏览器注入运行时 Provider 故障。真实知识底座新版字段、真实论文详情跳转和真机浏览器不在本轮通过声明中。截图作为本次本地交付附件提供，未将截图二进制加入源码。
