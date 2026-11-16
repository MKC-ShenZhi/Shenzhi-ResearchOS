# V1 响应式布局与搜索连续性

## 维护边界

- `AppShell` 提供手机 Header、导航抽屉和内容区，沿用 `lg`（1024px）断点。
- 手机和桌面共用一个 `AppSidebar` 实例及其中的栏目定义、可用性判断、账号和历史入口，不重复请求会话历史。
- `MobileNavDrawer` 只管理临时开关、遮罩、ESC、Tab 焦点循环、背景 inert、滚动锁定及焦点返回。完整地址（含 session 参数）变化或进入桌面断点时关闭。
- 手机导航不写桌面 `collapsed`。子栏目沿用既有展开状态；手机设置通过设置页 Tabs 进入，不显示侧向悬停菜单。
- 普通页面使用响应式 CSS。`useVisualViewport` 仅提供软键盘可见高度，不决定请求或业务状态。Agent 工作区通过 `.app-workspace-height` 使用该高度，消息区内部滚动。
- 论文页以 CSS 切换阅读和 Assistant，保留同一 PDF 与 Assistant 实例。桌面仍使用原有折叠、拖动和键盘宽度调整。
- 手机文献库纵向呈现文件夹与内容，文件夹列表限制高度；论文行保留标题、来源及操作，桌面仍显示作者和添加时间。
- 手机 Composer 主菜单相对 Composer 定位，子菜单就地展开；桌面保留侧向菜单。上传、模型及 Agent 协议不变。

新增页面应复用 AppShell，优先采用 `min-w-0`、换行及响应式 CSS，不创建第二套业务实例。新的沉浸式工作区应同时检查可见高度、安全区域、内部滚动和返回来源。

## 搜索状态归属

| 状态 | 来源 | 行为 |
| --- | --- | --- |
| 已提交词、筛选和页码 | Feature URL | 显式链接优先；直接空路径不被历史搜索自动重定向 |
| 最后搜索导航地址 | 既有 search-restoration | 按身份/注册路径保存白名单参数，通过 SearchNavigationLink 恢复 |
| 首页简单搜索、论文库未提交文本 | search-draft + useSearchDraft | sessionStorage，按身份/入口隔离，来源 URL 必须相同；最多 2000 字、30 分钟有效 |
| 搜索结果 | 既有 TanStack Query Resource | 两分钟新鲜期、三分钟内存保留，复用预取和取消机制；刷新重新请求 |
| 列表浏览位置 | 既有 search-scroll-state | 按身份/完整条件保存，等待结果渲染后恢复；提交、筛选或翻页废弃旧位置 |

草稿不覆盖不同查询、筛选或页码的显式 URL。未提交的空字符串也是草稿；提交时清除，由 URL 接管。身份未就绪时不读写；退出/切换账号清除离开身份的草稿，不复制给新身份。禁止存储时仅保留当前运行时编辑能力，刷新不保证恢复。API 结果、附件、AI 提问及附件正文不进入草稿存储。

首页只持久化简单搜索文本。恢复非空草稿时选择简单搜索；手动切换智能/简单模式仍保留当前输入。简单搜索提交导航前清除草稿。

### 搜索导航恢复机制

搜索导航恢复由 `apps/web/lib/navigation/search-restoration.ts` 的静态路由与参数白名单管理，
只在 `sessionStorage` 中按认证用户 ID（未登录为 `anonymous`）保存最后一次带参数的内部地址。
`AppShell` 在 Suspense 内监听 URL，侧栏 `SearchNavigationLink` 读取恢复地址并保留原生 Link 行为；
直接访问空路径不自动跳转，也不清除记录。Feature 继续负责 URL 的业务解析、请求和缓存，
主动清空时调用 `useClearSearchRestoration`；部分条件清除后仍有参数则记录新的地址。
新增搜索入口只需注册路径与允许参数，并在需要恢复的导航入口使用该 Link。
论文库的 `?mode=keyword` 与 `?mode=conference` 是显式登记的模式导航入口，使用同一
恢复机制分开保存各模式最近的查询地址；仅这些模式入口允许恢复，携带具体查询条件的
完整链接仍直接使用。`/knowledge/search/conferences` 作为独立目录保存自身筛选条件。
清空某一模式只清理该模式及指向它的最后导航地址，清空论文库主入口则同时清理两种模式。
存储访问集中封装，可替换存储策略；不可用时退回原始导航地址。认证切换时不将当前旧 URL
记到新身份下，直到 URL 再次变化。未提交的输入草稿、API 响应和其他页面状态不在此导航地址恢复机制内。
首页简单搜索与论文库的短期文本草稿由 `lib/navigation/search-draft.ts` 和
`hooks/use-search-draft.ts` 管理，按身份、入口及来源 URL 隔离，不保存附件或 API 结果。

## 验证方式

在 `apps/web` 中执行 `pnpm typecheck`、`pnpm lint`、`pnpm test`、`pnpm build`。
常规测试现已包含此前遗漏的 `tests/search/`。旧 simple-search 源码约束已校正到实际 Hook / Query Resource 边界。
草稿回归覆盖跨页/刷新、显式条件、身份和入口隔离、退出清理、空值、过期/损坏记录及禁止存储。

浏览器验收记录实际 CSS 视口，重点检查 375px、约 390px、768px、1280px：

1. 抽屉、遮罩、ESC、Tab/Shift+Tab、同路由链接、session 参数、登录及跨断点状态。
2. 草稿离页/刷新、显式分享链接、搜索/筛选/翻页、详情返回位置、清空和身份切换。
3. 首页模式、模型/附件/技能菜单、Agent 发送/停止/历史和长文本。
4. 文件夹管理、收藏/移动、上传、阅读历史及列表操作菜单。
5. PDF 加载/缩放、切换 Assistant 后的输入与阅读位置、桌面双栏折叠与调整宽度。
6. 图谱节点及详情、工具栏换行与纵向滚动。

模拟视口不能替代 iOS Safari / Android Chrome 真机软键盘、安全区域、旋转、文件选择及长 PDF 验收。
未登录环境只能验证文献库布局与鉴权提示，不能代替登录态收藏/上传。不得把权限错误提示记为业务成功。

历史验收与变更记录见 [responsive-core-validation.md](../dev/records/engineering/responsive-core-validation.md)。
