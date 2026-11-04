# 视觉探索主题：极致黑白与青绿

本说明覆盖「极致黑白」（`gpt`）与「青绿」（`warm-teal`）两个日夜自适应预设，不改变默认深知及其他固定外观预设。

预设注册表为 `apps/web/lib/theme-presets.ts` 的 `THEME_PRESETS`：侧栏调色盘的快捷预设（`QUICK_THEME_PRESET_IDS`）为深知、极致黑白、青绿、墨蓝青绿（`blue-teal`）、深知绿（`shenzhi-green`）；设置页（`VISIBLE_THEME_PRESETS`）另列出 Claude、alphaXiv、Apple / Neo / Air 系列、光谱系列等固定外观预设。`custom` 只为兼容已保存的偏好和首屏初始化而保留，当前不在设置页或侧栏列出。各预设配色定义在 `apps/web/styles/globals.css` 的 `html[data-theme="<预设 ID>"]` 规则中。

## 配色与运行机制

- `gpt` 保留持久化 ID，显示名为「极致黑白」。日间以近白页面、白色卡片、浅灰侧栏和黑色主操作构成层次；夜间采用 `#181818` 页面、`#202020` 侧栏、`#262626` 卡片，主操作反转为浅底深字。
- `warm-teal` 显示名为「青绿」，配色最初取自参考分支，现位于 `apps/web/styles/globals.css` 的 `html[data-theme="warm-teal"]` 及其 `.dark` 规则。日间保留暖白 `#fbfaf4` 与青绿 `#1c7783`；夜间保留中性 Gray 表面和 `#7bd4d8` 青绿强调。
- 两个预设均显式清空壁纸及容器图像，并排除旧探索主题的主色混入背景规则。状态颜色、模型供应商标识、论文图片、PDF 和图谱的数据颜色不做全局灰度过滤。
- 沿用 `ThemePreset`、Zustand、`data-theme`、`.dark` 与现有语义 CSS Token。参考分支独有的变量按当前 `primary/primary-soft/agent/chip/panel` 等语义适配，不直接引入参考 CSS，也不增加主题引擎。
- `MODE_THEME_PRESETS`（深知、极致黑白、青绿）定义支持日间、夜间、跟随系统的预设；`blue-teal`、`shenzhi-green` 等其他预设为固定外观。该注册表供 Store、移动按钮和两个设置入口共用。首屏脚本从同一注册表生成预设名单，和 Store 使用相同的模式判定。
- 继续使用 `shenzhi-theme` 和 `shenzhi-theme-preset` 存储偏好；首帧保持 SSR 默认状态，挂载后同步 Store。系统媒体查询变化会实时应用到支持模式的预设，移动端按钮同步更新图标且不会跳到 Apple。
- 首屏主题脚本放在根布局 `<head>` 的原生内联 `<script>` 中，随 HTML 解析直接执行，不等待 Next.js 客户端运行时。选择自定义预设时同步保存配置与生成的 CSS 变量，确保刷新首屏和 Store 水合后配色一致。
- `custom-theme.ts` 的生成与清理机制保持不变；切换离开自定义主题仍清除全部内联变量，防止覆盖预设。测试覆盖这一过程。

## 组件兼容范围

现有部分组件把主色背景与白字直接组合，另有智能搜索入口写死紫色。两个自适应预设使用有作用域的 CSS 兼容规则，让这些主操作读取 `primary-foreground`，让智能搜索选中态读取 `agent/agent-soft`。AI 标识去掉组件自身渐变，使用主操作颜色。兼容规则不匹配其他预设，不修改业务布局或组件结构。

## 预览与验收

1. 在 `apps/web` 中运行 `pnpm dev`，在「设置 → 个人 → 外观」或侧栏设置调色盘选中「极致黑白」或「青绿」。
2. 在同一主题下选择日间、夜间或跟随系统；移动端顶栏按钮可以显式切换日夜。
3. 检查 `/`、`/knowledge/search?q=transformer` 和已有的 `/agents?session=<真实会话 ID>`。
4. 刷新页面并检查预设、模式及控制台；若浏览器中保存过自定义主题（`custom`），切换到其他预设后确认没有内联颜色残留。

调试链接支持 `?theme=<预设 ID>`（如 `?theme=gpt`、`?theme=warm-teal`），仅指定预设，日夜读取已有模式偏好。`?theme=light|dark|system` 保留原有含义：选择深知预设及对应模式。登录账户的设置页仍按现有逻辑同步远端 `theme_mode`；侧栏和移动端模式切换沿用本地偏好行为。

检查命令（在 `apps/web` 内运行）：

```sh
pnpm typecheck
pnpm lint
pnpm test
```

若跨分支后遇到已删除路由或测试的缓存引用，先重新生成 Next 路由类型，并将旧 `.next/test-output` 移到临时目录保存后重新运行测试，避免执行不属于当前分支的编译产物。

历史验收与变更记录见 [visual-themes-validation.md](../dev/records/design/visual-themes-validation.md)。
