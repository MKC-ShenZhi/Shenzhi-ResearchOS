# Topic V2 OpenAlex 迁移验收

验收日期为 2026 年 11 月 10 日，基线为 GitHub `dev` 的 `3f108f4`。

## 真实接口和浏览器

- 使用本机 Next.js、FastAPI 和独立 PostgreSQL 测试库。FastAPI 按 `KNOWLEDGE_BASE_API_URL` 访问真实知识底座。
- 从 FastAPI 和 Next.js BFF 两个入口分别检查默认目录，均得到 75 个不同的叶节点和 11 个 Subfield。各分类计数之和与总数一致。
- `openalex:topic:T10028` 的编码路径返回详情和 12,379 篇论文统计。论文列表验证了 offset `0`、`20`、`1001`、`12377` 和 `12379`，抽查的页面之间没有重复 ID。使用响应里的 `paper_id` 打开论文详情成功。
- 旧 ID `deep-learning`、未启用 ID `openalex:topic:T10181` 和父节点 `openalex:subfield:1702` 的详情与论文请求均返回 404。
- Chrome 通过真实页面验证了窄屏分类横向滚动、Subfield 筛选和返回后恢复选择、编码详情、默认封面、无限加载和论文详情跳转。硬刷新后详情请求只对 Topic ID 编码一层。
- 匿名点击关注会打开登录提示。通过 Better Auth 登录两个隔离测试账号后，验证了关注、取消、刷新后状态、公开人数和账号隔离。预置的旧关注记录保留原 ID，旧详情链接显示找不到主题。浏览器无 JavaScript 异常。

## 自动化检查

在隔离 PostgreSQL 测试库执行迁移后，于 `apps/backend` 运行以下命令。

```powershell
uv run --locked --no-sync --env-file <TEST_ENV_FILE> python -m unittest tests.test_topic_api tests.test_topic_catalog tests.test_knowledge tests.test_knowledge_entities tests.test_knowledge_query tests.test_interactions_api tests.test_interactions_persistence tests.test_stats_snapshot tests.test_recommendation -v
```

165 项通过。上游 Mock 覆盖超时、404、失败恢复、目录动态变更、重复 ID、权限校验和分页适配。持久化与快照用例连接真实测试数据库。

于 `apps/web` 运行以下命令。

```powershell
pnpm run test
pnpm run typecheck
pnpm run build
pnpm exec eslint clients/knowledge features/knowledge/topics features/knowledge/papers/components/saved-interactions.tsx app/knowledge/topics tests/knowledge/bff.test.ts tests/knowledge/topic-papers.test.ts tests/knowledge/topics.test.ts
```

417 项前端测试通过，类型检查、生产构建与改动范围内的 ESLint 通过。
