# Topic V2 验收记录

> 从 [TOPIC-V2-STABILITY.md](../../../knowledge/TOPIC-V2-STABILITY.md) 拆出的历史记录，只反映记录当时的状态；当前约定以原文档为准。

## 广场渲染优化验证（2026-10-15）

- `cd apps/web && pnpm typecheck` 通过；本次四个 TSX 文件的 ESLint 检查通过。
- `cd apps/web && pnpm test`：299 项通过，0 失败。
- 使用现有本地 Web / Backend 进行浏览器验收：默认窗口初始挂载由 295 张降为 20 张（含精选及视口附近的三个分类），其余分类保留占位；滚动激活后每分类仍先挂载 6 张。
- 机器学习轮播能够追加至 49 张，49 个唯一详情链接，末尾右箭头消失；分类网格按 24 → 48 → 49 追加，末尾移除加载按钮。切换至大语言模型时重新显示 24 / 58。
- 搜索 `machine translation` 可找到默认批次以外的机器翻译主题；分类组合空结果正常，详情显示真实的 22 篇关联论文，返回广场保留搜索条件。
- 精选与分类中同一主题的关注按钮同步更新；窄屏布局无页面横向溢出，初始挂载 14 张；占位行与实际卡片行高度差约 1px。中等宽度下将轮播箭头收近，避免原有外置箭头撑出页面，2xl 宽屏保留外置位置。浏览器未记录运行错误，有一条重复封面资源的 Next Image LCP 建议。
- 本次未修改 Backend、接口、目录数据或依赖；未重跑生产构建与后端测试。上面是 DOM 挂载数量和交互验证，不代表首屏耗时提升比例。

## 本地验证（2026-10-13）

本轮两项 P1 修复重新执行下表中的六条前后端检查命令；新增回归覆盖返回 URL 与安全兜底、Catalog 导入隔离、标准 500、缓存及修复恢复。全量后端与浏览器联调条目保留此前验证记录，本轮未重跑。

| 命令 / 验收 | 结果 |
| --- | --- |
| `cd apps/web && pnpm typecheck` | 通过 |
| `cd apps/web && pnpm lint` | 0 错误；Chat Hook 与 popover Hook 各有 1 条既有依赖警告 |
| `cd apps/web && pnpm test` | 282 项通过，0 失败 |
| `cd apps/web && pnpm build` | 通过，Turbopack 生产构建及 30 个静态页面生成成功 |
| `cd apps/backend && uv --cache-dir /private/tmp/shenzhi-topic-uv-cache run --locked --no-sync python -m unittest discover -s tests -p 'test_topic*.py'` | 18 项通过，0 失败，包含目录质量与资源存在性 |
| `cd apps/backend && uv --cache-dir /private/tmp/shenzhi-topic-uv-cache run --locked --no-sync python -m unittest discover -s tests -p 'test_knowledge*.py'` | 103 项通过，包含正常响应与分页边界 |
| `cd apps/backend && uv --cache-dir /private/tmp/shenzhi-topic-uv-cache run --locked --no-sync python -m unittest discover -s tests` | 403 项：379 通过、23 跳过、1 导入错误 |
| 浏览器实际 BFF 链路 | 中文、llm、英文 subjectQuery、Enter、搜索按钮、分类组合、空结果、前进/后退已验证 |
| 真实知识底座 | 机器翻译主题 total=22；offset=0/10/20 均 200，10→20→22，结束提示正确；打开论文摘要成功并通过返回按钮回到 Topic |
| 窄屏详情 | 封面、简介、创建者、实时数量及列表正常，无横向页面溢出 |
| 下一页故障注入 | 对比学习已加载 10 条后临时停止本次启动的本地 FastAPI；offset=10 两次 503（初次 + 一次自动重试）后保留 10 条并显示手动重试；继续滚动没有额外请求；恢复后手动重试仅请求 offset=10，追加为 20 条，20 个唯一论文链接 |

后端全量测试的唯一错误是 `test_reading_history.py` 仍导入已不存在的 `app.services.reading_history`，本地 dev 也存在相同引用；属于既有无关问题。本次没有修改它。23 个跳过项需要对应数据库/集成测试环境。

沙箱内无法监听本地端口，最初 Turbopack 构建未完成；获得工具权限后，沿用原构建命令成功。uv 使用临时缓存及 `--locked --no-sync`，不更新依赖和锁文件。本地联调启动 FastAPI 时关闭 lifespan，避免无关的 Chat 恢复操作，因此不代表完整后台启动和数据库恢复验证。

真实输入法候选确认、不同浏览器、PDF 正文/图谱及超 1000 条主题的上游实测仍需人工验收。1000 条停止、失败后缓存保留和只重试下一页由实际 TanStack Query Observer 回归测试覆盖。

## 合并 dev 前的既有分支差异

以下是 `dev...HEAD` 中已有内容，本次未修改或删除，需负责人确认是否应随 Topic 合并：

- `apps/backend/uv.lock`：1581 行增加、1408 行删除，registry 从 PyPI 改为清华镜像，26 个包版本变化，并新增 opentelemetry-api。pyproject.toml 没有对应差异；不能视为 Topic 所需依赖变化。
- `app/models/chat.py`：增加匿名会话过期索引；仓库已有对应迁移，仍属于 Chat 清理能力。
- `migrations/env.py`：新增 collections、reading_history 模型导入，属于文献/阅读历史迁移配置。
- `OPEN.bat`、`scripts/start-local-services.ps1`、`scripts/start-local-postgres.bat`、ONBOARDING：修改 Windows PostgreSQL、FastAPI、Next.js 的启动与就绪检查流程；本次 macOS 未执行这些脚本。

Topic 修改已通过适用检查；整分支尚不能作为全量绿灯直接合并。需先确认上述范围、修复或明确豁免既有测试导入错误，并完成真实输入法与部署环境人工验收。
