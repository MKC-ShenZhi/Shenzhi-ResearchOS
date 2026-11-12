# 学者库 V2.1 · 视觉精修

## 范围

基于 V2 Mock 的 `13dd6a0`，在 `feat/scholars-v2-visual-refinement` 进行产品评审。不合并 `dev` / `main`。沿用 6 位演示学者、Provider、数据契约、路由编码与搜索返回逻辑。未增加依赖或真实接口，未调整全局主题、Sidebar 或 Chat。

## 视觉组织

- 列表采用紧凑双列学术目录：48 / 56px 头像、20px 姓名、机构优先的任职行、两行简介、横排指标。桌面现有数据的卡片实测约 224–248px；不设置固定高度，长姓名、多任职自然增长，完整保留任职。
- 标题与英文栏目名并排，减少顶部留白；搜索框移除阴影，结果栏和卡片边界对齐。
- 详情以人物身份为中心：桌面 40px 姓名，英文姓名为次级信息；指标位于身份下方，不再独立包装为统计卡片。
- 简介与引用并排，论文成果使用完整内容宽度。栏目通过细线与留白分隔，减少重复白底容器。
- `ScholarBiography` 只管理本地语言状态。双语默认中文，仅单语时直接显示可用内容，无简介时保留缺省提示。切换按钮支持键盘与 `aria-pressed`；按学者 ID 重建状态。
- 年度引用继续使用 CSS 柱图及无障碍数据表，展示范围和数值规则不变。仅绘制提供的有效年份，不补造年份，不推导总引用。
- 论文以年份、标题、会议、作者、两行摘要构成连续条目；移除重复文件图标和提示，不生成演示论文链接。

## 主要代码

均位于 `apps/web/features/knowledge/scholars/`：

- `ScholarDetailPage.tsx`：身份、指标、简介 / 引用和成果的布局。
- `components/scholars-browser.tsx`、`scholar-card.tsx`：目录密度与搜索区排版。
- `components/profile-parts.tsx`：头像、任职、横排指标及骨架密度。
- `components/scholar-biography.tsx`：轻量简介语言切换。
- `components/annual-citations.tsx`、`scholar-publications.tsx`：引用与论文排版。

## 本地预览

```sh
cd apps/web
pnpm install --frozen-lockfile
pnpm dev
```

打开 `http://localhost:3000/knowledge/scholars`。已有依赖时可直接运行 `npm run dev`。不需要启动 FastAPI；全局外壳的认证 / 会话请求仍遵循原有配置。主题请通过界面按钮切换；既有主题 Store 在 hydration 后会应用本地偏好，仅依赖 URL 的 `theme` 参数不能保证最终主题。

## 视觉验收（2026-10-20）

在实际浏览器检查默认列表、林知遥的完整档案、明暗主题、375px 内容宽度与约 1536 × 960 的桌面视口。内嵌浏览器存在缩放，校准时读取实际 CSS 宽度；截图导出额外空白已裁去，完整原图保留在本次交付附件中。

实际交互确认：姓名搜索、空结果与清空、详情返回保留 `q=Avery`、英文单语言简介、稀疏年份只展示 2022 / 2024 / 2026、双语言切换、缺失资料、特殊字符 ID。真实 0 与缺失值保持区别。

使用临时 Provider 和现有学者 ID 验证长姓名、多任职及无空格的英文机构名：375px 和 1536px 均无横向溢出，卡片可自然增长。临时验收路由与视口容器在交付前移除，未加入正式 Mock 数据。

仍需产品评审：两行简介 / 摘要的密度取舍，以及真实资料长度下的阅读节奏。真机软键盘、安全区域未验收；Provider 强制故障的重试过程未完成浏览器验收，继续由既有代码与回归测试覆盖。

## 工程检查

在 `apps/web` 运行仓库既有的 `typecheck`、`lint`、`test`、`build` 脚本。具体结果随本次提交交付。

| 检查 | 结果 |
| --- | --- |
| `npm run typecheck` | 通过 |
| `npm run lint` | 0 errors；原有 `use-chat-session`、`use-popover-placement` 两条 Hook 依赖警告 |
| `npm test` | 329 / 329 通过 |
| `npm run build` | 通过，Turbopack 生产编译、TypeScript 与静态生成完成 |

保留现有测试覆盖；语言切换、响应式排版与长文字通过实际浏览器验证，未为纯样式添加实现镜像测试。
