# Deep Research Skill Migration 实机验收（2026-09-20）

结论：**DONE**。在本地启动真实 FastAPI 与 Next.js，访问 `http://127.0.0.1:3000/agents`，从页面运行 `/research`，确认知识底座真实请求、报告落盘、运行结果回填和页面弹层。

## 成功 Trace

- 主题：`/research ALiBi 原论文《Train Short, Test Long》如何实现位置偏置并验证长度外推？只研究这一篇论文，写约 500 字、带可核对页码引用的报告到 report.md。`
- Web BFF：`GET /api/v1/agent/config` 返回 HTTP 200，`skills` 含 `deep-research`；`/agents` 页面显示并强制选中该 Skill。
- Agent 请求 ID：`2a48b4c2-54d0-4081-a031-6039d7a54363`；run ID：`00962346051a4f0aa489ce3a8fdd7920`；模型：`qwen3.8-27b`。
- 页面工具 Trace 出现 `paper_search`、`paper_detail`、`read_paper`、`write_file({"path":"report.md", ...})`。同一请求 ID 的 Backend 日志中，知识底座 `POST /api/retrieval/search` 与 `GET /api/kg/paper` 均返回 HTTP 200，分别耗时 5450 ms、1811 ms。这条调用经 Agent Tool → `KnowledgeService` → `integrations/knowledge`。
- `report.md` 实际生成于本地会话工作区 `apps/backend/workspace/a561e6aa1ca2/ses_mu9uju2w_3dq21x/report.md`，大小 3168 字节，包含结论、机制、长度外推验证、局限和参考来源。
- Backend 日志：`agent.run.end`，`status=done`，`turns=7`，`duration_ms=131645`。页面出现报告摘要卡和“查看报告”；点击后弹层显示完整报告及“导出 HTML / 打印 / PDF / 复制全文”。页面的摘要卡与弹层由 `result.output.report` 驱动，证明报告正文已回填并可打开。

## 验证与边界

- `uv run --no-sync python -m unittest -q tests.test_deep_research_skill`：7 个测试通过。
- 第一轮较宽的 RoPE / ALiBi 对比研究成功调用知识库并读取两篇原始 PDF，但模型长上下文响应超时，`status=failed`；因此改用单篇论文问题完成端到端验收，并将本地 Backend 的单次模型响应超时设为 `AI_TIMEOUT_SEC=300`。此环境参数只用于本次运行，未写入仓库配置。
- 本次结论只覆盖 Agent 入口的 Deep Research Skill 迁移；独立 Deep Research 页面、Auto Research、durable session、Redis / multi-worker 和 Deep Research UI 重构均不在验收范围。
